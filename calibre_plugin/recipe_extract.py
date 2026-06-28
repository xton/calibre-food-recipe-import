"""
Fetch a web page and extract a Schema.org Recipe object from its JSON-LD blocks.
No external dependencies — uses only Python stdlib.
"""

import html as _html
import json
import re
import urllib.parse
import urllib.request
import urllib.error
from dataclasses import dataclass, field, replace as _replace
from html.parser import HTMLParser as _HTMLParser


_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class RecipeExtractionError(Exception):
    pass


def fetch_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            charset = "utf-8"
            ct = resp.headers.get_content_charset()
            if ct:
                charset = ct
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise RecipeExtractionError(f"HTTP {exc.code} fetching {url}") from exc
    except urllib.error.URLError as exc:
        raise RecipeExtractionError(f"Network error fetching {url}: {exc.reason}") from exc


def _find_recipe_in_obj(obj) -> dict | None:
    """Recursively search a decoded JSON object for a Recipe @type node."""
    if isinstance(obj, dict):
        t = obj.get("@type", "")
        # @type can be a string or a list
        types = t if isinstance(t, list) else [t]
        if any(str(x).lower() == "recipe" for x in types):
            return obj
        # Recurse into every value; this naturally covers @graph arrays,
        # mainEntity, and any other nested structure.
        for v in obj.values():
            result = _find_recipe_in_obj(v)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_recipe_in_obj(item)
            if result:
                return result
    return None


def extract_recipe_jsonld(html: str) -> dict | None:
    """Return the first Schema.org Recipe dict found in JSON-LD blocks, or None."""
    for match in _JSONLD_RE.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        recipe = _find_recipe_in_obj(data)
        if recipe:
            return recipe
    return None


class _MicrodataParser(_HTMLParser):
    """Extract Schema.org Recipe microdata (itemprop/itemscope) from HTML."""

    _VOID_TAGS = frozenset({
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    })
    _LIST_PROPS = frozenset({"recipeIngredient", "recipeInstructions", "recipeCategory", "recipeCuisine"})
    # Block-level tags that signal "we've left the instruction zone" in post-recipe mode
    _STOP_TAGS = frozenset({"div", "section", "article", "aside", "nav",
                            "h1", "h2", "h3", "h4", "h5", "h6"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._in_recipe = False
        self._recipe_depth = 0
        self._depth = 0
        self._current_prop: str | None = None
        self._prop_depth = 0
        self._text_buf: list[str] = []
        self._data: dict = {}
        # hRecipe e-instructions block (Jetpack uses this without itemprop)
        self._in_instructions_block = False
        self._instructions_div_depth = 0   # count of open divs inside the block
        self._instructions_buf: list[str] = []
        self._instructions_paragraphs: list[str] = []
        # Post-recipe paragraph collection (fallback for sites that put
        # instructions in the blog body rather than in microdata)
        self._post_recipe = False
        self._post_buf: list[str] = []
        self._post_paragraphs: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._post_recipe:
            if tag == "p":
                self._flush_post_buf()
            elif tag in self._STOP_TAGS:
                self._flush_post_buf()
                self._post_recipe = False
            # Don't track depth in post-recipe mode
            return

        attrs = dict(attrs)
        self._depth += 1

        if not self._in_recipe:
            if "schema.org/recipe" in attrs.get("itemtype", "").lower():
                self._in_recipe = True
                self._recipe_depth = self._depth
        else:
            classes = attrs.get("class", "").split()
            if "e-instructions" in classes and not self._in_instructions_block:
                # hRecipe instructions block — collect paragraphs as separate steps
                self._in_instructions_block = True
                self._instructions_div_depth = 1
            elif self._in_instructions_block:
                if tag == "div":
                    self._instructions_div_depth += 1
                elif tag == "p":
                    self._flush_instructions_buf()
            else:
                itemprop = attrs.get("itemprop")
                if itemprop and self._current_prop is None:
                    self._current_prop = itemprop
                    self._prop_depth = self._depth
                    self._text_buf = []
                    # Capture attribute-based values immediately (no text content needed)
                    if tag == "time":
                        dt = attrs.get("datetime", "").strip()
                        if dt:
                            self._store(itemprop, dt)
                            self._current_prop = None
                    elif tag == "img":
                        src = attrs.get("src", "").strip()
                        if src:
                            self._store(itemprop, src)
                            self._current_prop = None
                    elif tag == "meta":
                        content = attrs.get("content", "").strip()
                        if content:
                            self._store(itemprop, content)
                            self._current_prop = None

        if tag in self._VOID_TAGS:
            self._depth -= 1

    def handle_endtag(self, tag):
        if self._post_recipe:
            if tag == "p":
                self._flush_post_buf()
            return

        if not self._in_recipe:
            return

        if self._in_instructions_block:
            if tag == "div":
                self._instructions_div_depth -= 1
                if self._instructions_div_depth == 0:
                    self._flush_instructions_buf()
                    self._in_instructions_block = False
            elif tag == "p":
                self._flush_instructions_buf()

        if self._depth == self._recipe_depth:
            self._in_recipe = False
            self._post_recipe = True  # start collecting post-recipe paragraphs
        if self._current_prop is not None and self._depth <= self._prop_depth:
            text = "".join(self._text_buf).strip()
            if text:
                self._store(self._current_prop, text)
            self._current_prop = None
            self._text_buf = []
        self._depth -= 1

    def handle_data(self, data):
        if self._post_recipe:
            self._post_buf.append(data)
            return
        if self._in_recipe and self._in_instructions_block and self._current_prop is None:
            self._instructions_buf.append(data)
            return
        if self._in_recipe and self._current_prop is not None:
            self._text_buf.append(data)

    def _flush_instructions_buf(self) -> None:
        text = "".join(self._instructions_buf).strip()
        if text:
            self._instructions_paragraphs.append(text)
        self._instructions_buf = []

    def _flush_post_buf(self) -> None:
        text = "".join(self._post_buf).strip()
        if text:
            self._post_paragraphs.append(text)
        self._post_buf = []

    def _store(self, prop: str, value: str) -> None:
        if prop in self._LIST_PROPS:
            self._data.setdefault(prop, []).append(value)
        elif prop not in self._data:
            self._data[prop] = value

    def get_result(self) -> dict | None:
        if not self._data.get("name"):
            return None
        if self._data.get("recipeInstructions"):
            return self._data
        result = dict(self._data)
        instructions = self._instructions_paragraphs or self._post_paragraphs
        if instructions:
            result["recipeInstructions"] = list(instructions)
        return result


def extract_recipe_microdata(html: str) -> dict | None:
    """Return the first Schema.org Recipe found as microdata, or None."""
    parser = _MicrodataParser()
    parser.feed(html)
    return parser.get_result()


def _first(value):
    """Unwrap a list to its first element (None if empty); pass non-lists through."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _scalar(value) -> str:
    """Flatten a string-or-list to a single string."""
    value = _first(value)
    return str(value) if value is not None else ""


def _list_of_strings(value) -> list[str]:
    """Normalise a value that may be a string, list of strings, or list of objects."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    result.append(item.strip())
            elif isinstance(item, dict):
                # HowToStep etc.
                text = item.get("text") or item.get("name") or ""
                if text.strip():
                    result.append(text.strip())
        return result
    return [str(value)]


def _image_url(value) -> str:
    """Extract image URL from Schema.org ImageObject or plain string."""
    value = _first(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url") or value.get("contentUrl") or ""
    return ""


def _duration_minutes(iso: str) -> int | None:
    """Parse ISO 8601 duration (PT1H30M) to total minutes, or None."""
    if not iso:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso, re.IGNORECASE)
    if not m:
        return None
    hours = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    total = hours * 60 + mins
    # Treat a zero/sub-minute duration as "no meaningful total time".
    return total if total > 0 else None


def _format_duration(iso: str) -> str:
    mins = _duration_minutes(iso)
    if mins is None:
        return ""
    if mins < 60:
        return f"{mins} min"
    h, m = divmod(mins, 60)
    return f"{h} hr {m} min" if m else f"{h} hr"


def _author_name(value) -> str:
    value = _first(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("name") or ""
    return ""


def _tags_from_recipe(raw: dict) -> list[str]:
    """Collect tags from recipeCategory, recipeCuisine, keywords."""
    tags = []
    for key in ("recipeCategory", "recipeCuisine"):
        v = raw.get(key)
        if isinstance(v, list):
            tags.extend(str(x).strip() for x in v if str(x).strip())
        elif isinstance(v, str) and v.strip():
            # may be comma-separated
            tags.extend(p.strip() for p in v.split(",") if p.strip())
    kw = raw.get("keywords")
    if isinstance(kw, str):
        tags.extend(p.strip() for p in kw.split(",") if p.strip())
    elif isinstance(kw, list):
        tags.extend(str(x).strip() for x in kw if str(x).strip())
    # deduplicate, preserve order
    seen = set()
    result = []
    for t in tags:
        tl = t.lower()
        if tl not in seen:
            seen.add(tl)
            result.append(t)
    return result


@dataclass(frozen=True, repr=False)
class Recipe:
    """Structured recipe data extracted from a Schema.org JSON-LD block.

    Immutable: build one with Recipe.from_jsonld(raw, url), which keeps the
    JSON-LD parsing separate from the plain data container.
    """

    source_url: str
    title: str
    description: str = ""
    author: str = ""
    site_name: str = ""
    image_url: str = ""
    yields: str = ""
    total_time: str = ""
    prep_time: str = ""
    cook_time: str = ""
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_jsonld(cls, raw: dict, source_url: str) -> "Recipe":
        """Build a Recipe from a decoded Schema.org Recipe JSON-LD dict."""
        return cls(
            source_url=source_url,
            title=_scalar(raw.get("name")) or "Untitled Recipe",
            description=_scalar(raw.get("description")),
            author=_author_name(raw.get("author")),
            image_url=_image_url(raw.get("image")),
            yields=_scalar(raw.get("recipeYield")),
            total_time=_format_duration(raw.get("totalTime", "")),
            prep_time=_format_duration(raw.get("prepTime", "")),
            cook_time=_format_duration(raw.get("cookTime", "")),
            ingredients=_list_of_strings(raw.get("recipeIngredient")),
            instructions=_list_of_strings(raw.get("recipeInstructions")),
            tags=_tags_from_recipe(raw),
        )

    def __repr__(self):
        return (
            f"<Recipe title={self.title!r} "
            f"ingredients={len(self.ingredients)} steps={len(self.instructions)}>"
        )


def _recipe_from_microdata(raw: dict, source_url: str) -> "Recipe":
    """Build a Recipe from microdata dict, handling non-ISO duration strings."""
    def _get_time(key: str) -> str:
        v = raw.get(key, "")
        if not v:
            return ""
        formatted = _format_duration(v)
        return formatted if formatted else v

    return Recipe(
        source_url=source_url,
        title=_scalar(raw.get("name")) or "Untitled Recipe",
        description=_scalar(raw.get("description")),
        author=_author_name(raw.get("author")),
        image_url=_image_url(raw.get("image")),
        yields=_scalar(raw.get("recipeYield")),
        total_time=_get_time("totalTime"),
        prep_time=_get_time("prepTime"),
        cook_time=_get_time("cookTime"),
        ingredients=_list_of_strings(raw.get("recipeIngredient")),
        instructions=_list_of_strings(raw.get("recipeInstructions")),
        tags=_tags_from_recipe(raw),
    )


def _site_name(html_text: str, url: str) -> str:
    """Best available site name: og:site_name, then the URL's hostname."""
    og = _og_value(html_text, "site_name")
    if og:
        return og
    host = urllib.parse.urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host


def scrape(url: str) -> Recipe:
    """Fetch *url* and return a Recipe, or raise RecipeExtractionError."""
    html_text = fetch_html(url)
    site = _site_name(html_text, url)
    raw = extract_recipe_jsonld(html_text)
    if raw is not None:
        return _replace(Recipe.from_jsonld(raw, url), site_name=site)
    raw = extract_recipe_microdata(html_text)
    if raw is not None:
        return _replace(_recipe_from_microdata(raw, url), site_name=site)
    raise RecipeExtractionError(
        f"No Schema.org Recipe found in the page at {url}.\n"
        "The site may not embed structured data, or may block automated fetching."
    )


def _og_value(html_text: str, name: str) -> str:
    """Extract content from <meta property="og:NAME" content="...">."""
    escaped = re.escape(name)
    for pat in (
        rf'property=["\']og:{escaped}["\'][^>]+content=["\']([^"\']*)["\']',
        rf'content=["\']([^"\']*)["\'][^>]+property=["\']og:{escaped}["\']',
    ):
        m = re.search(pat, html_text, re.IGNORECASE)
        if m:
            return _html.unescape(m.group(1))
    return ""


def _page_title(html_text: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.DOTALL | re.IGNORECASE)
    return _html.unescape(m.group(1)).strip() if m else ""


def scrape_partial(url: str) -> Recipe:
    """Fetch *url* and return whatever page metadata is available.

    Returns a Recipe with empty ingredients and instructions — intended as
    pre-fill data for the manual-entry dialog when no structured data is found.
    Never raises RecipeExtractionError; falls back to a bare Recipe on error.
    """
    try:
        html_text = fetch_html(url)
    except RecipeExtractionError:
        return Recipe(source_url=url, title=url)
    title = _og_value(html_text, "title") or _page_title(html_text) or url
    description = _og_value(html_text, "description") or ""
    image_url = _og_value(html_text, "image") or ""
    site = _site_name(html_text, url)
    return Recipe(source_url=url, title=title, description=description,
                  image_url=image_url, site_name=site)
