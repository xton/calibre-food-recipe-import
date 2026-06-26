import json
import pytest

from calibre_plugin.recipe_extract import (
    Recipe,
    RecipeExtractionError,
    _author_name,
    _duration_minutes,
    _format_duration,
    _image_url,
    _list_of_strings,
    _scalar,
    _tags_from_recipe,
    extract_recipe_jsonld,
    extract_recipe_microdata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _html(jsonld: dict | list) -> str:
    blob = json.dumps(jsonld)
    return f'<html><head><script type="application/ld+json">{blob}</script></head></html>'


def _minimal_raw(**kwargs) -> dict:
    base = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": "Test Recipe",
        "recipeIngredient": ["flour"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Mix."}],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# extract_recipe_jsonld
# ---------------------------------------------------------------------------

class TestExtractRecipeJsonld:
    def test_flat_type(self):
        raw = extract_recipe_jsonld(_html(_minimal_raw()))
        assert raw is not None
        assert raw["@type"] == "Recipe"

    def test_list_type(self):
        data = _minimal_raw()
        data["@type"] = ["Recipe", "Thing"]
        raw = extract_recipe_jsonld(_html(data))
        assert raw is not None

    def test_nested_graph(self):
        data = {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "WebPage", "name": "Site"},
                _minimal_raw(name="Graph Cookie"),
            ],
        }
        raw = extract_recipe_jsonld(_html(data))
        assert raw is not None
        assert raw["name"] == "Graph Cookie"

    def test_deeply_nested(self):
        # Recipe buried inside another object
        data = {"@type": "WebPage", "mainEntity": _minimal_raw(name="Deep")}
        raw = extract_recipe_jsonld(_html(data))
        assert raw is not None
        assert raw["name"] == "Deep"

    def test_multiple_scripts_picks_first_recipe(self):
        block1 = json.dumps({"@type": "Organization", "name": "Acme"})
        block2 = json.dumps(_minimal_raw(name="Pancakes"))
        html = (
            f'<html><head>'
            f'<script type="application/ld+json">{block1}</script>'
            f'<script type="application/ld+json">{block2}</script>'
            f'</head></html>'
        )
        raw = extract_recipe_jsonld(html)
        assert raw is not None
        assert raw["name"] == "Pancakes"

    def test_malformed_json_skipped(self):
        good = json.dumps(_minimal_raw(name="Good"))
        html = (
            '<html><head>'
            '<script type="application/ld+json">{bad json!!}</script>'
            f'<script type="application/ld+json">{good}</script>'
            '</head></html>'
        )
        raw = extract_recipe_jsonld(html)
        assert raw is not None
        assert raw["name"] == "Good"

    def test_no_recipe_returns_none(self):
        data = {"@type": "Organization", "name": "Acme"}
        assert extract_recipe_jsonld(_html(data)) is None

    def test_empty_html_returns_none(self):
        assert extract_recipe_jsonld("<html><body>nothing</body></html>") is None

    def test_case_insensitive_script_type(self):
        blob = json.dumps(_minimal_raw())
        html = f'<html><head><script type="Application/LD+JSON">{blob}</script></head></html>'
        assert extract_recipe_jsonld(html) is not None


# ---------------------------------------------------------------------------
# _scalar
# ---------------------------------------------------------------------------

class TestScalar:
    def test_string(self):
        assert _scalar("hello") == "hello"

    def test_list_first_element(self):
        assert _scalar(["a", "b"]) == "a"

    def test_empty_list(self):
        assert _scalar([]) == ""

    def test_none(self):
        assert _scalar(None) == ""

    def test_number(self):
        assert _scalar(42) == "42"


# ---------------------------------------------------------------------------
# _list_of_strings
# ---------------------------------------------------------------------------

class TestListOfStrings:
    def test_plain_string(self):
        assert _list_of_strings("one step") == ["one step"]

    def test_list_of_strings(self):
        assert _list_of_strings(["a", "b", "c"]) == ["a", "b", "c"]

    def test_how_to_step_text(self):
        steps = [{"@type": "HowToStep", "text": "Preheat"}, {"@type": "HowToStep", "text": "Bake"}]
        assert _list_of_strings(steps) == ["Preheat", "Bake"]

    def test_how_to_step_name_fallback(self):
        steps = [{"@type": "HowToStep", "name": "Step one"}]
        assert _list_of_strings(steps) == ["Step one"]

    def test_mixed_list(self):
        mixed = ["plain", {"@type": "HowToStep", "text": "structured"}]
        assert _list_of_strings(mixed) == ["plain", "structured"]

    def test_empty_strings_filtered(self):
        assert _list_of_strings(["", "  ", "keep"]) == ["keep"]

    def test_none_returns_empty(self):
        assert _list_of_strings(None) == []

    def test_whitespace_stripped(self):
        assert _list_of_strings(["  flour  "]) == ["flour"]


# ---------------------------------------------------------------------------
# _duration_minutes / _format_duration
# ---------------------------------------------------------------------------

class TestDuration:
    @pytest.mark.parametrize("iso,expected", [
        ("PT30M", 30),
        ("PT1H", 60),
        ("PT1H30M", 90),
        ("PT2H0M", 120),
        ("PT45S", None),   # seconds only → None (< 1 minute)
        ("PT0M", None),
        ("", None),
        ("garbage", None),
        ("P1DT2H", None),  # days not supported → None
    ])
    def test_duration_minutes(self, iso, expected):
        assert _duration_minutes(iso) == expected

    @pytest.mark.parametrize("iso,expected", [
        ("PT30M", "30 min"),
        ("PT1H", "1 hr"),
        ("PT1H30M", "1 hr 30 min"),
        ("PT2H0M", "2 hr"),
        ("", ""),
        ("bad", ""),
    ])
    def test_format_duration(self, iso, expected):
        assert _format_duration(iso) == expected


# ---------------------------------------------------------------------------
# _image_url
# ---------------------------------------------------------------------------

class TestImageUrl:
    def test_plain_string(self):
        assert _image_url("https://example.com/img.jpg") == "https://example.com/img.jpg"

    def test_image_object_url(self):
        assert _image_url({"@type": "ImageObject", "url": "https://x.com/a.jpg"}) == "https://x.com/a.jpg"

    def test_image_object_content_url_fallback(self):
        assert _image_url({"@type": "ImageObject", "contentUrl": "https://x.com/b.jpg"}) == "https://x.com/b.jpg"

    def test_list_of_strings(self):
        assert _image_url(["https://first.com/img.jpg", "https://second.com/img.jpg"]) == "https://first.com/img.jpg"

    def test_list_of_objects(self):
        imgs = [{"url": "https://a.com/1.jpg"}, {"url": "https://a.com/2.jpg"}]
        assert _image_url(imgs) == "https://a.com/1.jpg"

    def test_none(self):
        assert _image_url(None) == ""

    def test_empty_list(self):
        assert _image_url([]) == ""


# ---------------------------------------------------------------------------
# _author_name
# ---------------------------------------------------------------------------

class TestAuthorName:
    def test_string(self):
        assert _author_name("Alice") == "Alice"

    def test_person_object(self):
        assert _author_name({"@type": "Person", "name": "Bob"}) == "Bob"

    def test_list_takes_first(self):
        assert _author_name([{"name": "First"}, {"name": "Second"}]) == "First"

    def test_none(self):
        assert _author_name(None) == ""

    def test_empty_dict(self):
        assert _author_name({}) == ""


# ---------------------------------------------------------------------------
# _tags_from_recipe
# ---------------------------------------------------------------------------

class TestTagsFromRecipe:
    def test_category_and_cuisine(self):
        tags = _tags_from_recipe({"recipeCategory": "Dessert", "recipeCuisine": "French"})
        assert "Dessert" in tags
        assert "French" in tags

    def test_comma_separated_category(self):
        tags = _tags_from_recipe({"recipeCategory": "Dessert, Snack"})
        assert "Dessert" in tags
        assert "Snack" in tags

    def test_keywords_string(self):
        tags = _tags_from_recipe({"keywords": "easy, quick, healthy"})
        assert tags == ["easy", "quick", "healthy"]

    def test_keywords_list(self):
        tags = _tags_from_recipe({"keywords": ["vegan", "gluten-free"]})
        assert "vegan" in tags
        assert "gluten-free" in tags

    def test_deduplication_case_insensitive(self):
        tags = _tags_from_recipe({
            "recipeCategory": "Dessert",
            "keywords": "dessert, cake",
        })
        lower_tags = [t.lower() for t in tags]
        assert lower_tags.count("dessert") == 1

    def test_empty_recipe(self):
        assert _tags_from_recipe({}) == []

    def test_list_category(self):
        tags = _tags_from_recipe({"recipeCategory": ["Dinner", "Main Course"]})
        assert "Dinner" in tags
        assert "Main Course" in tags


# ---------------------------------------------------------------------------
# Recipe (integration of all normalisers)
# ---------------------------------------------------------------------------

class TestRecipe:
    def _make(self, **kwargs) -> Recipe:
        return Recipe.from_jsonld(_minimal_raw(**kwargs), "https://example.com/recipe")

    def test_defaults(self):
        r = self._make()
        assert r.title == "Test Recipe"
        assert r.author == ""
        assert r.image_url == ""
        assert r.total_time == ""
        assert r.yields == ""
        assert r.tags == []

    def test_full_recipe(self):
        raw = _minimal_raw(
            author={"@type": "Person", "name": "Chef A"},
            image="https://img.com/photo.jpg",
            totalTime="PT1H15M",
            recipeYield="4 servings",
            recipeCategory="Dinner",
            recipeCuisine="Italian",
            keywords="pasta, easy",
        )
        r = Recipe.from_jsonld(raw, "https://example.com/recipe")
        assert r.author == "Chef A"
        assert r.image_url == "https://img.com/photo.jpg"
        assert r.total_time == "1 hr 15 min"
        assert r.yields == "4 servings"
        assert "Dinner" in r.tags
        assert "Italian" in r.tags
        assert "pasta" in r.tags

    def test_missing_name_fallback(self):
        raw = _minimal_raw()
        del raw["name"]
        r = Recipe.from_jsonld(raw, "https://example.com/recipe")
        assert r.title == "Untitled Recipe"

    def test_ingredients_and_instructions_parsed(self):
        r = self._make()
        assert r.ingredients == ["flour"]
        assert r.instructions == ["Mix."]

    def test_source_url_stored(self):
        r = self._make()
        assert r.source_url == "https://example.com/recipe"


# ---------------------------------------------------------------------------
# extract_recipe_microdata
# ---------------------------------------------------------------------------

def _microdata_html(
    name="Test Recipe",
    ingredients=("1 cup flour", "2 eggs"),
    instructions=("Mix.", "Bake."),
    total_time=None,
    yields=None,
    image=None,
    description=None,
) -> str:
    parts = [
        '<div itemscope itemtype="https://schema.org/Recipe">',
        f'<h3 itemprop="name">{name}</h3>',
    ]
    if description:
        parts.append(f'<p itemprop="description">{description}</p>')
    if yields:
        parts.append(f'<span itemprop="recipeYield">{yields}</span>')
    if total_time:
        parts.append(f'<time itemprop="totalTime" datetime="{total_time}">{total_time}</time>')
    if image:
        parts.append(f'<img itemprop="image" src="{image}" />')
    for ing in ingredients:
        parts.append(f'<li itemprop="recipeIngredient">{ing}</li>')
    for step in instructions:
        parts.append(f'<li itemprop="recipeInstructions">{step}</li>')
    parts.append("</div>")
    return "<html><body>" + "".join(parts) + "</body></html>"


class TestExtractRecipeMicrodata:
    def test_basic_extraction(self):
        raw = extract_recipe_microdata(_microdata_html())
        assert raw is not None
        assert raw["name"] == "Test Recipe"

    def test_ingredients_collected(self):
        raw = extract_recipe_microdata(_microdata_html(ingredients=["1 cup flour", "2 eggs"]))
        assert raw["recipeIngredient"] == ["1 cup flour", "2 eggs"]

    def test_instructions_collected(self):
        raw = extract_recipe_microdata(_microdata_html(instructions=["Mix.", "Bake."]))
        assert raw["recipeInstructions"] == ["Mix.", "Bake."]

    def test_iso_duration_stored(self):
        raw = extract_recipe_microdata(_microdata_html(total_time="PT45M"))
        assert raw["totalTime"] == "PT45M"

    def test_human_readable_duration_stored(self):
        raw = extract_recipe_microdata(_microdata_html(total_time="3 hours including cooling"))
        assert raw["totalTime"] == "3 hours including cooling"

    def test_yields_extracted(self):
        raw = extract_recipe_microdata(_microdata_html(yields="8 servings"))
        assert raw["recipeYield"] == "8 servings"

    def test_image_from_src_attribute(self):
        raw = extract_recipe_microdata(_microdata_html(image="https://example.com/photo.jpg"))
        assert raw["image"] == "https://example.com/photo.jpg"

    def test_description_extracted(self):
        raw = extract_recipe_microdata(_microdata_html(description="A great recipe."))
        assert raw["description"] == "A great recipe."

    def test_no_recipe_returns_none(self):
        assert extract_recipe_microdata("<html><body>no recipe here</body></html>") is None

    def test_no_name_returns_none(self):
        html = '<div itemscope itemtype="https://schema.org/Recipe"><li itemprop="recipeIngredient">flour</li></div>'
        assert extract_recipe_microdata(html) is None

    def test_case_insensitive_itemtype(self):
        html = '<div itemscope itemtype="https://schema.org/Recipe"><h3 itemprop="name">Cake</h3></div>'
        raw = extract_recipe_microdata(html)
        assert raw is not None

    def test_nested_elements_inside_itemprop(self):
        html = (
            '<div itemscope itemtype="https://schema.org/Recipe">'
            '<h3 itemprop="name">Cake</h3>'
            '<li itemprop="recipeIngredient"><strong>1 cup</strong> flour</li>'
            '</div>'
        )
        raw = extract_recipe_microdata(html)
        assert raw is not None
        assert "flour" in raw["recipeIngredient"][0]

    def test_jetpack_style_recipe(self):
        """Matches the WordPress Jetpack recipe plugin pattern used by Smitten Kitchen."""
        html = (
            '<div class="jetpack-recipe" itemscope itemtype="https://schema.org/Recipe">'
            '<h3 class="jetpack-recipe-title" itemprop="name">Strawberry Cake</h3>'
            '<li class="jetpack-recipe-servings" itemprop="recipeYield"><strong>Servings: </strong>8</li>'
            '<time itemprop="totalTime" datetime="2 hours"><strong>Time:</strong> 2 hours</time>'
            '<li class="jetpack-recipe-ingredient" itemprop="recipeIngredient">2 cups flour</li>'
            '<li class="jetpack-recipe-ingredient" itemprop="recipeIngredient">1 cup sugar</li>'
            '</div>'
        )
        raw = extract_recipe_microdata(html)
        assert raw is not None
        assert raw["name"] == "Strawberry Cake"
        assert raw["totalTime"] == "2 hours"
        assert len(raw["recipeIngredient"]) == 2
        assert raw["recipeIngredient"][0] == "2 cups flour"

    def test_post_recipe_paragraphs_used_as_instructions(self):
        """Instructions in <p> tags after the recipe block are collected as fallback."""
        html = (
            '<div itemscope itemtype="https://schema.org/Recipe">'
            '<h3 itemprop="name">Simple Cake</h3>'
            '<li itemprop="recipeIngredient">2 cups flour</li>'
            '</div>'
            '<p>Mix the flour.</p>'
            '<p>Bake at 350F for 30 minutes.</p>'
            '<div class="sidebar">unrelated</div>'
        )
        raw = extract_recipe_microdata(html)
        assert raw is not None
        assert raw["recipeInstructions"] == ["Mix the flour.", "Bake at 350F for 30 minutes."]

    def test_microdata_instructions_take_precedence_over_post_recipe(self):
        """If microdata has recipeInstructions, post-recipe paragraphs are ignored."""
        html = (
            '<div itemscope itemtype="https://schema.org/Recipe">'
            '<h3 itemprop="name">Cake</h3>'
            '<li itemprop="recipeInstructions">Mix.</li>'
            '</div>'
            '<p>This should be ignored.</p>'
        )
        raw = extract_recipe_microdata(html)
        assert raw["recipeInstructions"] == ["Mix."]

    def test_post_recipe_stops_at_div(self):
        """Post-recipe collection stops when a <div> is encountered."""
        html = (
            '<div itemscope itemtype="https://schema.org/Recipe">'
            '<h3 itemprop="name">Cake</h3>'
            '</div>'
            '<p>Step one.</p>'
            '<div><p>This is in a sidebar, not an instruction.</p></div>'
        )
        raw = extract_recipe_microdata(html)
        assert raw["recipeInstructions"] == ["Step one."]

    def test_post_recipe_bare_text_before_first_p(self):
        """Text before the first explicit </p> is captured (handles Smitten Kitchen's
        malformed first step that has no opening <p> tag)."""
        html = (
            '<div itemscope itemtype="https://schema.org/Recipe">'
            '<h3 itemprop="name">Cake</h3>'
            '</div>'
            '<strong>Heat oven:</strong> To 350F.</p>'
            '<p>Mix ingredients.</p>'
            '<div class="sidebar">stop here</div>'
        )
        raw = extract_recipe_microdata(html)
        assert raw["recipeInstructions"][0] == "Heat oven: To 350F."
        assert raw["recipeInstructions"][1] == "Mix ingredients."
