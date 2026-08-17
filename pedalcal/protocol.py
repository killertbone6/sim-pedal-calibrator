"""The line protocol spoken between this app and the pedal firmware.

Everything is plain ASCII text, one message per line, terminated with "\\n".
That makes it trivial to debug: open the Arduino IDE's Serial Monitor at
115200 baud and you can type these commands by hand.

PC  ->  device
    ID?                     ask what is on the other end
    GET                     ask for the stored calibration
    SET <axis> <min> <max>  set calibration for one axis (applied immediately)
    SAVE                    write the current calibration to EEPROM
    LOAD                    re-read the calibration from EEPROM
    STREAM <0|1>            turn the live value stream off / on

device -> PC
    PEDALCAL <version>          identity banner (reply to ID?)
    D <raw0> <raw1> <raw2>      live raw ADC values, ~50 per second
    C <min0> <max0> ... <max2>  the current calibration (reply to GET / LOAD)
    OK                          command accepted
    ERR <reason>                command rejected
"""

from __future__ import annotations

from dataclasses import dataclass

BAUD = 115200
FIRMWARE_ID = "PEDALCAL"
PROTOCOL_VERSION = 1

AXIS_NAMES = ("Throttle", "Brake", "Clutch")
NUM_AXES = len(AXIS_NAMES)

#: Arduino's analogRead() is 10-bit, so raw values run 0..1023.
ADC_MAX = 1023


# --------------------------------------------------------------------------
# Messages coming from the device
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ident:
    """Reply to ``ID?`` - confirms we are talking to pedal firmware."""

    version: int


@dataclass(frozen=True)
class Data:
    """One frame of live raw readings, one per axis."""

    raw: tuple[int, ...]


@dataclass(frozen=True)
class Calibration:
    """The min/max pair currently in use for every axis."""

    points: tuple[tuple[int, int], ...]

    @staticmethod
    def default() -> "Calibration":
        return Calibration(tuple((0, ADC_MAX) for _ in range(NUM_AXES)))

    def with_axis(self, axis: int, lo: int, hi: int) -> "Calibration":
        points = list(self.points)
        points[axis] = (lo, hi)
        return Calibration(tuple(points))


@dataclass(frozen=True)
class Ack:
    """``OK`` or ``ERR <reason>``."""

    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class Unknown:
    """Anything we did not recognise - shown in the log, never fatal."""

    text: str


Message = Ident | Data | Calibration | Ack | Unknown


def parse_line(line: str) -> Message:
    """Turn one line of text from the device into a message object."""
    text = line.strip()
    if not text:
        return Unknown("")

    parts = text.split()
    tag = parts[0].upper()

    try:
        if tag == FIRMWARE_ID:
            version = int(parts[1]) if len(parts) > 1 else 0
            return Ident(version)

        if tag == "D" and len(parts) == NUM_AXES + 1:
            return Data(tuple(int(p) for p in parts[1:]))

        if tag == "C" and len(parts) == NUM_AXES * 2 + 1:
            numbers = [int(p) for p in parts[1:]]
            pairs = tuple(
                (numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)
            )
            return Calibration(pairs)

        if tag == "OK":
            return Ack(True)

        if tag == "ERR":
            return Ack(False, " ".join(parts[1:]))
    except ValueError:
        # A garbled line (unplugged mid-frame, line noise). Not worth crashing.
        return Unknown(text)

    return Unknown(text)


# --------------------------------------------------------------------------
# Commands going to the device
# --------------------------------------------------------------------------


def cmd_ident() -> str:
    return "ID?"


def cmd_get() -> str:
    return "GET"


def cmd_set(axis: int, lo: int, hi: int) -> str:
    """Build a SET command, refusing values the firmware would reject."""
    if not 0 <= axis < NUM_AXES:
        raise ValueError(f"axis must be 0..{NUM_AXES - 1}, got {axis}")
    if not 0 <= lo <= ADC_MAX or not 0 <= hi <= ADC_MAX:
        raise ValueError(f"values must be 0..{ADC_MAX}, got {lo}/{hi}")
    if lo >= hi:
        raise ValueError(f"min ({lo}) must be below max ({hi})")
    return f"SET {axis} {lo} {hi}"


def cmd_save() -> str:
    return "SAVE"


def cmd_load() -> str:
    return "LOAD"


def cmd_stream(enabled: bool) -> str:
    return f"STREAM {1 if enabled else 0}"


# --------------------------------------------------------------------------
# Shared maths - the firmware does exactly the same thing
# --------------------------------------------------------------------------


def scale(raw: int, lo: int, hi: int) -> float:
    """Map a raw reading onto 0.0 - 1.0 using the calibration, clamped."""
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (raw - lo) / (hi - lo)))
