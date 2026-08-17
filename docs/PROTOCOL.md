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
| `GET` | Report the calibration in use | `C ...` |
| `SET <axis> <min> <max>` | Set one axis, applied immediately (not saved) | `OK` / `ERR ...` |
| `SAVE` | Write current calibration to EEPROM | `OK` |
| `LOAD` | Re-read calibration from EEPROM | `C ...` |
| `STREAM <0\|1>` | Stop / start the live value stream | `OK` |

## Device → app

| Message | Meaning |
|---|---|
| `PEDALCAL 1` | Identity banner, protocol version 1 |
| `D <raw0> <raw1> <raw2>` | Live raw readings, sent ~50×/second |
| `C <min0> <max0> <min1> <max1> <min2> <max2>` | Current calibration |
| `OK` | Command accepted |
| `ERR <reason>` | Command rejected (`axis`, `range`, `unknown_command`) |

## Example session

```
>  ID?
<  PEDALCAL 1
<  D 118 205 101
<  D 340 205 101
>  SET 0 120 880
<  OK
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
