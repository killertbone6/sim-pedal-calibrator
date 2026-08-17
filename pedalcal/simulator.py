"""A fake pedal device.

Lets you run and develop the app with no hardware plugged in. It exposes the
handful of methods :class:`pedalcal.device.PedalDevice` actually uses from
``serial.Serial``, and speaks the same protocol as the Arduino firmware.
"""

from __future__ import annotations

import math
import time
from collections import deque

from . import protocol as P

#: Shown in the port dropdown so you can always try the app without hardware.
SIMULATOR_PORT = "SIMULATOR"

_STREAM_HZ = 50.0


class SimulatedSerial:
    """Pretends to be a ``serial.Serial`` object connected to pedal firmware."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.is_open = True
        self._outbox: deque[bytes] = deque()
        self._cal = [(120, 880), (200, 950), (100, 800)]
        self._streaming = True
        self._next_frame = time.monotonic()
        self._t0 = time.monotonic()

    # -- the bits PedalDevice needs -------------------------------------

    def write(self, payload: bytes) -> int:
        for line in payload.decode("ascii", "replace").splitlines():
            self._handle(line.strip())
        return len(payload)

    def readline(self) -> bytes:
        """Block briefly, then return one line (or b"" on timeout)."""
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            if self._outbox:
                return self._outbox.popleft()
            now = time.monotonic()
            if self._streaming and now >= self._next_frame:
                self._next_frame = now + 1.0 / _STREAM_HZ
                return self._frame()
            time.sleep(0.002)
        return b""

    def close(self) -> None:
        self.is_open = False

    def reset_input_buffer(self) -> None:
        self._outbox.clear()

    # -- internals -------------------------------------------------------

    def _emit(self, line: str) -> None:
        self._outbox.append((line + "\n").encode("ascii"))

    def _frame(self) -> bytes:
        """Three pedals sweeping at different rates, with a little noise."""
        t = time.monotonic() - self._t0
        raw = []
        for i, (lo, hi) in enumerate(self._cal):
            wave = 0.5 - 0.5 * math.cos(t * (0.8 + 0.35 * i))
            span = hi - lo
            value = lo + wave * span
            value += math.sin(t * 37.0 + i) * 1.5  # a touch of sensor noise
            raw.append(int(max(0, min(P.ADC_MAX, round(value)))))
        return f"D {raw[0]} {raw[1]} {raw[2]}\n".encode("ascii")

    def _cal_line(self) -> str:
        flat = " ".join(f"{lo} {hi}" for lo, hi in self._cal)
        return f"C {flat}"

    def _handle(self, line: str) -> None:
        if not line:
            return
        parts = line.split()
        cmd = parts[0].upper()

        if cmd == "ID?":
            self._emit(f"{P.FIRMWARE_ID} {P.PROTOCOL_VERSION}")
        elif cmd in ("GET", "LOAD"):
            self._emit(self._cal_line())
        elif cmd == "SET" and len(parts) == 4:
            try:
                axis, lo, hi = int(parts[1]), int(parts[2]), int(parts[3])
            except ValueError:
                self._emit("ERR bad_number")
                return
            if not 0 <= axis < P.NUM_AXES or lo >= hi:
                self._emit("ERR range")
                return
            self._cal[axis] = (lo, hi)
            self._emit("OK")
        elif cmd == "SAVE":
            self._emit("OK")
        elif cmd == "STREAM" and len(parts) == 2:
            self._streaming = parts[1] != "0"
            self._emit("OK")
        else:
            self._emit("ERR unknown_command")
