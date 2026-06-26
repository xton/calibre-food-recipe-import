"""
Core import logic: recipe → HTML → EPUB → Calibre library entry.
Runs in a worker thread; communicates back via Qt signals.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass

from PyQt5.Qt import QMutex, QMutexLocker, QObject, QWaitCondition, pyqtSignal

from calibre.ebooks.metadata.book.base import Metadata

from .config import prefs
from .recipe_extract import Recipe, RecipeExtractionError, scrape
from .html_template import render_html


@dataclass
class ImportResult:
    url: str
    recipe: Recipe | None = None
    book_id: int | None = None
    error: str | None = None         # set if the import failed
    skipped: bool = False            # True if user chose skip on duplicate
    preview_cancelled: bool = False  # True if user cancelled at the preview step


class RecipeImporter(QObject):
    """
    Worker object moved to a QThread.  Emits progress and per-URL results.
    For duplicate_policy='ask', emits ask_duplicate and blocks until
    the main thread calls answer_duplicate().
    """
    progress = pyqtSignal(str)
    result = pyqtSignal(object)          # ImportResult
    finished = pyqtSignal()
    # Emitted when a duplicate is found and policy=='ask'.
    # Payload: recipe title (str).  Main thread must call answer_duplicate().
    ask_duplicate = pyqtSignal(str)
    # Emitted after scraping, before converting.
    # Payload: Recipe object.  Main thread must call answer_preview().
    preview_recipe = pyqtSignal(object)

    def __init__(self, urls: list[str], db, duplicate_policy: str):
        """
        duplicate_policy: 'ask' | 'replace' | 'skip'
        db: calibre GUI db  (gui.current_db — we call .new_api internally)
        """
        super().__init__()
        self.urls = urls
        self.db = db.new_api
        self.duplicate_policy = duplicate_policy
        self._cancelled = False

        # Cross-thread synchronisation for the 'ask' policy
        self._mutex = QMutex()
        self._wait = QWaitCondition()
        self._dup_answer: str | None = None   # 'replace' or 'skip'
        self._preview_answer: bool | None = None  # True = confirmed, False = cancelled

    def cancel(self):
        self._cancelled = True
        # Unblock any waiting ask_duplicate or preview
        with QMutexLocker(self._mutex):
            self._dup_answer = "skip"
            self._preview_answer = False
            self._wait.wakeAll()

    def answer_duplicate(self, answer: str):
        """Called from the main thread after ask_duplicate is emitted."""
        with QMutexLocker(self._mutex):
            self._dup_answer = answer
            self._wait.wakeAll()

    def answer_preview(self, confirmed: bool):
        """Called from the main thread after preview_recipe is emitted."""
        with QMutexLocker(self._mutex):
            self._preview_answer = confirmed
            self._wait.wakeAll()

    def run(self):
        for url in self.urls:
            if self._cancelled:
                break
            self.progress.emit(f"Fetching {url} …")
            result = self._import_one(url)
            self.result.emit(result)
        self.finished.emit()

    # ------------------------------------------------------------------
    def _import_one(self, url: str) -> ImportResult:
        try:
            self.progress.emit(f"Extracting recipe from {url} …")
            recipe = scrape(url)
        except RecipeExtractionError as exc:
            return ImportResult(url, error=str(exc))
        except Exception as exc:
            return ImportResult(url, error=f"Unexpected error: {exc}")

        self.progress.emit(f"Previewing '{recipe.title}' — waiting for confirmation …")
        if not self._show_preview(recipe):
            return ImportResult(url, recipe=recipe, skipped=True, preview_cancelled=True)

        # Check for an existing entry with the same title.
        existing_ids = set(self.db.search(f'title:"={recipe.title}"'))
        if existing_ids:
            action = self._resolve_duplicate(recipe.title)
            if action == "skip":
                return ImportResult(url, recipe=recipe, skipped=True)
            if action == "replace":
                self.db.remove_books(existing_ids)

        try:
            book_id = self._convert_and_add(recipe)
        except Exception as exc:
            return ImportResult(url, recipe=recipe, error=str(exc))

        return ImportResult(url, recipe=recipe, book_id=book_id)

    def _resolve_duplicate(self, title: str) -> str:
        """Decide how to handle an existing recipe: returns 'skip' or 'replace'."""
        if self.duplicate_policy == "ask":
            return self._ask_user(title)
        return self.duplicate_policy   # already 'skip' or 'replace'

    def _ask_user(self, title: str) -> str:
        """Block the worker thread until the main thread answers."""
        with QMutexLocker(self._mutex):
            self._dup_answer = None
            self.ask_duplicate.emit(title)
            while self._dup_answer is None:
                self._wait.wait(self._mutex)
            return self._dup_answer

    def _show_preview(self, recipe: Recipe) -> bool:
        """Block the worker thread until the user confirms or cancels the preview."""
        with QMutexLocker(self._mutex):
            self._preview_answer = None
            self.preview_recipe.emit(recipe)
            while self._preview_answer is None:
                self._wait.wait(self._mutex)
            return self._preview_answer

    @staticmethod
    def _find_ebook_convert() -> str:
        """Locate ebook-convert: PATH first, then beside sys.executable (Calibre app bundle)."""
        found = shutil.which("ebook-convert")
        if found:
            return found
        candidate = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "ebook-convert")
        if os.path.isfile(candidate):
            return candidate
        return "ebook-convert"  # let subprocess raise a clear error

    def _convert_and_add(self, recipe: Recipe) -> int:
        with tempfile.TemporaryDirectory(prefix="calibre_recipe_") as tmpdir:
            html_path = os.path.join(tmpdir, "recipe.html")
            epub_path = os.path.join(tmpdir, "recipe.epub")

            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(render_html(recipe))

            # Download cover image if available
            cover_path = None
            if recipe.image_url:
                try:
                    cover_path = os.path.join(tmpdir, "cover.jpg")
                    req = urllib.request.Request(
                        recipe.image_url,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        with open(cover_path, "wb") as fh:
                            fh.write(resp.read())
                except Exception:
                    cover_path = None

            # ebook-convert: HTML → EPUB
            cmd = [
                self._find_ebook_convert(),
                html_path,
                epub_path,
                "--title", recipe.title,
                "--no-default-epub-cover",
            ]
            if recipe.author:
                cmd += ["--authors", recipe.author]
            if cover_path:
                cmd += ["--cover", cover_path]

            self.progress.emit(f"Converting '{recipe.title}' to EPUB …")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"ebook-convert failed (exit {proc.returncode}):\n{proc.stderr[-1000:]}"
                )
            if not os.path.exists(epub_path):
                raise RuntimeError("ebook-convert produced no output file.")

            # Build Calibre Metadata
            mi = Metadata(recipe.title)
            mi.authors = [recipe.author or prefs['default_author']]
            if recipe.tags:
                mi.tags = recipe.tags
            comments = f'<p>Source: <a href="{recipe.source_url}">{recipe.source_url}</a></p>'
            if recipe.description:
                comments = f"<p>{recipe.description}</p>" + comments
            mi.comments = comments

            self.progress.emit(f"Adding '{recipe.title}' to library …")
            book_id = self.db.create_book_entry(mi)
            with open(epub_path, "rb") as fh:
                self.db.add_format(book_id, "EPUB", fh)

            if cover_path:
                with open(cover_path, "rb") as fh:
                    self.db.set_cover({book_id: fh.read()})

            return book_id
