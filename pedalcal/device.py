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


@dataclass(frozen=True)
class PortInfo:
    device: str
    description: str

    def __str__(self) -> str:
        return f"{self.device} - {self.description}"


def explain_port_error(exc: BaseException) -> str:
    """Turn a pyserial exception into something a human can act on."""
    text = str(exc)
    low = text.lower()

    if "access is denied" in low or "permission" in low or "errno 13" in low:
        return (
            "Another program already has this port open.\n\n"
            "The usual culprit is the Arduino IDE - close its Serial Monitor, "
            "or close the IDE entirely. Also close any second copy of this app, "
            "and any other pedal or telemetry tool that might be holding the "
            "port.\n\n"
            "On Linux you may instead need to add yourself to the dialout "
            "group:  sudo usermod -a -G dialout $USER  (then log out and back in)."
        )
    if "could not open port" in low or "filenotfounderror" in low or "no such" in low:
        return (
            "That port isn't there any more.\n\n"
            "Unplug the board, plug it back in, click Refresh, and pick the "
            "port again - Windows sometimes assigns a different COM number."
        )
    if "device reports readiness" in low or "handle is invalid" in low:
        return (
            "The driver accepted the port but the device isn't responding.\n\n"
            "Unplug and replug the board, then try again."
        )
    return "The serial port could not be opened."


def list_serial_ports() -> list[PortInfo]:
    """Every serial port the OS knows about.

    On Windows these are COM1, COM3...; on Linux /dev/ttyACM0, /dev/ttyUSB0;
    on macOS /dev/cu.usbmodem*.
    """
    return [
        PortInfo(p.device, p.description or "unknown device")
        for p in sorted(list_ports.comports(), key=lambda p: p.device)
    ]


class PedalDevice:
    """An open connection to the pedal firmware."""

    def __init__(self, port: str, baud: int = P.BAUD, transport=None) -> None:
        """`transport` swaps in a stand-in for serial.Serial - the test suite
        uses it to run the whole app against a fake board."""
        self.port = port
        self.baud = baud
        self._open_transport = transport or self._open_serial
        self._ser = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._inbox: queue.Queue[P.Message] = queue.Queue()

    # -- lifecycle -------------------------------------------------------

    @property
    def is_open(self) -> bool:
        return self._ser is not None and getattr(self._ser, "is_open", False)

    def _open_serial(self, port: str, baud: int):
        ser = serial.Serial(port, baud, timeout=0.2)
        # Most Arduino boards reset when the port opens; give the bootloader a
        # moment before we expect sensible replies.
        time.sleep(2.0)
        ser.reset_input_buffer()
        return ser

    def open(self) -> None:
        self._ser = self._open_transport(self.port, self.baud)
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
