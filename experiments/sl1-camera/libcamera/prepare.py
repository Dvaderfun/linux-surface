#!/usr/bin/env python3
"""Recreate the tested contributions in a fresh checkout. Does not build or install."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.request import urlopen

root = Path(__file__).resolve().parent
base = 'adfa719f8ed67d18fd8a0739fc088a1f8b9e7252'
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('checkout', type=Path, help='new or empty path for the source checkout')
p.add_argument('--with-720', action='store_true', help='include the dependent SL1 native-HD RFC')
args = p.parse_args()
tree = args.checkout.resolve()
if tree.exists() and (not tree.is_dir() or any(tree.iterdir())):
    raise SystemExit('Choose a new or empty checkout directory.')
tree.mkdir(parents=True, exist_ok=True)
def git(*cmd):
    subprocess.run(['git','-C',str(tree),*map(str,cmd)],check=True)
def apply(path):
    git('apply','--check',path)
    git('apply',path)
git('init','-q')
git('remote','add','origin','https://gitlab.freedesktop.org/camera/libcamera.git')
git('fetch','-q','--depth=1','origin',base)
git('checkout','-q','--detach',base)
manifest = json.loads((root/'public-patches'/'manifest.json').read_text())
with tempfile.TemporaryDirectory(prefix='libcamera-public-patches-') as tmp:
    for item in manifest:
        n = item['patchwork_id']
        if n==28870:
            apply(root/'compat'/'28870-current-api.diff')
            continue
        path = root/'public-patches'/f'{n}.mbox'
        if not path.is_file():
            path=Path(tmp)/f'{n}.mbox'
            with urlopen(item['url']+'mbox/', timeout=25) as r: path.write_bytes(r.read())
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            raise SystemExit(f'Checksum mismatch: {item["url"]}')
        apply(path)
if args.with_720: apply(root/'rfc'/'ov9734-native-720.diff')
git('diff','--check')
print('Prepared',tree)
