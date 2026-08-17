"""Finding COM ports and talking to the pedal device.

Serial reads happen on a background thread and land in a queue; the GUI drains
that queue from its own event loop. Tkinter is not thread-safe, so no widget is
ever touched from the reader thread.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

from . import protocol as P
from .simulator import SIMULATOR_PORT, SimulatedSerial


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str

    def __str__(self) -> str:
        return f"{self.device} - {self.description}"


def list_serial_ports(include_simulator: bool = True) -> list[PortInfo]:
    """Every serial port the OS knows about, newest-looking first.

    On Windows these are COM1, COM3...; on Linux /dev/ttyACM0, /dev/ttyUSB0;
    on macOS /dev/cu.usbmodem*. The simulator is appended so the app is always
    usable without hardware.
    """
    ports = [
        PortInfo(p.device, p.description or "unknown device")
        for p in sorted(list_ports.comports(), key=lambda p: p.device)
    ]
    if include_simulator:
        ports.append(PortInfo(SIMULATOR_PORT, "built-in simulator, no hardware"))
    return ports


class PedalDevice:
    """An open connection to the pedal firmware (or to the simulator)."""

    def __init__(self, port: str, baud: int = P.BAUD) -> None:
        self.port = port
        self.baud = baud
        self._ser: serial.Serial | SimulatedSerial | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._inbox: queue.Queue[P.Message] = queue.Queue()

    # -- lifecycle -------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", False)

    def open(self) -> None:
        if self.port == SIMULATOR_PORT:
            self._ser = SimulatedSerial()
        else:
            self._ser = serial.Serial(self.port, self.baud, timeout=0.2)
            # Most Arduino boards reset when the port opens; give the
            # bootloader a moment before we expect sensible replies.
            time.sleep(2.0)
            self._ser.reset_input_buffer()

        self._stop.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    # -- traffic ---------------------------------------------------------

    def send(self, line: str) -> None:
        if self._ser is None:
            raise RuntimeError("not connected")
        self._ser.write((line + "\n").encode("ascii"))

    def poll(self) -> list[P.Message]:
        """Every message received since the last call. Never blocks."""
        out: list[P.Message] = []
        while True:
            try:
                out.append(self._inbox.get_nowait())
            except queue.Empty:
                return out

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                chunk = self._ser.readline()  # type: ignore[union-attr]
            except Exception as exc:
                self._inbox.put(P.Unknown(f"[serial error] {exc}"))
                return
            if not chunk:
                continue
            text = chunk.decode("ascii", errors="replace")
            self._inbox.put(P.parse_line(text))
