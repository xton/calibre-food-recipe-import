from PyQt5.Qt import QFormLayout, QLabel, QLineEdit, QWidget


class ConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        from calibre_plugins.import_recipe.config import prefs

        layout = QFormLayout(self)
        self._author_edit = QLineEdit(prefs['author_override'])
        self._author_edit.setMinimumWidth(200)
        self._author_edit.setPlaceholderText('leave blank to use each recipe\'s own author')
        layout.addRow(QLabel('Author override:'), self._author_edit)

    def commit(self):
        from calibre_plugins.import_recipe.config import prefs
        prefs['author_override'] = self._author_edit.text().strip()
