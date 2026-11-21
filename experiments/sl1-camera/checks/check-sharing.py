#!/usr/bin/python3
"""Check that a second desktop camera client cannot interrupt the current one."""
import json
from pathlib import Path
import signal
import subprocess as sp
import sys
import tempfile
import time

def sink(name):
    import gi
    gi.require_version("Gst", "1.0")
    from gi.repository import Gst
    Gst.init(None)
    ir = name == "infrared"
    token = "surface-laptop-ov7251-ir" if ir else "CAMF"
    nodes = json.loads(sp.check_output(["pw-dump"], timeout=4))
    props = next(p for n in nodes if n["type"].endswith(":Node") and (p := n.get("info", {}).get("props", {})).get(
        "media.class") == "Video/Source" and token in p.get("node.name", ""))
    w,h = (640,480) if ir else (1280,720)
    fmt = "YUY2" if ir else "NV12"
    pipe = Gst.parse_launch(f"pipewiresrc name=cam ! video/x-raw,width={w},height={h},format={fmt} ! "
                            "appsink name=s sync=false max-buffers=2 drop=true wait-on-eos=false")
    pipe.get_by_name("cam").set_property("target-object", str(props["object.serial"]))
    app = pipe.get_by_name("s")
    quitting = []
    signal.signal(signal.SIGTERM, lambda *_: quitting.append(True))
    end = time.monotonic() + 18
    try:
        pipe.set_state(Gst.State.PLAYING)
        while not quitting and time.monotonic() < end:
            sample = app.emit("try-pull-sample", 100*Gst.MSECOND)
            if sample:
                print(time.monotonic(), sample.get_buffer().pts, flush=True)
            elif pipe.get_bus().pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.EOS):
                break
    finally:
        pipe.set_state(Gst.State.NULL)

class Client:
    def __init__(self, directory, camera, tag):
        self.out = Path(directory) / (camera + tag)
        with self.out.open("w") as out, self.out.with_suffix(".log").open("w") as err:
            self.proc = sp.Popen([sys.executable, __file__, "--sink", camera], stdout=out, stderr=err)

    def frames(self):
        return [(float(row[0]), int(row[1])) for line in self.out.read_text().splitlines()
                if len(row := line.split()) == 2]

    def flowing(self, timeout=4):
        limit = time.monotonic() + timeout
        while time.monotonic() < limit:
            if len(self.frames()) >= 5: return True
            if self.proc.poll() is not None: break
            time.sleep(.05)
        return False

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=2)
            except sp.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=2)

def order(directory, first, second):
    clients = []
    def start(name, tag):
        c = Client(directory,name,tag)
        clients.append(c)
        return c
    try:
        owner = start(first, "-owner")
        if not owner.flowing(): raise RuntimeError(first + " did not start")
        contender = start(second, "-contender")
        time.sleep(.35)  # allow for starting GStreamer and the PipeWire connection
        begin = time.monotonic()
        time.sleep(1.25)
        end = time.monotonic()
        samples = [pts for t,pts in owner.frames() if begin <= t <= end]
        blocked = len([t for t,_ in contender.frames() if t <= end]) == 0
        fps = ((len(samples)-1)*1e9/(samples[-1]-samples[0])
               if len(samples)>1 and samples[-1]>samples[0] else 0)
        advancing = all(b>a for a,b in zip(samples,samples[1:]))
        if first == "color":
            owner.close()
            handoff = contender.flowing()
        else:
            # A libcamera app may report busy and require a fresh open.
            contender.close()
            owner.close()
            handoff = start(second,"-reopen").flowing()
        expected = 30 if first=="color" else 15
        return dict(first=first, second=second, owner_frames=len(samples), owner_fps=round(fps,1),
                    second_blocked_during_overlap=blocked, second_works_after_release=handoff,
                    passed=blocked and handoff and advancing and len(samples)>=expected and .85*expected<=fps<=1.15*expected)
    finally:
        for c in reversed(clients): c.close()

if __name__ == "__main__":
    if len(sys.argv)==3 and sys.argv[1]=="--sink":
        sink(sys.argv[2])
    else:
        with tempfile.TemporaryDirectory(prefix="sl1-camera-sharing-") as d:
            rows = [order(d,"color","infrared"), order(d,"infrared","color")]
        print(json.dumps({"sharing_tests":rows},indent=2))
        sys.exit(0 if all(r["passed"] for r in rows) else 1)
