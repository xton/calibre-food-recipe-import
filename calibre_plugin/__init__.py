"""
Import Recipe — Calibre Interface Action Plugin
================================================
Adds a toolbar button that opens a dialog for importing food recipes
from web pages (via their Schema.org JSON-LD structured data) directly
into your Calibre library as clean EPUB files.

This file is the InterfaceActionBase wrapper. It is intentionally
free of GUI imports so that Calibre's CLI tools (calibredb, etc.) can
read plugin metadata without loading PyQt5. The real InterfaceAction
lives in action.py and is referenced via actual_plugin below.
"""

from calibre.customize import InterfaceActionBase


class ImportRecipeBase(InterfaceActionBase):
    name = "Import Recipe"
    description = (
        "Import food recipes from web pages into your Calibre library as clean EPUBs. "
        "Reads Schema.org Recipe JSON-LD structured data embedded in recipe blog pages."
    )
    author = "calibre-food-recipe-import contributors"
    version = (0, 1, 0)
    minimum_calibre_version = (5, 0, 0)
    supported_platforms = ["windows", "osx", "linux"]

    #: Pointer to the real InterfaceAction — loaded only in a GUI context.
    actual_plugin = "calibre_plugins.import_recipe.action:ImportRecipeAction"

    def is_customizable(self):
        return False
