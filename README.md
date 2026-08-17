# Sim Pedal Calibrator

A small Python app that finds your pedal controller on a COM port, shows what
each pedal is actually reading, and lets you set the min and max point of each
one. The calibration is stored on the device, so it survives unplugging.

![screenshot](docs/screenshot.png)

There is a **built-in simulator**, so you can download this and click around
before you have any hardware wired up.

## What's in here

| Path | What it is |
|---|---|
| `pedalcal/` | The desktop app (Python + Tkinter) |
| `firmware/pedal_firmware/` | Arduino sketch for the pedal controller |
| `docs/PROTOCOL.md` | The serial protocol, if you want to talk to the device yourself |
| `tests/` | Protocol tests plus a headless GUI smoke test |

## Try it without hardware

Requires **Python 3.10 or newer**.

```bash
git clone https://github.com/YOUR-USERNAME/sim-pedal-calibrator.git
cd sim-pedal-calibrator
pip install -r requirements.txt
python -m pedalcal --simulate
```

Three fake pedals will start sweeping. Everything in the UI works.

To see the real ports on your machine:

```bash
python -m pedalcal --list
```

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

1. Plug the board in and run `python -m pedalcal`.
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

### What the bar shows

The dark bar is the sensor's whole 0–1023 range. The blue block is the part
you calibrated as usable, and the white line is where the pedal is right now.
The progress bar underneath is what a game would actually see.

## Building a Windows .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PedalCalibrator run_app.py
```

The result is `dist/PedalCalibrator.exe`, a single file with no Python
install needed. The included GitHub Actions workflow does this automatically
and attaches the .exe to a release whenever you push a `v*` tag.

## Running the tests

```bash
pip install pytest
pytest tests -q                                    # protocol tests
python tests/smoke_gui.py                          # drives the real GUI
```

## License

MIT — see [LICENSE](LICENSE).
