"""
Core import logic: recipe → HTML → EPUB → Calibre library entry.
Runs in a worker thread; communicates back via Qt signals.
"""

import os
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional

from PyQt5.Qt import QMutex, QMutexLocker, QObject, QWaitCondition, pyqtSignal

from calibre.ebooks.metadata.book.base import Metadata

from .recipe_extract import Recipe, RecipeExtractionError, scrape
from .html_template import render_html


@dataclass
class ImportResult:
    url: str
    recipe: Optional[Recipe] = None
    book_id: Optional[int] = None
    error: Optional[str] = None      # set if the import failed
    skipped: bool = False            # True if user chose skip on duplicate


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

    def cancel(self):
        self._cancelled = True
        # Unblock any waiting ask_duplicate
        with QMutexLocker(self._mutex):
            self._dup_answer = "skip"
            self._wait.wakeAll()

    def answer_duplicate(self, answer: str):
        """Called from the main thread after ask_duplicate is emitted."""
        with QMutexLocker(self._mutex):
            self._dup_answer = answer
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
                "ebook-convert",
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
            if recipe.author:
                mi.set_field("authors", [recipe.author])
            if recipe.tags:
                mi.set_field("tags", recipe.tags)
            comments = f'<p>Source: <a href="{recipe.source_url}">{recipe.source_url}</a></p>'
            if recipe.description:
                comments = f"<p>{recipe.description}</p>" + comments
            mi.set_field("comments", comments)

            self.progress.emit(f"Adding '{recipe.title}' to library …")
            book_id = self.db.create_book_entry(mi)
            with open(epub_path, "rb") as fh:
                self.db.add_format(book_id, "EPUB", fh)

            if cover_path:
                with open(cover_path, "rb") as fh:
                    self.db.set_cover({book_id: fh.read()})

            return book_id
