"""
Import Recipe — Calibre Interface Action Plugin
================================================
Adds a toolbar button that opens a dialog for importing food recipes
from web pages (via their Schema.org JSON-LD structured data) directly
into your Calibre library as clean EPUB files.
"""

from calibre.gui2.actions import InterfaceAction


class ImportRecipeAction(InterfaceAction):
    name = "Import Recipe"
    # (label, icon resource, tooltip, keyboard shortcut)
    action_spec = (
        "Import Recipe",
        "add_book.png",
        "Import a food recipe from a URL into your Calibre library",
        None,
    )
    # Show in the toolbar by default
    action_add_menu = False
    dont_add_to = frozenset()
    popup_type = 0  # QToolButton::InstantPopup

    def genesis(self):
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.import_recipe.dialog import ImportRecipesDialog
        d = ImportRecipesDialog(self.gui, self.gui.current_db)
        d.exec_()
