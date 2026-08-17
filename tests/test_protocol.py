import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pedalcal import protocol as P
from pedalcal.device import explain_port_error
from fake_device import FakeSerial


def test_parses_identity():
    assert P.parse_line("PEDALCAL 1") == P.Ident(1)


def test_parses_data_frame():
    assert P.parse_line("D 100 200 300") == P.Data((100, 200, 300))


def test_parses_calibration():
    msg = P.parse_line("C 10 900 20 800 30 700")
    assert msg == P.Calibration(((10, 900), (20, 800), (30, 700)))


def test_parses_acks():
    assert P.parse_line("OK") == P.Ack(True)
    assert P.parse_line("ERR range") == P.Ack(False, "range")


@pytest.mark.parametrize("junk", ["", "D 1 2", "D x y z", "hello", "C 1 2"])
def test_garbage_never_raises(junk):
    P.parse_line(junk)  # must not raise


def test_cmd_set_validates():
    assert P.cmd_set(0, 100, 900) == "SET 0 100 900"
    with pytest.raises(ValueError):
        P.cmd_set(9, 0, 100)      # no such axis
    with pytest.raises(ValueError):
        P.cmd_set(0, 900, 100)    # min above max
    with pytest.raises(ValueError):
        P.cmd_set(0, 0, 5000)     # beyond ADC range


def test_scale_clamps():
    assert P.scale(100, 100, 900) == 0.0
    assert P.scale(900, 100, 900) == 1.0
    assert P.scale(500, 100, 900) == pytest.approx(0.5)
    assert P.scale(50, 100, 900) == 0.0     # below min
    assert P.scale(1000, 100, 900) == 1.0   # above max
    assert P.scale(500, 500, 500) == 0.0    # degenerate range


@pytest.mark.parametrize("message, expected", [
    # what pyserial actually raises on Windows when another app holds the port
    ("could not open port 'COM4': PermissionError(13, 'Access is denied.')",
     "Arduino IDE"),
    # ...and on Linux without dialout membership
    ("[Errno 13] could not open port /dev/ttyACM0: Permission denied",
     "dialout"),
    ("could not open port COM9: FileNotFoundError(2, 'cannot find the file')",
     "Refresh"),
])
def test_port_errors_get_actionable_advice(message, expected):
    assert expected in explain_port_error(OSError(message))


def test_unknown_port_error_still_returns_something():
    assert explain_port_error(RuntimeError("kaboom")).strip()


def _replies(sim: FakeSerial, command: str) -> list[P.Message]:
    """Every non-streaming message the device sends back to one command.

    GET answers with two lines (calibration and axis state), so this drains
    the reply rather than grabbing the first line and leaving the rest to
    confuse the next command.
    """
    sim.write((command + "\n").encode())
    out: list[P.Message] = []
    for _ in range(60):
        msg = P.parse_line(sim.readline().decode())
        if isinstance(msg, P.Data):
            if out:
                return out          # stream resumed: the reply is complete
            continue
        if isinstance(msg, P.Unknown) and not msg.text:
            continue
        out.append(msg)
    if out:
        return out
    raise AssertionError(f"no reply to {command!r}")


def _exchange(sim: FakeSerial, command: str) -> P.Message:
    return _replies(sim, command)[0]


def test_percent_round_trip():
    for pct in (0, 1, 12, 50, 86, 99, 100):
        assert P.raw_to_pct(P.pct_to_raw(pct)) == pct
    assert P.raw_to_pct(-5) == 0 and P.raw_to_pct(99999) == 100
    assert P.pct_to_raw(-5) == 0 and P.pct_to_raw(150) == P.ADC_MAX


def test_enable_commands():
    assert P.cmd_enable(2, False) == "EN 2 0"
    assert P.cmd_enable(0, True) == "EN 0 1"
    with pytest.raises(ValueError):
        P.cmd_enable(7, True)
    assert P.parse_line("E 1 1 0") == P.Enabled((True, True, False))


def test_disabled_axis_reports_zero():
    """The whole point: an unused pin must not mirror its neighbour."""
    sim = FakeSerial()
    assert _exchange(sim, "EN 2 0") == P.Ack(True)
    for _ in range(80):
        msg = P.parse_line(sim.readline().decode())
        if isinstance(msg, P.Data):
            assert msg.raw[2] == 0, "disabled axis still streaming a signal"
            assert msg.raw[0] > 0 or msg.raw[1] > 0
            return
    raise AssertionError("no data frames arrived")


def test_simulator_speaks_the_protocol():
    sim = FakeSerial()
    assert _exchange(sim, "ID?") == P.Ident(P.PROTOCOL_VERSION)
    assert _exchange(sim, "SET 1 111 888") == P.Ack(True)
    cal, enabled = _replies(sim, "GET")
    assert isinstance(cal, P.Calibration)
    assert cal.points[1] == (111, 888)
    assert enabled == P.Enabled.all_on()
    assert _exchange(sim, "SET 1 900 100") == P.Ack(False, "range")
    assert _exchange(sim, "NONSENSE") == P.Ack(False, "unknown_command")


def test_simulator_streams_data_in_range():
    sim = FakeSerial()
    frames = 0
    for _ in range(200):
        msg = P.parse_line(sim.readline().decode())
        if isinstance(msg, P.Data):
            frames += 1
            assert len(msg.raw) == P.NUM_AXES
            assert all(0 <= v <= P.ADC_MAX for v in msg.raw)
        if frames >= 5:
            return
    raise AssertionError("simulator did not stream data")
