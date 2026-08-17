"""Settings persistence and colour parsing."""

import json

import pytest

from pedalcal import settings as S
from pedalcal import theme as T


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / ".pedalcal.json"
    monkeypatch.setattr(S, "CONFIG_FILE", path)
    return path


def test_round_trip(config):
    original = S.AppSettings(theme="light", accent="#a3e635", on_top=False,
                             console_open=True, axes=[True, True, False])
    S.save(original)
    assert S.load() == original


def test_missing_file_gives_defaults(config):
    assert S.load() == S.AppSettings.defaults()


def test_corrupt_file_gives_defaults(config):
    config.write_text("{not json at all")
    assert S.load() == S.AppSettings.defaults()


def test_junk_values_are_ignored(config):
    config.write_text(json.dumps({"theme": "neon", "accent": "puce",
                                  "axes": ["only", "two"]}))
    loaded = S.load()
    assert loaded.theme == S.DEFAULT_THEME
    assert loaded.accent == S.DEFAULT_ACCENT
    assert loaded.axes == [True, True, True]


def test_never_saves_every_pedal_off(config):
    """An all-off state would leave the calibration tab empty."""
    config.write_text(json.dumps({"axes": [False, False, False]}))
    assert S.load().axes == [True, True, True]


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


def test_light_theme_darkens_bright_accents():
    lime = "#a3e635"
    assert T.palette_for("dark", lime).accent == lime
    light = T.palette_for("light", lime)
    assert light.accent != lime          # adjusted for contrast
    assert light.accent_seed == lime     # but the swatch still matches
