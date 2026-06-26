"""
Make the calibre_plugin package importable without a Calibre installation
by stubbing out the calibre.* imports that only __init__.py needs.
recipe_extract and html_template are pure stdlib and need no stubs.
"""
import sys
import types


def _make_stub(*path_parts):
    """Create a chain of stub modules so `from a.b import C` doesn't fail."""
    full = ""
    for part in path_parts:
        full = f"{full}.{part}" if full else part
        if full not in sys.modules:
            sys.modules[full] = types.ModuleType(full)


# Only needed if tests ever import __init__; kept here for safety.
_make_stub("calibre")
_make_stub("calibre", "gui2")
_make_stub("calibre", "gui2", "actions")
sys.modules["calibre.gui2.actions"].InterfaceAction = object
