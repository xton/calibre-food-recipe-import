from PyQt5.Qt import QFormLayout, QLabel, QLineEdit, QWidget


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        from calibre_plugins.import_recipe.config import prefs

        layout = QFormLayout(self)
        self._author_edit = QLineEdit(prefs['default_author'])
        self._author_edit.setMinimumWidth(200)
        layout.addRow(QLabel('Default author for imported recipes:'), self._author_edit)

    def commit(self):
        from calibre_plugins.import_recipe.config import prefs
        value = self._author_edit.text().strip()
        prefs['default_author'] = value if value else 'Recipes'
