"""
Fetch a web page and extract a Schema.org Recipe object from its JSON-LD blocks.
No external dependencies — uses only Python stdlib.
"""

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional


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


def _find_recipe_in_obj(obj) -> Optional[dict]:
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


def extract_recipe_jsonld(html: str) -> Optional[dict]:
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


def _duration_minutes(iso: str) -> Optional[int]:
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
    for field in ("recipeCategory", "recipeCuisine"):
        v = raw.get(field)
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


def scrape(url: str) -> Recipe:
    """Fetch *url* and return a Recipe, or raise RecipeExtractionError."""
    html = fetch_html(url)
    raw = extract_recipe_jsonld(html)
    if raw is None:
        raise RecipeExtractionError(
            f"No Schema.org Recipe found in the page at {url}.\n"
            "The site may not embed structured data, or may block automated fetching."
        )
    return Recipe.from_jsonld(raw, url)
