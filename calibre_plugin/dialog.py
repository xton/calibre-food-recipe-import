"""
ImportRecipesDialog — the main UI shown when the toolbar button is clicked.
"""

from PyQt5.Qt import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QTextBrowser, QTextEdit, QThread, QVBoxLayout, QWidget, Qt, pyqtSlot,
)

from calibre.gui2 import error_dialog, warning_dialog

from .html_template import render_html
from .importer import RecipeImporter, ImportResult
from .recipe_extract import Recipe


class RecipePreviewDialog(QDialog):
    """Shows the rendered recipe HTML and lets the user confirm or cancel."""

    def __init__(self, recipe, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview: {recipe.title}")
        self.setMinimumSize(680, 560)

        layout = QVBoxLayout(self)

        label = QLabel("Review the recipe below, then choose <b>Import</b> to add it to your library or <b>Cancel</b> to skip it.")
        label.setWordWrap(True)
        layout.addWidget(label)

        browser = QTextBrowser()
        browser.setHtml(render_html(recipe))
        browser.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(browser)

        btn_box = QDialogButtonBox()
        import_btn = btn_box.addButton("Import", QDialogButtonBox.AcceptRole)
        cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        import_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(btn_box)


class ManualEntryDialog(QDialog):
    """Shown when no structured recipe data is found on the page.
    Pre-filled with whatever OG metadata could be extracted.
    """

    def __init__(self, partial: Recipe, parent=None):
        super().__init__(parent)
        self._partial = partial
        self._recipe: Recipe | None = None

        self.setWindowTitle("Manual Recipe Entry")
        self.setMinimumSize(660, 520)

        layout = QVBoxLayout(self)

        info = QLabel(
            "No structured recipe data was found on this page. "
            "Paste the ingredients and instructions below to import it manually."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()
        self._title_edit = QLineEdit(partial.title)
        form.addRow("Title:", self._title_edit)
        layout.addLayout(form)

        areas = QHBoxLayout()

        ing_group = QGroupBox("Ingredients (one per line)")
        ing_layout = QVBoxLayout(ing_group)
        self._ing_edit = QTextEdit()
        self._ing_edit.setPlaceholderText("2 cups flour\n1 tsp salt\n…")
        ing_layout.addWidget(self._ing_edit)
        areas.addWidget(ing_group)

        inst_group = QGroupBox("Instructions (one per line)")
        inst_layout = QVBoxLayout(inst_group)
        self._inst_edit = QTextEdit()
        self._inst_edit.setPlaceholderText("Whisk dry ingredients.\nAdd buttermilk and egg.\n…")
        inst_layout.addWidget(self._inst_edit)
        areas.addWidget(inst_group)

        layout.addLayout(areas)

        btn_box = QDialogButtonBox()
        import_btn = btn_box.addButton("Import", QDialogButtonBox.AcceptRole)
        cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        import_btn.clicked.connect(self._on_import)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_import(self):
        import dataclasses
        title = self._title_edit.text().strip() or "Untitled Recipe"
        ingredients = [
            line for line in (l.strip() for l in self._ing_edit.toPlainText().splitlines()) if line
        ]
        instructions = [
            line for line in (l.strip() for l in self._inst_edit.toPlainText().splitlines()) if line
        ]
        self._recipe = dataclasses.replace(
            self._partial,
            title=title,
            ingredients=ingredients,
            instructions=instructions,
        )
        self.accept()

    def get_recipe(self) -> Recipe | None:
        return self._recipe


class _UrlRow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("https://example.com/recipe/…")
        self.edit.setMinimumWidth(440)
        self.remove_btn = QPushButton("✕")
        self.remove_btn.setFixedWidth(28)
        self.remove_btn.setToolTip("Remove this row")
        lay.addWidget(self.edit)
        lay.addWidget(self.remove_btn)


class ImportRecipesDialog(QDialog):
    def __init__(self, gui, db):
        super().__init__(gui)
        self.gui = gui
        self.db = db.new_api
        self._thread = None
        self._worker = None
        self._rows: list[_UrlRow] = []

        self.setWindowTitle("Import Recipe from URL")
        self.setMinimumWidth(560)
        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)

        # --- URL list ---
        url_group = QGroupBox("Recipe URLs")
        url_layout = QVBoxLayout(url_group)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFixedHeight(200)
        self._url_container = QWidget()
        self._url_container_layout = QVBoxLayout(self._url_container)
        self._url_container_layout.setAlignment(Qt.AlignTop)
        self._url_container_layout.setSpacing(0)
        self._scroll_area.setWidget(self._url_container)
        url_layout.addWidget(self._scroll_area)

        add_btn = QPushButton("+ Add URL")
        add_btn.clicked.connect(self._add_row)
        url_layout.addWidget(add_btn, alignment=Qt.AlignLeft)
        root.addWidget(url_group)

        # Add a first row by default
        self._add_row()

        # --- Duplicate policy ---
        dup_group = QGroupBox("If a recipe with the same title already exists")
        dup_layout = QHBoxLayout(dup_group)
        self._dup_combo = QComboBox()
        self._dup_combo.addItem("Ask me each time", "ask")
        self._dup_combo.addItem("Skip (keep existing)", "skip")
        self._dup_combo.addItem("Replace (remove old, add new)", "replace")
        dup_layout.addWidget(self._dup_combo)
        dup_layout.addStretch()
        root.addWidget(dup_group)

        # --- Log ---
        log_group = QGroupBox("Progress")
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFixedHeight(120)
        log_layout.addWidget(self._log)
        root.addWidget(log_group)

        # --- Buttons ---
        btn_box = QDialogButtonBox()
        self._import_btn = btn_box.addButton("Import", QDialogButtonBox.AcceptRole)
        self._import_btn.clicked.connect(self._start_import)
        self._cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.RejectRole)
        self._cancel_btn.clicked.connect(self._on_cancel)
        root.addWidget(btn_box)

    def _add_row(self):
        row = _UrlRow(self._url_container)
        row.remove_btn.clicked.connect(lambda: self._remove_row(row))
        self._url_container_layout.addWidget(row)
        self._rows.append(row)
        row.edit.setFocus()

    def _remove_row(self, row: _UrlRow):
        if len(self._rows) == 1:
            row.edit.clear()
            return
        self._rows.remove(row)
        self._url_container_layout.removeWidget(row)
        row.deleteLater()

    # ------------------------------------------------------------------
    def _log_msg(self, msg: str):
        self._log.append(msg)
        self._log.verticalScrollBar().setValue(self._log.verticalScrollBar().maximum())

    def _start_import(self):
        urls = [r.edit.text().strip() for r in self._rows if r.edit.text().strip()]
        if not urls:
            warning_dialog(
                self, "No URLs", "Please enter at least one recipe URL.", show=True
            )
            return

        # validate loosely
        bad = [u for u in urls if not u.startswith(("http://", "https://"))]
        if bad:
            error_dialog(
                self,
                "Invalid URL",
                "These URLs don't look right (must start with http:// or https://):\n"
                + "\n".join(bad),
                show=True,
            )
            return

        duplicate_policy = self._dup_combo.currentData()
        self._import_btn.setEnabled(False)
        self._had_errors = False
        self._log.clear()
        self._log_msg(f"Starting import of {len(urls)} URL(s) …\n")

        self._worker = RecipeImporter(urls, self.gui.current_db, duplicate_policy)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._log_msg)
        self._worker.result.connect(self._on_result)
        self._worker.finished.connect(self._on_finished)
        self._worker.ask_duplicate.connect(self._on_ask_duplicate)
        self._worker.preview_recipe.connect(self._on_preview_recipe)
        self._worker.manual_entry.connect(self._on_manual_entry)

        self._thread.start()

    @pyqtSlot(object)
    def _on_preview_recipe(self, recipe):
        dlg = RecipePreviewDialog(recipe, parent=self)
        confirmed = dlg.exec_() == QDialog.Accepted
        self._worker.answer_preview(confirmed)

    @pyqtSlot(object)
    def _on_manual_entry(self, partial):
        dlg = ManualEntryDialog(partial, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._worker.answer_manual(dlg.get_recipe())
        else:
            self._worker.answer_manual(None)

    @pyqtSlot(str)
    def _on_ask_duplicate(self, title: str):
        msg = QMessageBox(self)
        msg.setWindowTitle("Duplicate Recipe")
        msg.setText(f"<b>{title}</b> is already in your library.")
        msg.setInformativeText("Do you want to replace the existing entry or skip this recipe?")
        replace_btn = msg.addButton("Replace", QMessageBox.AcceptRole)
        skip_btn = msg.addButton("Skip", QMessageBox.RejectRole)
        msg.setDefaultButton(skip_btn)
        msg.exec_()
        answer = "replace" if msg.clickedButton() is replace_btn else "skip"
        self._worker.answer_duplicate(answer)

    @pyqtSlot(object)
    def _on_result(self, result: ImportResult):
        if result.error:
            self._had_errors = True
            self._log_msg(f"✗ FAILED — {result.url}\n  {result.error}\n")
        elif result.skipped:
            label = "cancelled at preview" if result.preview_cancelled else "duplicate"
            self._log_msg(f"— SKIPPED ({label}) — {result.recipe.title}\n")
        else:
            self._log_msg(f"✓ Added: {result.recipe.title} (id {result.book_id})\n")

    @pyqtSlot()
    def _on_finished(self):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._import_btn.setEnabled(True)
        try:
            self.gui.tags_view.recount()
            self.gui.library_view.model().refresh()
        except Exception:
            pass
        if not self._had_errors:
            self.accept()
        else:
            self._log_msg("\nDone.")

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self._log_msg("Cancelling after current URL …")
        else:
            self.reject()

    def closeEvent(self, event):
        if self._worker:
            self._worker.cancel()
            if self._thread:
                self._thread.quit()
                self._thread.wait()
        super().closeEvent(event)
