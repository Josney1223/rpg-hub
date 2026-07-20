"""Music packs: bundle playlists + their audio into a portable .zip.

A pack is a zip containing:
    pack.json          -- manifest (name, version, playlists with RELATIVE paths)
    audio/<files...>   -- the actual audio

Import extracts into <config>/packs/<pack-name>/ and returns playlists whose
track paths are absolute (pointing into the extracted folder), ready to append
to the app's playlist list.
"""

import os
import re
import json
import shutil
import zipfile
import tempfile

from . import config

MANIFEST = "pack.json"


def _safe(name):
    s = re.sub(r"[^A-Za-z0-9._-]", "_", str(name)).strip("_")
    return s or "pack"


def export_pack(zip_path, playlists, pack_name="Music Pack"):
    """Write a pack zip from the given playlist dicts. Returns zip_path."""
    tmp = tempfile.mkdtemp()
    try:
        audio_dir = os.path.join(tmp, "audio")
        os.makedirs(audio_dir)
        manifest = {"name": pack_name, "version": 1, "playlists": []}
        used = {}  # dest filename -> source path (dedupe / collision handling)
        for pl in playlists:
            rel = []
            for src in pl.get("tracks", []):
                if not os.path.isfile(src):
                    continue
                base = os.path.basename(src)
                dest = base
                i = 1
                while dest in used and used[dest] != src:
                    stem, ext = os.path.splitext(base)
                    dest = f"{stem}_{i}{ext}"
                    i += 1
                if dest not in used:
                    shutil.copy2(src, os.path.join(audio_dir, dest))
                    used[dest] = src
                rel.append("audio/" + dest)
            manifest["playlists"].append({
                "name": pl["name"],
                "category": (pl.get("category") or "OST").upper(),
                "tracks": rel,
                "loop": pl.get("loop", True),
                "shuffle": pl.get("shuffle", False),
            })
        with open(os.path.join(tmp, MANIFEST), "w") as fh:
            json.dump(manifest, fh, indent=2)

        if os.path.exists(zip_path):
            os.remove(zip_path)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(tmp):
                for fn in files:
                    full = os.path.join(root, fn)
                    z.write(full, os.path.relpath(full, tmp))
        return zip_path
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def import_pack(zip_path):
    """Extract a pack and return (pack_name, [playlist dicts with abs paths])."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if MANIFEST not in names:
            raise ValueError("Not a valid music pack (no pack.json inside).")
        manifest = json.loads(z.read(MANIFEST))
        pack_name = manifest.get("name", os.path.splitext(os.path.basename(zip_path))[0])
        dest_dir = os.path.join(config.PACKS_DIR, _safe(pack_name))
        os.makedirs(dest_dir, exist_ok=True)
        root_abs = os.path.abspath(dest_dir)
        for n in names:
            if n.endswith("/"):
                continue
            target = os.path.join(dest_dir, n)
            if not os.path.abspath(target).startswith(root_abs):
                continue  # guard against path traversal in the zip
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(n) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)

    playlists = []
    for pl in manifest.get("playlists", []):
        tracks = [os.path.join(dest_dir, t) for t in pl.get("tracks", [])]
        playlists.append({
            "name": pl["name"],
            "category": (pl.get("category") or "OST").upper(),
            "tracks": tracks,
            "loop": pl.get("loop", True),
            "shuffle": pl.get("shuffle", False),
        })
    return pack_name, playlists
