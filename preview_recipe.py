#!/usr/bin/env python3
"""
Fetch a recipe URL and write the rendered HTML to a file.

Exercises the same extraction + rendering code the Calibre plugin uses,
so you can inspect what the EPUB will look like before importing it.

Usage:
    python preview_recipe.py <URL> [-o OUTPUT]

Examples:
    python preview_recipe.py https://example.com/chocolate-cake
    python preview_recipe.py https://example.com/cookies -o cookies.html
    open recipe.html          # macOS
    xdg-open recipe.html      # Linux
"""

import argparse
import importlib.util
import pathlib
import sys

_HERE = pathlib.Path(__file__).parent
_PLUGIN = _HERE / "calibre_plugin"


def _load(name: str):
    """Load a plugin module directly by file, bypassing calibre_plugin/__init__.py."""
    full_name = f"calibre_plugin.{name}"
    spec = importlib.util.spec_from_file_location(full_name, _PLUGIN / f"{name}.py",
                                                  submodule_search_locations=[])
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "calibre_plugin"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_extract = _load("recipe_extract")
_tmpl = _load("html_template")

scrape = _extract.scrape
RecipeExtractionError = _extract.RecipeExtractionError
render_html = _tmpl.render_html


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="Recipe page URL")
    parser.add_argument(
        "-o", "--output",
        default="recipe.html",
        metavar="FILE",
        help="Output file (default: recipe.html)",
    )
    args = parser.parse_args()

    print(f"Fetching {args.url} …")
    try:
        recipe = scrape(args.url)
    except RecipeExtractionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    html = render_html(recipe)
    out = pathlib.Path(args.output)
    out.write_text(html, encoding="utf-8")

    print(f"Title:       {recipe.title}")
    print(f"Author:      {recipe.author or '—'}")
    print(f"Prep:        {recipe.prep_time or '—'}")
    print(f"Cook:        {recipe.cook_time or '—'}")
    print(f"Total:       {recipe.total_time or '—'}")
    print(f"Yield:       {recipe.yields or '—'}")
    print(f"Tags:        {', '.join(recipe.tags) or '—'}")
    print(f"Ingredients: {len(recipe.ingredients)}")
    print(f"Steps:       {len(recipe.instructions)}")
    print(f"\nWrote {len(html):,} bytes → {out}")


if __name__ == "__main__":
    main()
