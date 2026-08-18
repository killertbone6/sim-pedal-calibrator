# Serial protocol — Lord3D pedal firmware

Plain ASCII, one message per line, terminated with `\n`, at **115200 baud**.

Because it is text, you can drive the device by hand: open the Arduino IDE's
Serial Monitor at 115200, set the line ending to "Newline", and type commands.

Axis numbers are `0 = throttle`, `1 = brake`, `2 = clutch`.
Raw values are 10-bit, so `0`–`1023`.

## App → device

| Command | Meaning | Reply |
|---|---|---|
| `ID?` | Who is there? | `PEDALCAL <version>` |
| `GET` | Report the whole configuration | `C ...`, `E ...`, `L ...`, `Z ...`, `M ...` |
| `SET <axis> <min> <max>` | Set one axis, applied immediately (not saved) | `OK` / `ERR ...` |
| `EN <axis> <0\|1>` | Mark an axis as unused / in use | `OK` / `ERR ...` |
| `CURVE <axis> <-100..100>` | Response curve; 0 is linear | `OK` / `ERR ...` |
| `DZ <axis> <0..30>` | Deadzone, percent of travel above rest | `OK` / `ERR ...` |
| `SM <axis> <0\|1>` | Noise filtering on / off for one axis | `OK` / `ERR ...` |
| `RATE <hz>` | How often to stream `D` frames, 1-200 | `OK` / `ERR ...` |
| `SAVE` | Write current calibration to EEPROM | `OK` |
| `LOAD` | Re-read everything from EEPROM | `C ...`, `E ...`, `L ...`, `Z ...`, `M ...` |
| `STREAM <0\|1>` | Stop / start the live value stream | `OK` |

## Device → app

| Message | Meaning |
|---|---|
| `PEDALCAL 5` | Identity banner, protocol version 5 |
| `D <raw0> <raw1> <raw2>` | Live raw readings, sent ~50×/second |
| `C <min0> <max0> <min1> <max1> <min2> <max2>` | Current calibration |
| `E <en0> <en1> <en2>` | Which axes are in use; a disabled axis streams a hard `0` |
| `L <lin0> <lin1> <lin2>` | Response curve per axis, -100 to +100 |
| `Z <dz0> <dz1> <dz2>` | Deadzone per axis, percent |
| `M <sm0> <sm1> <sm2>` | Noise filtering per axis |
| `OK` | Command accepted |
| `ERR <reason>` | Command rejected (`axis`, `range`, `unknown_command`) |

## Example session

```
>  ID?
<  PEDALCAL 5
<  D 118 205 101
<  D 340 205 101
>  SET 0 120 880
<  OK
>  EN 2 0            (no clutch wired up)
<  OK
<  D 340 205 0       (clutch now reads a hard zero)
>  SAVE
<  OK
```

## Scaling

Both sides compute the pedal output the same way:

```
output = clamp((raw - min) / (max - min), 0, 1)
```

Anything at or below `min` reads 0%, anything at or above `max` reads 100%.
That is the whole point of calibration: your sensor might only physically
travel between raw 120 and raw 880, and you want that to map to a full
0–100% pedal.

## Unused inputs

An analog pin with nothing connected does not read zero. The ADC shares one
sample-and-hold capacitor across all channels, so the first conversion after
switching pins still carries charge from the previous one - an unwired clutch
input ends up echoing the brake next door. The firmware handles this two ways:

* it discards one conversion per channel before sampling, letting the
  capacitor settle, which fixes ghosting on long pedal leads too;
* an axis turned off with `EN <axis> 0` is never read at all and reports `0`.

That is why the app asks which pedals you actually wired up.

## The processing chain

Three steps, in this order, on both sides:

1. **Calibration** — `apply_calibration()`: raw sensor value mapped onto
   0-1023 between the stored min and max.
2. **Deadzone** — `apply_deadzone()`: anything below the threshold reads 0,
   and what remains is stretched back out so full travel still reaches 100%.
3. **Curve** — `apply_curve()`: `output = input ^ (2 ^ (n / 50))`, so -50 is a
   square root and +50 is a square.

Every step is integer arithmetic, written the same way in the sketch and in
`pedalcal/protocol.py`, and cross-checked over the full input range for every
combination of curve and deadzone. That matters more than it sounds: an early
version truncated in the calibration step where the app rounded, and although
that is a single count, the curve at its extreme setting has a nearly vertical
gradient off the bottom and multiplied it into **sixteen** counts of
disagreement between the graph and the hardware.

The curve is computed directly rather than through a lookup table. A table
with evenly spaced points was out by up to 20% in its first segment for the
same reason - the gradient of `x^0.25` is infinite at zero - and the error
only falls with the fourth root of the point count, so no practical table size
fixes it. Those errors also showed up as visible notches in the drawn curve.
`pow()` on a 16 MHz AVR costs a couple of hundred microseconds; three per
5 ms tick is a small price for being exact.

## Streaming and blocking

`D` frames are best-effort telemetry for the UI and nothing else depends on
them. The firmware assembles each frame into a buffer and writes it in a
single call, only when `Serial.availableForWrite()` says the whole line fits.

That matters more than it sounds. `USB_Send` on a 32u4 waits up to 250 ms for
room in the endpoint, so a frame written as eight separate `print()` calls can
stall the main loop for two seconds once the host stops draining the port -
which is what happens when the app is closed while the serial device stays
open. The controller updates sit behind that stall and the pedals drop to a
couple of updates a second in game. Skipping a telemetry frame costs nothing;
delaying a HID report costs everything.
