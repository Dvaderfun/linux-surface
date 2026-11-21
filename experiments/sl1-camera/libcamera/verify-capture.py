#!/usr/bin/env python3
# Read numeric capture metadata only. cam saves no images unless --file is set.
import argparse
import json
import re
import statistics
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("cam", type=Path)
p.add_argument("--height", type=int, choices=[704, 720], required=True)
p.add_argument("--reject-hd", action="store_true")
p.add_argument("--fixed-30", action="store_true")
p.add_argument("--role", choices=["video", "viewfinder", "still"], default="viewfinder")
a = p.parse_args()
def cmd(*args):
    return subprocess.run([str(a.cam.resolve()), *args], capture_output=True, text=True, timeout=14)
def success(r):
    if r.returncode:
        raise SystemExit(f"cam failed ({r.returncode}):\n{r.stdout[-700:]}\n{r.stderr[-1700:]}")
# On a shared desktop the libcamera manager may enumerate media links even before acquire.
# Decline to start while either sensor is active. Never force or stop other clients.
for node in ["i2c-OVTI9734:00", "i2c-INT347E:00"]:
    state = Path("/sys/bus/i2c/devices") / node / "power/runtime_status"
    if not state.is_file() or state.read_text().strip() != "suspended":
        raise SystemExit("Camera absent or already active; skipping capture")
listing = cmd("-l")
success(listing)
hit = re.search(r"^\d+:.*ov9734.*\(([^()]+)\)", listing.stdout, re.M | re.I)
if not hit:
    raise SystemExit("No OV9734 listed: " + listing.stdout + listing.stderr[-900:])
cam = hit.group(1)
def capture(height, role, count):
    return cmd("-c", cam, "--strict-formats", "-s",
               f"role={role},width=1280,height={height},pixelformat=NV12", f"-C{count}",
               *(["--script", str(Path(__file__).with_name("fixed-30.yaml"))] if a.fixed_30 else []))
result = {"role": a.role, "format": "NV12", "width": 1280, "height": a.height,
          "frame_duration_limits_us": [33333,33333] if a.fixed_30 else None}
if a.reject_hd:
    reject = capture(720, a.role, 1)
    msg = reject.stdout + '\n' + reject.stderr
    if reject.returncode == 0 or not re.search(r"adjust|unsupported|invalid", msg, re.I):
        raise SystemExit("Expected explicit rejection of strict 720p, got " + msg[-1500:])
    result["strict_1280x720_rejected"] = True
# allow for an intentional initial FrameError with zero bytes in the upstream series
r = capture(a.height, a.role, 50)
success(r)
frames = [(float(ts), int(seq), int(y), int(uv)) for ts, seq, y, uv in re.findall(
    r"^(\d+\.\d+).*?stream0 seq:\s*(\d+) bytesused:\s*(\d+)/(\d+)", r.stdout, re.M)]
valid = [(t, s) for t,s,y,uv in frames if y == 1280*a.height and uv == 640*a.height]
if len(valid) < 48 or any(t2<=t1 or s2<=s1 for (t1,s1),(t2,s2) in zip(valid,valid[1:])):
    raise SystemExit(f"Unexpected frame count/sequence: {len(valid)}/50, output:\n" + r.stdout[-600:])
ts = [t for t,_ in valid]
result.update(full_frames=len(valid), captured=len(frames), plane_bytes=[1280*a.height,640*a.height],
              median_interframe_fps=round(1/statistics.median(b-a for a,b in zip(ts[8:],ts[9:])),2),
              delivered_fps=round((len(ts)-1)/(ts[-1]-ts[0]),2))
print(json.dumps(result, indent=2))
