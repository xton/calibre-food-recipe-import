"""
The actual InterfaceAction — only loaded in a GUI (PyQt5) context.
Calibre routes here via the actual_plugin pointer in __init__.py.
"""

from calibre.gui2.actions import InterfaceAction


class ImportRecipeAction(InterfaceAction):
    name = "Import Recipe"
    action_spec = (
        "Import Recipe",
        "add_book.png",
        "Import a food recipe from a URL into your Calibre library",
        None,
    )
    action_add_menu = False
    dont_add_to = frozenset()
    popup_type = 0  # QToolButton::InstantPopup

    def genesis(self):
        self.qaction.triggered.connect(self.show_dialog)

    def show_dialog(self):
        from calibre_plugins.import_recipe.dialog import ImportRecipesDialog
        d = ImportRecipesDialog(self.gui, self.gui.current_db)
        d.exec_()
