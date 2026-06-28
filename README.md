# Import Recipe — Calibre Plugin

Adds an **Import Recipe** toolbar button to Calibre. Click it, paste one or
more recipe blog URLs, and each recipe is fetched, stripped of ads and clutter,
converted to a clean EPUB, and added to your library — ready to send to your
e-reader.

## How it works

```
URL ──urllib──▶ raw HTML
             ──JSON-LD extractor──▶ Schema.org Recipe object  ─┐
             ──microdata extractor──▶ Schema.org Recipe object ─┤──▶ recipe.html
             ──(manual entry dialog if incomplete)─────────────┘      │
                                                                 ebook-convert
                                                                       │
                                                                 library entry
```

Extraction tries Schema.org structured data in two formats:

1. **JSON-LD** (`<script type="application/ld+json">`) — used by most modern recipe sites
2. **Microdata** (`itemscope`/`itemprop`) — used by WordPress Jetpack and others;
   also detects the hRecipe `e-instructions` class for sites that omit `itemprop`
   on their directions block

If neither format is found, or if ingredients or instructions are empty after
extraction, a **manual entry dialog** opens pre-filled with whatever metadata
(title, description, cover image) could be pulled from the page's Open Graph
tags.

## Requirements

- **Calibre 5+** (the plugin uses the new-API db and PyQt5)
- `ebook-convert` on your PATH (bundled with every Calibre install)
- Internet access from the machine running Calibre (to fetch pages and cover images)

## Installation

1. Build the plugin zip:
   ```
   python build.py
   ```
   This creates `dist/import_recipe.zip`.

2. In Calibre: **Preferences → Plugins → Load plugin from file**,
   select `dist/import_recipe.zip`, click **Yes** on the security prompt.

3. Restart Calibre.

4. Right-click the toolbar → **Customize toolbar** → drag
   **Import Recipe** from the available actions into the toolbar.

## Usage

1. Click **Import Recipe** in the toolbar.
2. Paste a recipe URL into the first text field. Click **+ Add URL** for
   additional recipes.
3. Choose your duplicate policy (ask / skip / replace).
4. Click **Import**. A **preview dialog** appears for each recipe showing the
   rendered title, metadata, ingredients, and instructions — confirm or cancel
   before it's added to the library.
5. If no structured data is found, or if ingredients or instructions are
   missing, a **manual entry dialog** opens instead. It is pre-filled with
   the page title and any fields that were extracted; paste the missing text
   (one item per line) and click **Import**.
6. New books appear in your library immediately after import.

## What gets imported

| Field | Source |
|---|---|
| Title | `name` from structured data |
| Author | Configurable default (see Preferences) |
| Tags | `recipeCategory`, `recipeCuisine`, `keywords` |
| Comments | `description` + source URL |
| Cover | `image` (downloaded; shown as Calibre thumbnail only, not in book body) |
| Ingredients | `recipeIngredient` |
| Instructions | `recipeInstructions` / `e-instructions` block / post-recipe paragraphs |

## Configuration

Go to **Preferences → Plugins**, find **Import Recipe**, and click
**Customize plugin**.

| Setting | Default | Description |
|---|---|---|
| Default author | `Recipes` | Author applied to every imported book, regardless of what the recipe page lists |

## Limitations

- Sites that require JavaScript execution (Cloudflare bot challenges, Vercel
  security checkpoints) cannot be fetched. The error message will describe the
  HTTP status, and the manual entry dialog will open so you can paste the recipe
  text yourself.
- The plugin does not bypass paywalls or login walls; it behaves like a normal
  browser request.
- Some sites block `urllib` requests by user-agent. The plugin sends a standard
  Chrome user-agent string but cannot run JavaScript.

## Development

All plugin source lives in `calibre_plugin/`. Tests live in `tests/`.

```bash
python -m pytest tests/ -q   # run the test suite
python build.py              # build dist/import_recipe.zip for release
```

On macOS with Calibre installed in `/Applications`:

```bash
make reload   # install plugin, kill Calibre, relaunch
make test     # run the test suite
make dist     # build the release zip
```

`make reload` uses `calibre-customize -b calibre_plugin` (no zip needed), then
kills and restarts the app.

### Previewing extraction without Calibre

`preview_recipe.py` runs the same extraction and rendering code as the plugin
and writes the result to a local HTML file — no Calibre installation required:

```bash
python preview_recipe.py https://example.com/chocolate-cake
open recipe.html          # macOS
```

Use this to quickly check whether a site's structured data is readable before
importing, or to inspect the rendered layout.
