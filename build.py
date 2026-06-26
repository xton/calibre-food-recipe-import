#!/usr/bin/env python3
"""
Build import_recipe.zip — the Calibre plugin package.

Usage:
    python build.py

Produces dist/import_recipe.zip, which you install via:
    Calibre → Preferences → Plugins → Load plugin from file
"""

import os
import zipfile
import sys

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "calibre_plugin")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "dist")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "import_recipe.zip")

INCLUDE_SUFFIXES = (".py", ".png", ".svg", ".txt")


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    files = []
    for dirpath, dirnames, filenames in os.walk(PLUGIN_DIR):
        # skip __pycache__
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fname in filenames:
            if any(fname.endswith(s) for s in INCLUDE_SUFFIXES):
                abs_path = os.path.join(dirpath, fname)
                # path inside zip: relative to PLUGIN_DIR
                rel_path = os.path.relpath(abs_path, PLUGIN_DIR)
                files.append((abs_path, rel_path))

    with zipfile.ZipFile(OUTPUT_FILE, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in sorted(files):
            zf.write(abs_path, rel_path)
            print(f"  + {rel_path}")

    print(f"\nBuilt {OUTPUT_FILE}  ({os.path.getsize(OUTPUT_FILE):,} bytes)")
    print("\nInstall in Calibre:")
    print("  Preferences → Plugins → Load plugin from file → select dist/import_recipe.zip")
    print("  Then restart Calibre and add 'Import Recipe' to your toolbar.")


if __name__ == "__main__":
    main()
