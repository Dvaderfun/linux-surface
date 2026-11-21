#!/usr/bin/env python3
"""Confirm the extra 16 luma and 8 chroma rows contain live image data, in memory."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import json
import os
from pathlib import Path
import re
import statistics
import subprocess as sp

p = argparse.ArgumentParser()
p.add_argument("cam", type=Path)
a = p.parse_args()
cam = str(a.cam.resolve())
for node in ["i2c-OVTI9734:00", "i2c-INT347E:00"]:
    if (Path("/sys/bus/i2c/devices") / node / "power/runtime_status").read_text().strip() != "suspended":
        raise SystemExit("Camera active; skipping")
listing = sp.run([cam, "-l"], capture_output=True, check=True, text=True)
camera_id = re.search(r"^\d+:.*ov9734.*\(([^()]+)\)", listing.stdout, re.M | re.I).group(1)
w, h, n = 1280, 720, 30
bands = [(0, 688, 704, 0), (0, 704, 720, 0), (w*h, 344, 352, 0), (w*h, 352, 360, 0),
         (w*h, 344, 352, 1), (w*h, 352, 360, 1)]
def measure(readfd):
    observations = [[] for _ in bands]
    with os.fdopen(readfd, "rb") as reader:
        for i in range(n):
            data = reader.read(w*h*3//2)
            if len(data) != w*h*3//2:
                raise ValueError(f"Incomplete frame {i}")
            if i < 8: continue
            for j, (offset, y0, y1, channel) in enumerate(bands):
                samples = b''.join(data[offset+w*y+channel:offset+w*(y+1):32] for y in range(y0, y1))
                observations[j].append((statistics.mean(samples), statistics.pstdev(samples), hash(samples)))
        if reader.read(1):
            raise ValueError("Unexpected bytes after last frame")
    return [{"mean": round(statistics.median(x[0] for x in band),1),
             "spatial_sd": round(statistics.median(x[1] for x in band),1),
             "distinct_frames": len(set(x[2] for x in band))} for band in observations]
rfd, wfd = os.pipe()
args = [cam, "-c", camera_id, "--strict-formats", "-s", "role=viewfinder,width=1280,height=720,pixelformat=NV12",
        "-C"+str(n), "--script", str(Path(__file__).with_name("fixed-30.yaml")), "--file=/proc/self/fd/"+str(wfd)]
with sp.Popen(args, stdout=sp.DEVNULL, stderr=sp.PIPE, pass_fds=(wfd,)) as proc:
    os.close(wfd)
    with ThreadPoolExecutor(max_workers=1) as pool:
        work = pool.submit(measure, rfd)
        try:
            _, errors = proc.communicate(timeout=10)
        except BaseException:
            proc.kill(); proc.wait(); raise
        if proc.returncode: raise SystemExit(errors.decode()[-700:])
        stats = work.result()
labels = ["Y.previous16","Y.bottom16","U.previous8","U.bottom8","V.previous8","V.bottom8"]
ok = all(s["distinct_frames"] >= 10 and s["spatial_sd"] > 0.5 for s in stats)
ok &= all(abs(stats[i]["mean"]-stats[i+1]["mean"])<35 for i in (0,2,4))
print(json.dumps({"spatial_test_pass":bool(ok),"frames":n,"skip_initial":8,"bands":dict(zip(labels,stats))},indent=2))
if not ok: raise SystemExit(1)
