"""Regenerate the app icon.

Writes docs/icon.png (source), docs/icon.ico (used for the .exe) and
pedalcal/icon_data.py (embedded in the app for the window icon).

    pip install pillow
    python tools/make_icon.py
"""

import base64
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
S = 1024

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=(31, 35, 42, 255))

pad, gap = int(S * 0.18), int(S * 0.07)
usable = S - 2 * pad
bw = (usable - 2 * gap) // 3
base = S - pad
for i, (h, col) in enumerate(zip(
    [0.34, 0.60, 0.86],
    [(123, 160, 200, 255), (78, 133, 190, 255), (110, 200, 140, 255)],
)):
    x0 = pad + i * (bw + gap)
    d.rounded_rectangle([x0, base - int(usable * h), x0 + bw, base],
                        radius=int(bw * 0.28), fill=col)

img.save(ROOT / "docs" / "icon.png")
img.save(ROOT / "docs" / "icon.ico",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

small = ROOT / "docs" / "_icon256.png"
img.resize((256, 256), Image.LANCZOS).save(small, optimize=True)
b64 = base64.b64encode(small.read_bytes()).decode()
small.unlink()

body = "\n".join('    "%s"' % line for line in textwrap.wrap(b64, 76))
(ROOT / "pedalcal" / "icon_data.py").write_text(
    '"""The app icon, embedded as base64 PNG.\n\n'
    "Keeping it in a .py file rather than a separate image means a PyInstaller\n"
    "one-file build has no data files to bundle and no runtime paths to resolve.\n"
    "Regenerate from docs/icon.png with tools/make_icon.py.\n"
    '"""\n\nICON_PNG_B64 = (\n' + body + "\n)\n"
)
print("icon regenerated")
