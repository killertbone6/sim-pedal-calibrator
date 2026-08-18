"""Named per-pedal profiles."""

import json

import pytest

from pedalcal import protocol as P
from pedalcal.profiles import PedalProfile, ProfileStore, clean_name


@pytest.fixture
def store(tmp_path):
    return ProfileStore(tmp_path / "profiles.json")


def test_starts_empty(store):
    for axis in range(P.NUM_AXES):
        assert store.names(axis) == []
        assert store.selected(axis) == ""


def test_save_and_reload(store, tmp_path):
    store.put(0, "Rain", PedalProfile(lo=100, hi=900, curve=-20, deadzone=4,
                                      smoothing=False))
    reopened = ProfileStore(tmp_path / "profiles.json")
    profile = reopened.get(0, "Rain")
    assert profile == PedalProfile(lo=100, hi=900, curve=-20, deadzone=4,
                                   smoothing=False)
    assert reopened.selected(0) == "Rain"


def test_each_pedal_has_its_own_set(store):
    """A brake profile means nothing applied to a throttle."""
    store.put(0, "Rain", PedalProfile(lo=10, hi=900))
    store.put(1, "Rain", PedalProfile(lo=50, hi=800))
    assert store.get(0, "Rain").lo == 10
    assert store.get(1, "Rain").lo == 50
    assert store.names(2) == []


def test_saving_over_a_name_replaces_it(store):
    store.put(0, "Rain", PedalProfile(deadzone=2))
    store.put(0, "Rain", PedalProfile(deadzone=9))
    assert store.names(0) == ["Rain"]
    assert store.get(0, "Rain").deadzone == 9


def test_delete_clears_the_selection_too(store):
    store.put(0, "Rain", PedalProfile())
    store.delete(0, "Rain")
    assert store.names(0) == []
    assert store.selected(0) == ""


def test_selecting_something_that_was_deleted_selects_nothing(store):
    store.select(0, "never existed")
    assert store.selected(0) == ""


def test_unique_name_does_not_silently_overwrite(store):
    store.put(0, "Rain", PedalProfile())
    assert store.unique_name(0, "Rain") == "Rain 2"
    store.put(0, "Rain 2", PedalProfile())
    assert store.unique_name(0, "Rain") == "Rain 3"
    assert store.unique_name(0, "Dry") == "Dry"


@pytest.mark.parametrize("given, expected", [
    ("  Rain  ", "Rain"),
    ("Rain\tand\nsnow", "Rain and snow"),
    ("x" * 80, "x" * 32),
    ("", ""),
])
def test_names_are_tidied(given, expected):
    assert clean_name(given) == expected


def test_a_nameless_profile_is_refused(store):
    assert store.put(0, "   ", PedalProfile()) == ""
    assert store.names(0) == []


def test_values_are_clamped_to_what_the_hardware_accepts():
    profile = PedalProfile(lo=-50, hi=99999, curve=500, deadzone=90).clamped()
    assert profile.lo == 0
    assert profile.hi == P.ADC_MAX
    assert profile.curve == P.CURVE_MAX
    assert profile.deadzone == P.DEADZONE_MAX


def test_an_inverted_range_becomes_the_full_range():
    """A saved lo above hi would read as a permanently stuck pedal."""
    profile = PedalProfile(lo=800, hi=200).clamped()
    assert (profile.lo, profile.hi) == (0, P.ADC_MAX)


def test_corrupt_file_does_not_stop_the_app(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{ this is not json")
    store = ProfileStore(path)
    assert store.names(0) == []


def test_junk_entries_are_skipped_but_good_ones_survive(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({
        "version": 1,
        "axes": [
            {"chosen": "Good",
             "profiles": {"Good": {"lo": 5, "hi": 900},
                          "Bad": "not a dict",
                          "Worse": {"lo": "banana"}}},
            "not a dict at all",
            {},
        ],
    }))
    store = ProfileStore(path)
    assert store.names(0) == ["Good"]
    assert store.get(0, "Good").hi == 900
    assert store.selected(0) == "Good"


def test_clear_removes_everything(store):
    store.put(0, "Rain", PedalProfile())
    store.put(2, "Dry", PedalProfile())
    store.clear()
    assert store.names(0) == [] and store.names(2) == []


def test_a_read_only_home_does_not_raise(tmp_path):
    store = ProfileStore(tmp_path / "no-such-directory" / "profiles.json")
    store.put(0, "Rain", PedalProfile())      # must not raise
    assert store.names(0) == ["Rain"]
