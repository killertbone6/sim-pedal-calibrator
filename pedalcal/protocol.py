"""The line protocol spoken between this app and the pedal firmware.

Everything is plain ASCII text, one message per line, terminated with "\\n".
That makes it trivial to debug: open the Arduino IDE's Serial Monitor at
115200 baud and you can type these commands by hand.

PC  ->  device
    ID?                     ask what is on the other end
    GET                     ask for the stored calibration
    SET <axis> <min> <max>  set calibration for one axis (applied immediately)
    EN <axis> <0|1>         mark an axis as unused / in use
    CURVE <axis> <-100..100>  response curve; 0 is linear, negative gives more
                            output early, positive softens the first half
    DZ <axis> <0..30>       deadzone, as a percentage of travel above rest
    SM <axis> <0|1>         noise filtering on / off for one axis
    RATE <hz>               how often to stream D frames, 1..200
    SAVE                    write the current calibration to EEPROM
    LOAD                    re-read the calibration from EEPROM
    STREAM <0|1>            turn the live value stream off / on

device -> PC
    PEDALCAL <version> [hid|nohid]  identity banner (reply to ID?); the third
                                field says whether the board is presenting
                                itself to the OS as a game controller
    D <raw0> <raw1> <raw2>      live raw ADC values, ~50 per second
    C <min0> <max0> ... <max2>  the current calibration (reply to GET / LOAD)
    E <en0> <en1> <en2>         which axes are in use (reply to GET / LOAD)
    L <lin0> <lin1> <lin2>      response curve per axis (reply to GET / LOAD)
    Z <dz0> <dz1> <dz2>         deadzone per axis (reply to GET / LOAD)
    M <sm0> <sm1> <sm2>         filtering per axis (reply to GET / LOAD)
    OK                          command accepted
    ERR <reason>                command rejected
"""

from __future__ import annotations

from dataclasses import dataclass

BAUD = 115200
FIRMWARE_ID = "PEDALCAL"
PROTOCOL_VERSION = 5

AXIS_NAMES = ("Throttle", "Brake", "Clutch")
NUM_AXES = len(AXIS_NAMES)

#: Arduino's analogRead() is 10-bit, so raw values run 0..1023.
ADC_MAX = 1023

#: Response curve limits. 0 is a straight line; negative gives more output for
#: the same pedal travel (twitchier), positive gives less (gentler).
CURVE_MAX = 100

#: Deadzone is a percentage of travel ignored just off the rest position.
DEADZONE_MAX = 30


# --------------------------------------------------------------------------
# Messages coming from the device
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Ident:
    """Reply to ``ID?`` - confirms we are talking to pedal firmware.

    ``hid`` is True when the board also appears to the operating system as a
    game controller, False when it doesn't, and None for older firmware that
    predates the flag. Calibrating works either way, but only a board with
    native USB can feed the axes to a game.
    """

    version: int
    hid: bool | None = None


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
class Enabled:
    """Which pedals are actually wired up.

    An analog pin with nothing on it doesn't read zero - it floats, and the
    ADC's sample-and-hold leaks the previous channel's voltage into it, so an
    unused clutch input mirrors the brake. Telling the firmware an axis is
    unused makes it report a hard 0 instead of that ghost signal.
    """

    axes: tuple[bool, ...]

    @staticmethod
    def all_on() -> "Enabled":
        return Enabled(tuple(True for _ in range(NUM_AXES)))


@dataclass(frozen=True)
class Linearity:
    """The response curve of each pedal, -100 to +100. 0 is a straight line."""

    axes: tuple[int, ...]

    @staticmethod
    def flat() -> "Linearity":
        return Linearity(tuple(0 for _ in range(NUM_AXES)))


@dataclass(frozen=True)
class Deadzone:
    """Travel ignored just off rest, as a percentage, per axis."""

    axes: tuple[int, ...]

    @staticmethod
    def none() -> "Deadzone":
        return Deadzone(tuple(0 for _ in range(NUM_AXES)))


@dataclass(frozen=True)
class Smoothing:
    """Whether the noise filter is on, per axis."""

    axes: tuple[bool, ...]

    @staticmethod
    def all_on() -> "Smoothing":
        return Smoothing(tuple(True for _ in range(NUM_AXES)))


@dataclass(frozen=True)
class Ack:
    """``OK`` or ``ERR <reason>``."""

    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class Unknown:
    """Anything we did not recognise - shown in the log, never fatal."""

    text: str


Message = (Ident | Data | Calibration | Enabled | Linearity | Deadzone
           | Smoothing | Ack | Unknown)


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
            hid = None
            if len(parts) > 2:
                hid = parts[2].lower() == "hid"
            return Ident(version, hid)

        if tag == "D" and len(parts) == NUM_AXES + 1:
            return Data(tuple(int(p) for p in parts[1:]))

        if tag == "C" and len(parts) == NUM_AXES * 2 + 1:
            numbers = [int(p) for p in parts[1:]]
            pairs = tuple(
                (numbers[i], numbers[i + 1]) for i in range(0, len(numbers), 2)
            )
            return Calibration(pairs)

        if tag == "E" and len(parts) == NUM_AXES + 1:
            return Enabled(tuple(p != "0" for p in parts[1:]))

        if tag == "L" and len(parts) == NUM_AXES + 1:
            return Linearity(tuple(
                max(-CURVE_MAX, min(CURVE_MAX, int(p))) for p in parts[1:]))

        if tag == "Z" and len(parts) == NUM_AXES + 1:
            return Deadzone(tuple(
                max(0, min(DEADZONE_MAX, int(p))) for p in parts[1:]))

        if tag == "M" and len(parts) == NUM_AXES + 1:
            return Smoothing(tuple(p != "0" for p in parts[1:]))

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


def cmd_enable(axis: int, on: bool) -> str:
    if not 0 <= axis < NUM_AXES:
        raise ValueError(f"axis must be 0..{NUM_AXES - 1}, got {axis}")
    return f"EN {axis} {1 if on else 0}"


def cmd_curve(axis: int, linearity: int) -> str:
    if not 0 <= axis < NUM_AXES:
        raise ValueError(f"axis must be 0..{NUM_AXES - 1}, got {axis}")
    if not -CURVE_MAX <= linearity <= CURVE_MAX:
        raise ValueError(f"linearity must be {-CURVE_MAX}..{CURVE_MAX}, "
                         f"got {linearity}")
    return f"CURVE {axis} {linearity}"


def cmd_deadzone(axis: int, percent: int) -> str:
    if not 0 <= axis < NUM_AXES:
        raise ValueError(f"axis must be 0..{NUM_AXES - 1}, got {axis}")
    if not 0 <= percent <= DEADZONE_MAX:
        raise ValueError(f"deadzone must be 0..{DEADZONE_MAX}, got {percent}")
    return f"DZ {axis} {percent}"


def cmd_smoothing(axis: int, on: bool) -> str:
    if not 0 <= axis < NUM_AXES:
        raise ValueError(f"axis must be 0..{NUM_AXES - 1}, got {axis}")
    return f"SM {axis} {1 if on else 0}"


def cmd_rate(hz: int) -> str:
    if not 1 <= hz <= 200:
        raise ValueError(f"stream rate must be 1..200 Hz, got {hz}")
    return f"RATE {hz}"


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


def raw_to_pct(raw: int) -> int:
    """Sensor reading as a percentage of its full travel.

    The UI works entirely in percentages - "my brake rests at 12% and bottoms
    out at 86%" is something you can reason about, where "raw 123 to 880"
    is an implementation detail of a 10-bit ADC.
    """
    return round(max(0, min(ADC_MAX, raw)) / ADC_MAX * 100)


def pct_to_raw(pct: float) -> int:
    """The inverse of raw_to_pct, for talking to the firmware."""
    return round(max(0.0, min(100.0, pct)) / 100 * ADC_MAX)


def curve_gamma(linearity: int) -> float:
    """Turn the -100..100 slider into an exponent.

    +-50 lands on a half or double exponent, which is about as far as anyone
    sensibly goes; the ends give 4.0 and 0.25 for the truly committed.
    """
    return 2.0 ** (max(-CURVE_MAX, min(CURVE_MAX, int(linearity))) / 50.0)


def apply_curve(value: int, linearity: int) -> int:
    """Shape an already-calibrated 0..ADC_MAX value.

    This was a lookup table with interpolation, on the reasoning that an 8-bit
    micro shouldn't run pow() a few hundred times a second. Measuring it
    settled the argument: at the extremes the curve is near-vertical off the
    bottom - the gradient of x**0.25 is infinite at zero - so a table with
    evenly spaced points was out by as much as 20% in the first segment, and
    no sane number of points fixes that, because the error only shrinks with
    the fourth root of the point count. Those errors were also what made the
    drawn line look notched.

    A 16 MHz AVR gets through pow() in a couple of hundred microseconds, so
    three of them per 5 ms tick costs low single-digit percent of the loop.
    Exactness is worth far more than those cycles.
    """
    value = max(0, min(ADC_MAX, value))
    if linearity == 0:
        return value
    # int(x + 0.5), not round(): round() is banker's rounding in Python and
    # would disagree with the firmware's C cast on exact halves.
    return int(ADC_MAX * (value / ADC_MAX) ** curve_gamma(linearity) + 0.5)


def apply_calibration(raw: int, lo: int, hi: int) -> int:
    """Map a raw reading onto 0..ADC_MAX using the calibration points.

    Written as integer arithmetic that the firmware mirrors exactly, rather
    than a float version that merely agrees to within a count. The difference
    is not academic: a curve at its extreme setting has an almost vertical
    gradient just off zero, so one count of disagreement here came out as
    sixteen counts of disagreement in the output.
    """
    if hi <= lo or raw <= lo:
        return 0
    if raw >= hi:
        return ADC_MAX
    span = hi - lo
    return ((raw - lo) * ADC_MAX + span // 2) // span


def apply_deadzone(value: int, deadzone: int) -> int:
    """Ignore the first few percent of travel, then stretch what's left.

    Rescaling matters: without it a 5% deadzone would also cost you 5% off the
    top, and the pedal would never reach 100%.
    """
    if deadzone <= 0:
        return value
    threshold = (max(0, min(DEADZONE_MAX, deadzone)) * ADC_MAX) // 100
    if value <= threshold:
        return 0
    span = ADC_MAX - threshold
    return min(ADC_MAX, ((value - threshold) * ADC_MAX + span // 2) // span)


def pedal_output(raw: int, lo: int, hi: int, linearity: int = 0,
                 deadzone: int = 0) -> float:
    """The whole chain - calibrate, deadzone, then shape - as 0.0-1.0.

    This is what the game receives, so it's also what the app shows. The
    firmware performs these three steps in exactly this order.
    """
    value = apply_calibration(raw, lo, hi)
    value = apply_deadzone(value, deadzone)
    return apply_curve(value, linearity) / ADC_MAX


def curve_ideal(fraction: float, linearity: int) -> float:
    """The smooth curve the lookup table approximates, for drawing.

    The table is what the board evaluates and it is accurate to a fraction of
    a percent, but plotting it directly puts a visible kink at every table
    point. Drawing the underlying function instead gives a clean line that
    still describes what the hardware does.
    """
    return max(0.0, min(1.0, fraction)) ** curve_gamma(linearity)
