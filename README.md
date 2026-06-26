# Import Recipe — Calibre Plugin

Adds an **Import Recipe** toolbar button to Calibre. Click it, paste one or
more recipe blog URLs, and each recipe is fetched, stripped of ads and clutter,
converted to a clean EPUB, and added to your library — ready to send to your
e-reader.

## How it works

```
URL ──urllib──▶ raw HTML
             ──JSON-LD extractor──▶ Schema.org Recipe object
             ──HTML renderer──▶ recipe.html  (ingredients aside + numbered steps)
             ──ebook-convert──▶ recipe.epub
             ──Calibre internal API──▶ library entry
```

Extraction reads the `application/ld+json` structured-data block that most
modern recipe blogs embed (Schema.org `Recipe` type). Sites that don't publish
structured data will produce a clear error message rather than silently adding
a blank book.

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
4. Click **Import**. Progress is shown in the log area.
5. New books appear in your library immediately after import.

## What gets imported

| Field | Source |
|---|---|
| Title | `name` |
| Author | `author.name` |
| Tags | `recipeCategory`, `recipeCuisine`, `keywords` |
| Comments | `description` + source URL |
| Cover | `image` (downloaded) |
| Ingredients | `recipeIngredient` |
| Instructions | `recipeInstructions` |

## Limitations

- Sites that don't embed Schema.org `Recipe` JSON-LD will fail gracefully with
  an error message.
- Some sites block automated fetching (Cloudflare, login walls). The error
  message will describe the HTTP status.
- The plugin does not bypass paywalls or bot-detection; it behaves like a
  normal browser request.

## Development

All plugin source lives in `calibre_plugin/`. Run `python build.py` to repack
the zip after any change, then reinstall via Preferences → Plugins.
