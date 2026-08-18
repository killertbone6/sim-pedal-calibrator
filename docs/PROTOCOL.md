# Serial protocol

Plain ASCII, one message per line, terminated with `\n`, at **115200 baud**.

Because it is text, you can drive the device by hand: open the Arduino IDE's
Serial Monitor at 115200, set the line ending to "Newline", and type commands.

Axis numbers are `0 = throttle`, `1 = brake`, `2 = clutch`.
Raw values are 10-bit, so `0`–`1023`.

## App → device

| Command | Meaning | Reply |
|---|---|---|
| `ID?` | Who is there? | `PEDALCAL <version>` |
| `GET` | Report calibration, axis state and curves | `C ...`, `E ...`, `L ...` |
| `SET <axis> <min> <max>` | Set one axis, applied immediately (not saved) | `OK` / `ERR ...` |
| `EN <axis> <0\|1>` | Mark an axis as unused / in use | `OK` / `ERR ...` |
| `CURVE <axis> <-100..100>` | Response curve; 0 is linear | `OK` / `ERR ...` |
| `SAVE` | Write current calibration to EEPROM | `OK` |
| `LOAD` | Re-read everything from EEPROM | `C ...`, `E ...`, `L ...` |
| `STREAM <0\|1>` | Stop / start the live value stream | `OK` |

## Device → app

| Message | Meaning |
|---|---|
| `PEDALCAL 4` | Identity banner, protocol version 4 |
| `D <raw0> <raw1> <raw2>` | Live raw readings, sent ~50×/second |
| `C <min0> <max0> <min1> <max1> <min2> <max2>` | Current calibration |
| `E <en0> <en1> <en2>` | Which axes are in use; a disabled axis streams a hard `0` |
| `L <lin0> <lin1> <lin2>` | Response curve per axis, -100 to +100 |
| `OK` | Command accepted |
| `ERR <reason>` | Command rejected (`axis`, `range`, `unknown_command`) |

## Example session

```
>  ID?
<  PEDALCAL 4
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

## The response curve

`CURVE <axis> <n>` shapes an axis after calibration. `n` runs from -100 to
+100, where 0 is a straight line, negative gives more output for the same
travel (quicker, more sensitive) and positive gives less (gentler, easier to
hold part-way). The exponent is `2 ^ (n / 50)`, so -50 is a square root and
+50 is a square.

The firmware doesn't call `pow()` per sample. When the curve changes it builds
a 17-point lookup table once and interpolates between the points with a 6-bit
fraction. The desktop app runs byte-identical integer arithmetic in
`protocol.apply_curve()`, verified across the whole input range, so the curve
drawn on screen is exactly what the board applies.

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
