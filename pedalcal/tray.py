"""System tray icon.

Optional by design. pystray needs a platform tray backend - present on
Windows and macOS, and on Linux only with GTK/AppIndicator available - so the
import is allowed to fail and the app carries on without the feature rather
than refusing to start.
"""

from __future__ import annotations

import base64
import io
import threading

_IMPORT_ERROR = ""

try:  # pragma: no cover - depends entirely on the host platform
    import pystray
    from PIL import Image

    _AVAILABLE = True
except Exception as exc:  # noqa: BLE001 - any failure means "no tray here"
    _AVAILABLE = False
    _IMPORT_ERROR = str(exc)


def available() -> bool:
    return _AVAILABLE


def unavailable_reason() -> str:
    if _AVAILABLE:
        return ""
    return _IMPORT_ERROR or "no system tray on this platform"


class Tray:
    """A tray icon with Show and Quit.

    pystray's run() blocks, so it lives on its own thread. The callbacks fire
    on that thread - never touch Tk from them directly, hand the work back to
    the main loop with root.after().
    """

    def __init__(self, icon_png_b64: str, on_show, on_quit,
                 title: str = "Lord3D Pedal Calibrator") -> None:
        self.icon_png_b64 = icon_png_b64
        self.on_show = on_show
        self.on_quit = on_quit
        self.title = title
        self._icon = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if not _AVAILABLE or self._icon is not None:
            return False
        try:
            image = Image.open(io.BytesIO(base64.b64decode(self.icon_png_b64)))
            menu = pystray.Menu(
                pystray.MenuItem("Show", lambda *_: self.on_show(),
                                 default=True),
                pystray.MenuItem("Quit", lambda *_: self.on_quit()),
            )
            self._icon = pystray.Icon("pedalcal", image, self.title, menu)
            self._thread = threading.Thread(target=self._icon.run, daemon=True)
            self._thread.start()
            return True
        except Exception:  # noqa: BLE001
            self._icon = None
            return False

    def stop(self) -> None:
        icon, self._icon = self._icon, None
        if icon is not None:
            try:
                icon.stop()
            except Exception:  # noqa: BLE001
                pass
        self._thread = None

    @property
    def running(self) -> bool:
        return self._icon is not None
