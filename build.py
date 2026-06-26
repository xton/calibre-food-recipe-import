#!/usr/bin/env python3
"""
Build import_recipe.zip — the Calibre plugin package.

Usage:
    python build.py [--output-dir DIR]

Produces dist/import_recipe.zip (or DIR/import_recipe.zip).

Install via:
    Calibre → Preferences → Plugins → Load plugin from file
"""

import argparse
import importlib.util
import os
import zipfile

PLUGIN_DIR = os.path.join(os.path.dirname(__file__), "calibre_plugin")

# Files included in the zip by suffix.  The plugin-import-name-*.txt sentinel
# must be included; images (.png/.svg) are optional but kept for completeness.
INCLUDE_SUFFIXES = (".py", ".png", ".svg", ".txt")


def _load_version() -> str:
    """Read version tuple from calibre_plugin/__init__.py without importing calibre."""
    init_path = os.path.join(PLUGIN_DIR, "__init__.py")
    with open(init_path) as fh:
        for line in fh:
            if line.strip().startswith("version = ("):
                # e.g.  version = (0, 1, 0)
                nums = line.split("(", 1)[1].split(")")[0]
                return ".".join(p.strip() for p in nums.split(","))
    return "0.0.0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=os.path.join(os.path.dirname(__file__), "dist"))
    args = parser.parse_args()

    version = _load_version()
    os.makedirs(args.output_dir, exist_ok=True)
    output_file = os.path.join(args.output_dir, "import_recipe.zip")

    files = []
    for dirpath, dirnames, filenames in os.walk(PLUGIN_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fname in filenames:
            if any(fname.endswith(s) for s in INCLUDE_SUFFIXES):
                abs_path = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(abs_path, PLUGIN_DIR)
                files.append((abs_path, rel_path))

    with zipfile.ZipFile(output_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for abs_path, rel_path in sorted(files):
            zf.write(abs_path, rel_path)
            print(f"  + {rel_path}")

    size = os.path.getsize(output_file)
    print(f"\nv{version}  →  {output_file}  ({size:,} bytes)")
    print("\nInstall in Calibre:")
    print("  Preferences → Plugins → Load plugin from file → select the zip above")
    print("  Then restart Calibre and add 'Import Recipe' to your toolbar.")


if __name__ == "__main__":
    main()
