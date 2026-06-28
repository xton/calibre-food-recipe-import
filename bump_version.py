#!/usr/bin/env python3
"""
Bump the plugin version, commit, and tag for release.

Usage:
    python bump_version.py patch       # 0.1.0 → 0.1.1
    python bump_version.py minor       # 0.1.0 → 0.2.0
    python bump_version.py major       # 0.1.0 → 1.0.0
    python bump_version.py --dry-run patch

Pushes nothing — run `git push && git push --tags` yourself to
trigger the release workflow.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

INIT_FILE = Path(__file__).parent / "calibre_plugin" / "__init__.py"
PYPROJECT_FILE = Path(__file__).parent / "pyproject.toml"
VERSION_RE = re.compile(r"^(\s*version\s*=\s*)\((\d+),\s*(\d+),\s*(\d+)\)", re.MULTILINE)
PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*)"(\d+\.\d+\.\d+)"', re.MULTILINE)


def read_version(text: str) -> tuple[int, int, int]:
    m = VERSION_RE.search(text)
    if not m:
        sys.exit(f"ERROR: Could not find version tuple in {INIT_FILE}")
    return int(m.group(2)), int(m.group(3)), int(m.group(4))


def bump(version: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    if part == "patch":
        return major, minor, patch + 1
    sys.exit(f"ERROR: Unknown part {part!r}. Choose major, minor, or patch.")


def write_version(text: str, new: tuple[int, int, int]) -> str:
    replacement = r"\g<1>({}, {}, {})".format(*new)
    result, n = VERSION_RE.subn(replacement, text)
    if n != 1:
        sys.exit("ERROR: Expected exactly one version match in __init__.py")
    return result


def git(*args, dry_run: bool = False) -> None:
    cmd = ["git", *args]
    print("  $", " ".join(cmd))
    if not dry_run:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            sys.exit(f"ERROR: git command failed:\n{result.stderr.strip()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("part", choices=["major", "minor", "patch"])
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making any changes")
    args = parser.parse_args()

    # Safety check: no uncommitted changes to versioned files
    versioned = [str(INIT_FILE), str(PYPROJECT_FILE)]
    dirty = subprocess.run(
        ["git", "status", "--porcelain", *versioned],
        capture_output=True, text=True
    ).stdout.strip()
    if dirty and not args.dry_run:
        sys.exit("ERROR: versioned files have uncommitted changes. Commit or stash first.")

    text = INIT_FILE.read_text()
    old = read_version(text)
    new = bump(old, args.part)
    old_str = "{}.{}.{}".format(*old)
    new_str = "{}.{}.{}".format(*new)
    tag = f"v{new_str}"

    print(f"\nBumping {args.part}: {old_str} → {new_str}  (tag: {tag})")
    if args.dry_run:
        print("\n[dry run — no changes made]")
        return

    INIT_FILE.write_text(write_version(text, new))
    print(f"Updated {INIT_FILE}")

    pyproject_text = PYPROJECT_FILE.read_text()
    pyproject_new, n = PYPROJECT_VERSION_RE.subn(rf'\g<1>"{new_str}"', pyproject_text)
    if n != 1:
        sys.exit("ERROR: Expected exactly one version match in pyproject.toml")
    PYPROJECT_FILE.write_text(pyproject_new)
    print(f"Updated {PYPROJECT_FILE}")

    print("\nCommitting and tagging:")
    git("add", str(INIT_FILE), str(PYPROJECT_FILE))
    git("commit", "-m", f"Bump version to {new_str}")
    git("tag", "-a", tag, "-m", f"Release {tag}")

    print(f"""
Done.  Next steps:
  git push && git push --tags

Pushing the tag triggers the release workflow, which will:
  1. Run the test suite
  2. Build dist/import_recipe.zip
  3. Create a GitHub Release with the zip attached
""")


if __name__ == "__main__":
    main()
