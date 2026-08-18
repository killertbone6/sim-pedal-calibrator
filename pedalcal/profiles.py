"""Named per-pedal profiles, kept on this PC.

A profile is one pedal's whole feel: where its travel starts and ends, its
response curve, its deadzone, and whether filtering is on. Rally settings and
a hotlap setting are different enough to be worth naming.

They live on the PC rather than on the board on purpose. The board stores
exactly one configuration - the one it uses when the app isn't running - so
there is nowhere on it to keep a second. Loading a profile writes it to the
board, and Save on the calibration page makes it the one the board keeps.

Each pedal has its own set of profiles: a brake profile has no meaning applied
to a throttle, and being able to name them separately is the point.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from . import protocol as P

PROFILE_FILE = Path.home() / ".pedalcal-profiles.json"

#: Long enough to be descriptive, short enough for the dropdown.
NAME_MAX = 32


@dataclass
class PedalProfile:
    """Everything that makes one pedal feel the way it does."""

    lo: int = 0
    hi: int = P.ADC_MAX
    curve: int = 0
    deadzone: int = 0
    smoothing: bool = True

    def clamped(self) -> "PedalProfile":
        lo = max(0, min(P.ADC_MAX, int(self.lo)))
        hi = max(0, min(P.ADC_MAX, int(self.hi)))
        if hi <= lo:                       # a zero-width range reads as stuck
            lo, hi = 0, P.ADC_MAX
        return PedalProfile(
            lo=lo,
            hi=hi,
            curve=max(-P.CURVE_MAX, min(P.CURVE_MAX, int(self.curve))),
            deadzone=max(0, min(P.DEADZONE_MAX, int(self.deadzone))),
            smoothing=bool(self.smoothing),
        )


def clean_name(name: str) -> str:
    """Trim a name to something that will fit and can be found again."""
    return " ".join(str(name).split())[:NAME_MAX]


class ProfileStore:
    """The saved profiles for all three pedals, plus which one is selected."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or PROFILE_FILE
        #: axis index -> {name: PedalProfile}
        self.axes: list[dict[str, PedalProfile]] = [
            {} for _ in range(P.NUM_AXES)]
        #: axis index -> the name currently in use, "" for none
        self.chosen: list[str] = ["" for _ in range(P.NUM_AXES)]
        self.load()

    # -- persistence -----------------------------------------------------

    def load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return  # no profiles yet, or an unreadable file: start empty

        axes = data.get("axes")
        if not isinstance(axes, list):
            return
        for index, entry in enumerate(axes[:P.NUM_AXES]):
            if not isinstance(entry, dict):
                continue
            saved = entry.get("profiles")
            if isinstance(saved, dict):
                for name, values in saved.items():
                    name = clean_name(name)
                    if not name or not isinstance(values, dict):
                        continue
                    try:
                        profile = PedalProfile(
                            lo=int(values.get("lo", 0)),
                            hi=int(values.get("hi", P.ADC_MAX)),
                            curve=int(values.get("curve", 0)),
                            deadzone=int(values.get("deadzone", 0)),
                            smoothing=bool(values.get("smoothing", True)),
                        )
                    except (TypeError, ValueError):
                        continue
                    self.axes[index][name] = profile.clamped()
            chosen = clean_name(entry.get("chosen", ""))
            if chosen in self.axes[index]:
                self.chosen[index] = chosen

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps({
                "version": 1,
                "axes": [
                    {
                        "chosen": self.chosen[i],
                        "profiles": {name: asdict(profile)
                                     for name, profile in self.axes[i].items()},
                    }
                    for i in range(P.NUM_AXES)
                ],
            }, indent=2), encoding="utf-8")
        except Exception:
            pass  # a read-only home directory must not break calibration

    # -- queries ---------------------------------------------------------

    def names(self, axis: int) -> list[str]:
        return sorted(self.axes[axis], key=str.casefold)

    def get(self, axis: int, name: str) -> PedalProfile | None:
        return self.axes[axis].get(clean_name(name))

    def selected(self, axis: int) -> str:
        return self.chosen[axis]

    def select(self, axis: int, name: str) -> None:
        name = clean_name(name)
        self.chosen[axis] = name if name in self.axes[axis] else ""
        self.save()

    # -- edits -----------------------------------------------------------

    def put(self, axis: int, name: str, profile: PedalProfile) -> str:
        """Create or overwrite a profile and make it the selected one."""
        name = clean_name(name)
        if not name:
            return ""
        self.axes[axis][name] = profile.clamped()
        self.chosen[axis] = name
        self.save()
        return name

    def delete(self, axis: int, name: str) -> None:
        name = clean_name(name)
        self.axes[axis].pop(name, None)
        if self.chosen[axis] == name:
            self.chosen[axis] = ""
        self.save()

    def clear(self) -> None:
        self.axes = [{} for _ in range(P.NUM_AXES)]
        self.chosen = ["" for _ in range(P.NUM_AXES)]
        self.save()

    def unique_name(self, axis: int, base: str) -> str:
        """'Rain' -> 'Rain 2' when 'Rain' is taken, so Save As never silently
        overwrites the profile the user is looking at."""
        base = clean_name(base) or "Profile"
        if base not in self.axes[axis]:
            return base
        for n in range(2, 100):
            candidate = clean_name(f"{base} {n}")
            if candidate not in self.axes[axis]:
                return candidate
        return base
