"""
ImportRecipesDialog — the main UI shown when the toolbar button is clicked.
"""

from PyQt5.Qt import (
    QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
    QSizePolicy, QTextEdit, QThread, QVBoxLayout, QWidget,
    Qt, pyqtSlot,
)

from calibre.gui2 import error_dialog, info_dialog, question_dialog, warning_dialog

from .importer import RecipeImporter, ImportResult


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
        from PyQt5.Qt import QComboBox
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

        self._thread.start()

    @pyqtSlot(str)
    def _on_ask_duplicate(self, title: str):
        from PyQt5.Qt import QMessageBox
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
            self._log_msg(f"✗ FAILED — {result.url}\n  {result.error}\n")
        elif result.skipped:
            self._log_msg(f"— SKIPPED (duplicate) — {result.recipe.title}\n")
        else:
            self._log_msg(f"✓ Added: {result.recipe.title} (id {result.book_id})\n")
            # Refresh Calibre's book list
            try:
                self.gui.current_db.refresh()
                self.gui.iactions['Edit Metadata'].refresh_books_after_edit(
                    {result.book_id}
                )
            except Exception:
                pass  # refresh is best-effort

    @pyqtSlot()
    def _on_finished(self):
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._import_btn.setEnabled(True)
        self._log_msg("\nDone.")
        # Trigger a full GUI refresh so new books appear immediately
        try:
            self.gui.tags_view.recount()
            self.gui.library_view.model().refresh()
        except Exception:
            pass

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
