#!/usr/bin/python3
"""Verify the physical camera through the same PipeWire graph desktop apps use."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst


def check_camera(infrared):
    objects = json.loads(subprocess.check_output(["pw-dump"], timeout=8))
    props = {o["id"]: o.get("info", {}).get("props", {}) for o in objects}
    for o in objects:
        p = props[o["id"]]
        if not o["type"].endswith(":Node") or p.get("media.class") != "Video/Source":
            continue
        device = props.get(p.get("device.id"), {})
        identity = str((p, device))
        if infrared:
            if not re.search(r"ov7251|surface.*infrared|surface[._-]ir", identity, re.I):
                continue
        elif not re.search(r"OVTI9734|ov9734|CAMF", identity, re.I):
            continue
        return p
    if not infrared and not Path("/sys/bus/i2c/devices/i2c-OVTI9734:00/driver").exists():
        sys.exit("Color sensor is not bound. Check Secure Boot enrollment and the running Surface kernel.")
    sys.exit("No matching camera is published by PipeWire. See: wpctl status")


def test(props, infrared):
    Gst.init(None)
    w, h, wanted = (640, 480, 12) if infrared else (1280, 720, 60)
    pipeline = Gst.parse_launch(f"pipewiresrc name=camera ! video/x-raw,width={w},height={h} ! videoconvert ! "
                                "video/x-raw,format=RGB ! appsink name=frames "
                                "sync=false max-buffers=2 drop=true wait-on-eos=false")
    pipeline.get_by_name("camera").set_property("target-object", str(props["object.serial"]))
    sink = pipeline.get_by_name("frames")
    bus = pipeline.get_bus()
    count, stamps, pixel_min, pixel_max = 0, [], 255, 0
    print(f"Opening {props.get('node.description') or props['node.name']} for {wanted} frames …", flush=True)
    deadline = time.monotonic() + 15
    try:
        if pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
            sys.exit("Could not start the PipeWire stream.")
        while count < wanted and time.monotonic() < deadline:
            sample = sink.emit("try-pull-sample", 500 * Gst.MSECOND)
            if sample is None:
                msg = bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS)
                if msg:
                    sys.exit(str(msg.parse_error()[0]) if msg.type == Gst.MessageType.ERROR
                             else "Source stopped early.")
                continue
            buf, caps = sample.get_buffer(), sample.get_caps().get_structure(0)
            width, height = caps.get_value("width"), caps.get_value("height")
            ok, view = buf.map(Gst.MapFlags.READ)
            if not ok:
                sys.exit("Could not read a delivered video buffer.")
            try:
                if len(view.data) < width * height * 3:
                    sys.exit("Truncated RGB frame.")
                # In-memory brightness check only; never save or display the image.
                levels = view.data[::max(1, len(view.data) // 1000)]
                pixel_min, pixel_max = min(pixel_min, min(levels)), max(pixel_max, max(levels))
            finally:
                buf.unmap(view)
            if buf.pts != Gst.CLOCK_TIME_NONE:
                stamps.append(buf.pts)
            count += 1
    finally:
        pipeline.set_state(Gst.State.NULL)
    if count != wanted or len(stamps) < 2 or any(b <= a for a, b in zip(stamps, stamps[1:])):
        sys.exit(f"Capture incomplete or timestamps not advancing: {count}/{wanted} frames.")
    last = stamps[-30:]
    fps = (len(last) - 1) * Gst.SECOND / (last[-1] - last[0])
    print(f"PASS: {count} timestamped {width}×{height} frames through PipeWire at {fps:.1f} fps; "
          f"sample range {pixel_min}–{pixel_max}/255. No images saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--infrared", action="store_true", help="Test the optional monochrome camera.")
    infrared = parser.parse_args().infrared
    test(check_camera(infrared), infrared)
