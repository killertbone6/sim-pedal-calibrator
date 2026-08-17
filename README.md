# Sim Pedal Calibrator

A small app that finds your pedal controller on a COM port, shows what each
pedal is actually reading, and lets you set the min and max point of each one.
The calibration is stored on the device, so it survives unplugging.

![screenshot](docs/screenshot.png)

Dark and light themes, six accent colours, and your choice is remembered.

## Download (Windows)

**[Get PedalCalibrator.exe from the Releases page →](../../releases/latest)**

One file. Nothing to install, no Python needed. Download it, double-click it,
done.

> Windows may show a blue **"Windows protected your PC"** box the first time.
> Click **More info → Run anyway**. That appears for any program that hasn't
> been code-signed, which costs a few hundred dollars a year — most small
> open-source tools skip it.

There's a **built-in simulator** in the port dropdown, so you can click through
the whole app before you've wired up any hardware.

## Run from source

For development, or on macOS and Linux. Needs **Python 3.10+** — get it from
[python.org/downloads](https://www.python.org/downloads/) and tick
**"Add python.exe to PATH"** on the first installer screen.

**Windows:** double-click `Run Simulator.bat` (fake pedals) or
`Run Calibrator.bat` (real hardware). They install the one dependency on first
run.

**macOS / Linux:** `./run.sh --simulate`

**Any platform, from a terminal:**

```bash
pip install -r requirements.txt
python -m pedalcal --simulate      # fake pedals
python -m pedalcal                 # real hardware
python -m pedalcal --list          # just print the ports found
```

## What's in here

| Path | What it is |
|---|---|
| `pedalcal/` | The desktop app (Python + Tkinter) |
| `firmware/pedal_firmware/` | Arduino sketch for the pedal controller |
| `docs/PROTOCOL.md` | The serial protocol, if you want to talk to the device yourself |
| `tests/` | Protocol tests plus a headless GUI smoke test |

## The hardware side

Any Arduino works. If you want the pedals to show up as a **game controller**
in Windows, use a board with native USB — Leonardo, Pro Micro, Micro, or a
Teensy. An Uno or Nano cannot do that, but it can still stream values to this
app.

### Wiring, per pedal

Each pedal needs a sensor that outputs a voltage: a potentiometer, a hall
sensor, or a load cell with an amplifier board.

```
   5V  ─────── sensor VCC   (or pot outer leg 1)
   GND ─────── sensor GND   (or pot outer leg 2)
   A0  ─────── sensor OUT   (or pot wiper)   →  Throttle
   A1  ─────── sensor OUT                    →  Brake
   A2  ─────── sensor OUT                    →  Clutch
```

You do not need all three — unused pins just read noise, and you can drop
`NUM_AXES` in the sketch if you only have two pedals.

### Flashing the firmware

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. Open `firmware/pedal_firmware/pedal_firmware.ino`.
3. *(Optional, native-USB boards only)* Tools → Manage Libraries → search
   **Joystick** → install "Joystick" by Matthew Heironimus. Then uncomment
   `#define USE_JOYSTICK` near the top of the sketch.
4. Tools → Board / Port → pick your board.
5. Click Upload.

## Calibrating

1. Plug the board in and open the app.
2. Pick the port. On Windows it's usually the one described as *Arduino* or
   *USB Serial Device*; on Linux `/dev/ttyACM0`; on macOS `/dev/cu.usbmodem…`.
3. **Connect**. The status line should say `pedal firmware v1`.
4. Click **Learn range**, press every pedal all the way down and let it back
   up a couple of times, then click **Stop learning**. The min and max boxes
   fill in from what it saw.
   *Or* set them by hand: rest your foot off the pedal and click **Use
   current** next to Min, press it fully and click **Use current** next to Max.
5. Check the percentage readouts — resting should be 0%, fully pressed 100%.
6. Click **Save to device** to write it to EEPROM.

A tip on brakes: don't set Max at the absolute hardest you can press. Set it
where you want 100% braking to happen, which is usually a bit before the pedal
physically stops.

### What the meter shows

The track is the sensor's whole 0–1023 range, marked off in 10% steps. The
tinted block is the part you've calibrated as usable, the solid accent fill is
how far into that range the pedal currently is, and the bright line is the raw
reading. The big number on the right is what a game would actually see.

## Appearance

Click **THEME** in the top right for the theme row: dark or light, plus six
accent colours. The choice is written to `.pedalcal.json` in your user folder
and restored next launch.

Everything is drawn on a canvas rather than using stock Tk widgets, so it looks
identical on Windows, macOS and Linux. If you want colours of your own, edit
`DARK`, `LIGHT` or the `ACCENTS` list in `pedalcal/theme.py` — a palette is
just a dataclass of hex strings, and bright accents are darkened automatically
on the light theme so they stay readable.

## Troubleshooting

**"Another program already has this port open" / Access is denied.**
Only one program can hold a serial port at a time. Close the Arduino IDE's
**Serial Monitor** — that's the cause nine times out of ten. Also close any
second copy of this app, and any other pedal or telemetry software. On Linux,
add yourself to the `dialout` group instead:
`sudo usermod -a -G dialout $USER`, then log out and back in.

**"Connected, but no reply — is the firmware flashed?"**
The port opened but nothing identified itself. Either the sketch isn't
uploaded yet, or you picked the wrong port. Check by opening the Arduino IDE's
Serial Monitor at **115200 baud** — you should see a stream of `D 512 400 300`
lines. If you see nothing, or unreadable characters, re-upload the sketch and
make sure the Serial Monitor's baud rate is 115200.

**The window freezes for a second or two when connecting.** Expected. Most
Arduino boards reboot when a program opens their serial port, so the app waits
for the bootloader before it starts talking. The window stays responsive and
the button says "Cancel" while it happens.

**The app closes by itself.** It writes what happened to `pedalcal.log` in your
user folder (`C:\Users\<you>\pedalcal.log` on Windows). Open it — the last few
lines will say what failed. That file also records every connection attempt,
which is handy when a port misbehaves.

**Which COM port is it?** Unplug the board, look at the port list, plug it back
in and hit Refresh — the one that appears is yours. Windows sometimes hands out
a different COM number after a reconnect.

## Publishing a release

The included GitHub Actions workflow runs the tests, builds the Windows .exe,
and attaches it to a release — all on GitHub's machines, so you don't need
Python or Windows locally.

```bash
git tag v0.1.0
git push --tags
```

Watch it under the **Actions** tab. A few minutes later the .exe is on your
Releases page. Bump the version number for each new release.

To build one yourself instead:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PedalCalibrator --icon docs/icon.ico run_app.py
```

## Running the tests

```bash
pip install pytest
python -m pytest tests -q    # protocol tests
python tests/smoke_gui.py    # drives the real GUI against the simulator
```

## License

MIT — see [LICENSE](LICENSE).
