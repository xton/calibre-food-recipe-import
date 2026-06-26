import re
from dataclasses import replace

import pytest

from calibre_plugin.recipe_extract import Recipe
from calibre_plugin.html_template import render_html


# Recipe fields that can be set directly (rather than via JSON-LD input).
_DIRECT_FIELDS = (
    "source_url", "author", "image_url", "yields",
    "total_time", "prep_time", "cook_time",
)


def _make_recipe(**kwargs) -> Recipe:
    overrides = {k: kwargs.pop(k) for k in list(kwargs) if k in _DIRECT_FIELDS}
    raw = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": kwargs.pop("name", "Chocolate Cake"),
        "recipeIngredient": kwargs.pop("ingredients", ["flour", "eggs"]),
        "recipeInstructions": [
            {"@type": "HowToStep", "text": s}
            for s in kwargs.pop("steps", ["Mix.", "Bake."])
        ],
    }
    raw.update(kwargs)  # any remaining JSON-LD-shaped keys
    source_url = overrides.pop("source_url", "https://example.com/cake")
    recipe = Recipe.from_jsonld(raw, source_url)
    return replace(recipe, **overrides) if overrides else recipe


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

class TestHtmlStructure:
    def test_valid_xhtml_declaration(self):
        html = render_html(_make_recipe())
        assert html.startswith("<?xml")
        assert 'encoding="utf-8"' in html

    def test_title_in_head_and_body(self):
        html = render_html(_make_recipe(name="My Cake"))
        assert "<title>My Cake</title>" in html
        assert "<h1>My Cake</h1>" in html

    def test_ingredients_in_aside(self):
        html = render_html(_make_recipe(ingredients=["flour", "sugar", "butter"]))
        aside_match = re.search(r"<aside>(.*?)</aside>", html, re.DOTALL)
        assert aside_match, "No <aside> found"
        aside = aside_match.group(1)
        assert "flour" in aside
        assert "sugar" in aside
        assert "butter" in aside

    def test_instructions_in_ordered_list(self):
        html = render_html(_make_recipe(steps=["Step one", "Step two"]))
        main_match = re.search(r"<main>(.*?)</main>", html, re.DOTALL)
        assert main_match, "No <main> found"
        main_content = main_match.group(1)
        assert "<ol>" in main_content
        assert "Step one" in main_content
        assert "Step two" in main_content

    def test_source_url_present(self):
        html = render_html(_make_recipe())
        assert "https://example.com/cake" in html

    def test_cover_image_rendered(self):
        html = render_html(_make_recipe(image_url="https://img.example.com/cake.jpg"))
        assert 'src="https://img.example.com/cake.jpg"' in html

    def test_no_image_url_no_img_tag(self):
        html = render_html(_make_recipe(image_url=""))
        assert "<img" not in html

    def test_meta_time_rendered(self):
        html = render_html(_make_recipe(total_time="45 min"))
        assert "45 min" in html

    def test_meta_yield_rendered(self):
        html = render_html(_make_recipe(yields="8 servings"))
        assert "8 servings" in html

    def test_meta_prep_time_rendered(self):
        html = render_html(_make_recipe(prep_time="15 min"))
        assert "Prep" in html
        assert "15 min" in html

    def test_meta_cook_time_rendered(self):
        html = render_html(_make_recipe(cook_time="40 min"))
        assert "Cook" in html
        assert "40 min" in html

    def test_empty_prep_and_cook_not_rendered(self):
        html = render_html(_make_recipe(prep_time="", cook_time=""))
        assert "Prep:" not in html
        assert "Cook:" not in html

    def test_meta_author_rendered(self):
        html = render_html(_make_recipe(author="Julia Child"))
        assert "Julia Child" in html

    def test_empty_time_not_rendered(self):
        html = render_html(_make_recipe(total_time=""))
        assert "Total:" not in html


# ---------------------------------------------------------------------------
# HTML escaping / security
# ---------------------------------------------------------------------------

class TestHtmlEscaping:
    def test_title_escaped(self):
        r = _make_recipe(name="<script>alert('xss')</script>")
        html = render_html(r)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_ingredient_escaped(self):
        r = _make_recipe(ingredients=["1 cup <b>sugar</b> & honey"])
        html = render_html(r)
        assert "<b>sugar</b>" not in html
        assert "&lt;b&gt;sugar&lt;/b&gt;" in html
        assert "&amp;" in html

    def test_instruction_escaped(self):
        r = _make_recipe(steps=['Add "salt" to taste'])
        html = render_html(r)
        assert '"salt"' not in html
        assert "&quot;salt&quot;" in html

    def test_source_url_escaped(self):
        r = _make_recipe(source_url="https://example.com/recipe?a=1&b=2")
        html = render_html(r)
        # Raw & must not appear in href attribute
        assert 'href="https://example.com/recipe?a=1&amp;b=2"' in html

    def test_author_escaped(self):
        html = render_html(_make_recipe(author="Chef <Evil>"))
        assert "<Evil>" not in html
        assert "&lt;Evil&gt;" in html


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_ingredients_list(self):
        r = _make_recipe(ingredients=[])
        html = render_html(r)
        assert "<aside>" in html   # aside still renders

    def test_empty_instructions_list(self):
        r = _make_recipe(steps=[])
        html = render_html(r)
        assert "<ol>" in html      # ol still renders

    def test_unicode_content(self):
        r = _make_recipe(
            name="Crème Brûlée",
            ingredients=["200ml crème fraîche", "½ tsp vanilla"],
            steps=["Réfrigérer pendant 2h."],
        )
        html = render_html(r)
        assert "Crème Brûlée" in html
        assert "crème fraîche" in html
        assert "Réfrigérer" in html
