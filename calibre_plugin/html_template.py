"""
Render a Recipe to a standalone HTML string suitable for ebook-convert input.
Pure stdlib — no Jinja2 dependency.
"""

import html as _html
from .recipe_extract import Recipe


_CSS = """\
body {
    font-family: Georgia, serif;
    font-size: 1em;
    line-height: 1.6;
    max-width: 700px;
    margin: 2em auto;
    padding: 0 1em;
    color: #222;
}
h1 { font-size: 1.8em; margin-bottom: 0.2em; }
.meta { color: #666; font-size: 0.9em; margin-bottom: 1.5em; }
.meta span { margin-right: 1.5em; }
.layout { display: flex; gap: 2em; }
aside {
    min-width: 220px;
    max-width: 260px;
    background: #f8f5f0;
    border-left: 3px solid #c8a96e;
    padding: 1em;
    font-size: 0.92em;
}
aside h2 { font-size: 1em; margin-top: 0; text-transform: uppercase; letter-spacing: 0.05em; }
aside ul { margin: 0; padding-left: 1.2em; }
aside li { margin-bottom: 0.4em; }
main { flex: 1; }
main h2 { font-size: 1em; text-transform: uppercase; letter-spacing: 0.05em; }
ol { padding-left: 1.4em; }
ol li { margin-bottom: 0.8em; }
.source { font-size: 0.8em; color: #888; margin-top: 2em; word-break: break-all; }
@media (max-width: 500px) {
    .layout { flex-direction: column; }
    aside { max-width: 100%; }
}
"""


def _e(text: str) -> str:
    """HTML-escape a string."""
    return _html.escape(str(text))


def _meta_span(label: str, value: str) -> str:
    if not value:
        return ""
    return f'<span><strong>{_e(label)}:</strong> {_e(value)}</span>'


def render_html(recipe: Recipe) -> str:
    meta_parts = [
        _meta_span("Prep", recipe.prep_time),
        _meta_span("Cook", recipe.cook_time),
        _meta_span("Total", recipe.total_time),
        _meta_span("Yield", recipe.yields),
        _meta_span("Author", recipe.author),
    ]
    meta_html = "".join(p for p in meta_parts if p)

    ingredients_html = "\n".join(f"<li>{_e(i)}</li>" for i in recipe.ingredients)

    instructions_html = "\n".join(
        f"<li>{_e(step)}</li>" for step in recipe.instructions
    )

    cover_img = ""
    if recipe.image_url:
        cover_img = f'<img src="{_e(recipe.image_url)}" alt="{_e(recipe.title)}" style="max-width:100%;margin-bottom:1em;" />'

    return f"""\
<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
  <meta charset="utf-8" />
  <title>{_e(recipe.title)}</title>
  <style>{_CSS}</style>
</head>
<body>
  {cover_img}
  <h1>{_e(recipe.title)}</h1>
  <div class="meta">{meta_html}</div>
  <div class="layout">
    <aside>
      <h2>Ingredients</h2>
      <ul>
{ingredients_html}
      </ul>
    </aside>
    <main>
      <h2>Instructions</h2>
      <ol>
{instructions_html}
      </ol>
    </main>
  </div>
  <p class="source">Source: <a href="{_e(recipe.source_url)}">{_e(recipe.source_url)}</a></p>
</body>
</html>
"""
