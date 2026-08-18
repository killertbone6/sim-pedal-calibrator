/*
 * Controller test - the smallest thing that can prove HID works
 * -------------------------------------------------------------
 * Nothing to do with pedals. It sweeps one axis back and forth so you can see
 * whether this board can register as a game controller at all, independent of
 * the calibrator firmware.
 *
 * 1. Upload this to your Pro Micro / Leonardo.
 * 2. Windows key -> type  joy.cpl  -> Enter.
 * 3. Your board should be listed. Select it, click Properties, and the X axis
 *    should sweep left and right on its own.
 *
 * How to read the result:
 *
 *   It won't compile, "Joystick.h: No such file"
 *       -> the Joystick library isn't installed where the IDE can see it.
 *
 *   It won't compile, "'Joystick_' does not name a type" or similar
 *       -> the WRONG library named Joystick is installed (Giuseppe Martini's
 *          analog-thumbstick reader). Remove it and install
 *          ArduinoJoystickLibrary by Matthew Heironimus.
 *
 *   It compiles and uploads, and the axis sweeps in joy.cpl
 *       -> board and library are both fine. The problem is elsewhere; tell
 *          me and we'll look at the calibrator sketch.
 *
 *   It compiles and uploads, but nothing appears in joy.cpl
 *       -> unplug the board, wait five seconds, plug it back in. Windows
 *          caches the old descriptor from when the board was serial-only.
 *
 *   It compiles, then upload fails with "butterfly_recv failed" or
 *   "initialization failed (rc = -1)"
 *       -> the code is fine; avrdude can't reach the bootloader. Close the
 *          calibrator app (it holds the COM port) and the Serial Monitor,
 *          then try again. If it still fails, tap RST to GND twice as soon
 *          as the IDE says "Uploading" - a 32u4 board only exposes its
 *          bootloader port for about eight seconds. See the README.
 */

#include <Joystick.h>

// Default constructor, matching every working example of this library.
Joystick_ joystick;

void setup() {
  joystick.setXAxisRange(0, 1023);
  joystick.setYAxisRange(0, 1023);
  joystick.setZAxisRange(0, 1023);
  joystick.begin();      // auto-send, so loop() only has to set values
}

void loop() {
  static int value = 0;
  static int step = 8;

  value += step;
  if (value >= 1023 || value <= 0) step = -step;

  joystick.setXAxis(value);
  joystick.setYAxis(1023 - value);   // second axis moves the opposite way
  delay(20);
}
