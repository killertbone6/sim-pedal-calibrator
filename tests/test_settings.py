"""Settings persistence, colour derivation and translations."""

import json

import pytest

from pedalcal import i18n
from pedalcal import settings as S
from pedalcal import theme as T


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / ".pedalcal.json"
    monkeypatch.setattr(S, "CONFIG_FILE", path)
    return path


def test_round_trip(config):
    original = S.AppSettings(bg_brightness=64, accent="#a3e635", on_top=False,
                             console_open=True, language="de",
                             language_chosen=True, layout="side",
                             axes=[True, True, False])
    S.save(original)
    assert S.load() == original


def test_missing_file_gives_defaults(config):
    assert S.load() == S.AppSettings.defaults()


def test_corrupt_file_gives_defaults(config):
    config.write_text("{not json at all")
    assert S.load() == S.AppSettings.defaults()


def test_junk_values_are_ignored(config):
    config.write_text(json.dumps({"accent": "puce", "language": "klingon",
                                  "layout": "diagonal",
                                  "axes": ["only", "two"]}))
    loaded = S.load()
    assert loaded.accent == S.DEFAULT_ACCENT
    assert loaded.language == "en"
    assert loaded.layout == "stacked"
    assert loaded.axes == [True, True, True]


def test_never_saves_every_pedal_off(config):
    """An all-off state would leave the calibration tab empty."""
    config.write_text(json.dumps({"axes": [False, False, False]}))
    assert S.load().axes == [True, True, True]


def test_old_light_theme_becomes_a_bright_background(config):
    """Upgrading shouldn't throw someone back onto a black window."""
    config.write_text(json.dumps({"theme": "light"}))
    assert S.load().bg_brightness > 80


def test_old_dark_theme_keeps_the_default(config):
    config.write_text(json.dumps({"theme": "dark"}))
    assert S.load().bg_brightness == T.DEFAULT_BRIGHTNESS


# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------


@pytest.mark.parametrize("text, expected", [
    ("#22d3ee", "#22d3ee"),
    ("22D3EE", "#22d3ee"),
    ("34,211,238", "#22d3ee"),
    ("34 211 238", "#22d3ee"),
    ("rgb(34, 211, 238)", "#22d3ee"),
    ("0f8", "#00ff88"),
])
def test_colour_formats_people_actually_paste(text, expected):
    assert T.parse_colour(text) == expected


@pytest.mark.parametrize("text", ["", "puce", "300,0,0", "12,34", "#12345"])
def test_bad_colours_rejected(text):
    assert T.parse_colour(text) is None


def test_brightness_slider_runs_dark_to_light():
    assert T.luminance(T.brightness_bg(0)) < T.luminance(T.brightness_bg(50))
    assert T.luminance(T.brightness_bg(50)) < T.luminance(T.brightness_bg(100))
    assert T.brightness_bg(100) == "#ffffff"


def test_brightness_ramp_is_perceptual_not_linear():
    """Half way along the slider should not already be light grey.

    A linear ramp puts the midpoint at 50% grey, which leaves every usable
    dark shade crammed into the first few percent of the travel.
    """
    assert T.luminance(T.brightness_bg(50)) < 0.15


def test_every_background_stays_readable():
    """The awkward part of a brightness slider is the middle.

    4.5:1 is WCAG AA for body text and 3:1 is the floor for interface parts.
    Body text clears AA at every slider position and every accent, which is
    close to as good as it can be: against a mid-grey background *no* colour
    beats 4.58:1, so a palette that gets 4.6 there is at the ceiling rather
    than being generous.
    """
    for brightness in range(0, 101):
        for _name, seed in T.ACCENTS:
            palette = T.palette_for(brightness, seed)
            where = (brightness, seed)
            assert T.contrast(palette.text, palette.surface) >= 4.5, where
            assert T.contrast(palette.text_dim, palette.surface) >= 3.0, where
            assert T.contrast(palette.accent, palette.surface) >= 3.0, where
            assert T.contrast(palette.on_accent, palette.accent) >= 3.0, where
            assert T.contrast(palette.ok, palette.surface) >= 3.0, where
            assert T.contrast(palette.offline, palette.surface) >= 3.0, where


def test_the_ink_is_never_the_worse_of_the_two_choices():
    """A brightness threshold, rather than a measurement, used to put white
    type on a light-grey background at 2.7:1 while black would have read 7:1."""
    for brightness in range(0, 101):
        palette = T.palette_for(brightness, "#22d3ee")
        other = (T.INK_DARK if T.luminance(palette.text) > 0.5
                 else T.INK_LIGHT)
        assert (T.contrast(palette.text, palette.surface)
                >= T.contrast(other, palette.surface)), brightness


def test_fitting_a_colour_never_makes_it_worse():
    """The fit walks towards black or white; if it can't reach the target it
    has to return its best attempt, not wherever it stopped."""
    for background in ("#000000", "#808080", "#9b9c9e", "#ffffff"):
        for seed in ("#22d3ee", "#a3e635", "#0b0f14", "#f3f7fb"):
            fitted = T.fit_contrast(seed, background, target=21.0)
            assert (T.contrast(fitted, background)
                    >= T.contrast(seed, background))


def test_the_swatch_you_picked_is_still_the_one_selected():
    """A bright accent gets darkened on a light background, but the settings
    page still has to know which chip to ring."""
    lime = "#a3e635"
    assert T.palette_for(0, lime).accent == lime
    bright = T.palette_for(100, lime)
    assert bright.accent != lime
    assert bright.accent_seed == lime


def test_a_typed_background_wins_over_the_slider():
    palette = T.palette_for(10, "#22d3ee", custom_bg="#3b1f5e")
    assert palette.bg == "#3b1f5e"


def test_slider_position_matches_a_typed_colour():
    """Typing a colour moves the slider to where that colour lives, so the two
    controls never disagree about how bright the window is."""
    for brightness in (0, 20, 55, 80, 100):
        colour = T.brightness_bg(brightness)
        assert abs(T.bg_brightness_of(colour) - brightness) <= 1


# --------------------------------------------------------------------------
# Translations
# --------------------------------------------------------------------------


def test_every_language_translates_every_string():
    for code in i18n.LANGUAGE_CODES:
        assert i18n.missing(code) == [], code


def test_unknown_language_falls_back_to_english():
    i18n.set_language("klingon")
    assert i18n.current() == "en"
    assert i18n.t("Settings") == "Settings"


def test_untranslated_string_returns_its_english_source():
    i18n.set_language("de")
    try:
        assert i18n.t("Settings") == "Einstellungen"
        assert i18n.t("not a key in the catalogue") == \
            "not a key in the catalogue"
    finally:
        i18n.set_language("en")


def test_no_language_is_secretly_english():
    """A row copied and not translated would be invisible at a glance."""
    for code in i18n.COLUMNS:
        untranslated = [source for source, text in i18n.CATALOG[code].items()
                        if text == source and len(source.split()) > 2]
        assert untranslated == [], f"{code}: {untranslated}"
