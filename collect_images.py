"""
Optional helper: copy just the BASE card images into the app, preserving your
images/<SET>/ folder structure and skipping the _p/_r alt-art asset files the
app doesn't use.

You may not need this at all: since your images are already organised as
images/<SET>/<file> (images/OP01/OP01-120.png, ...), you can simply copy your
whole images/ folder into the app folder next to index.html and you're done.

Use this script only if you want a leaner copy (base images only, no _p/_r files):

    python collect_images.py --src images --dest most-wanted-app/images

It mirrors images/<SET>/<CODE>.png and drops the alt-art assets.
"""

import argparse
import re
import shutil
from pathlib import Path

BASE_RE = re.compile(r"^[A-Z0-9]+-\d{3}\.png$")  # OP01-120.png — no _p/_r suffix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="images")
    ap.add_argument("--dest", default="most-wanted-app/images")
    args = ap.parse_args()

    src = Path(args.src)
    dest = Path(args.dest)
    if not src.exists():
        raise SystemExit(f"Source not found: {src.resolve()}  (pass --src to point at your images/ folder)")

    copied = skipped = 0
    for png in src.rglob("*.png"):
        if not BASE_RE.match(png.name):
            skipped += 1               # alt-art asset (_p/_r) — unused by the app
            continue
        set_folder = png.name.split("-")[0]      # OP01-120.png -> OP01
        out_dir = dest / set_folder
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(png, out_dir / png.name)
        copied += 1

    size_mb = sum(f.stat().st_size for f in dest.rglob("*.png")) / (1024 * 1024)
    print(f"Copied {copied} base images into {dest}/<SET>/  ({size_mb:.0f} MB)")
    print(f"Skipped {skipped} alt-art / non-base files.")


if __name__ == "__main__":
    main()

