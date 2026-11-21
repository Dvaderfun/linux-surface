"""Resolve the OV7251 and linked CIO2 nodes without changing the media graph."""
import glob
import re
import subprocess

def ctl(*args):
    return subprocess.check_output(args, text=True)


def discover():
    # Enumerate actual media links: device minor numbers change after reboot.
    for media in sorted(glob.glob("/dev/media[0-9]*")):
        graph = ctl("media-ctl", "-d", media, "-p")
        # Read-only discovery: starting/advertising the service must not
        # configure the shared CIO2 controller while a colour client owns it.
        chunks = re.split(r"^\s*- entity (\d+): ", graph, flags=re.M)
        ids = {block.partition(" (")[0]: num for num, block in zip(chunks[1::2], chunks[2::2])}
        for block in chunks[2::2]:
            match = re.match(r"(ov7251 [\da-fA-F]+-[\da-fA-F]+) \(", block)
            link = re.search(r'-> "(ipu3-csi2 (\d+))":0 \[', block)
            if not (match and link):
                continue
            sensor, bridge, port = match[1], link[1], link[2]
            def node(name):
                return ctl("media-ctl", "-d", media, "-e", name).strip()
            return node(f"ipu3-cio2 {port}"), node(sensor), media, node(bridge), ids[sensor], ids[bridge]
    raise SystemExit("No connected OV7251 infrared sensor was found.")
