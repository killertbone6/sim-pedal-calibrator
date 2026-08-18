/*
 * Sim Pedal Calibrator - firmware
 * -------------------------------
 * Reads three analog pedals, presents them to the OS as a game controller,
 * and accepts calibration from the desktop app over USB serial. Everything is
 * stored in EEPROM, so once it is set up the board needs no software running:
 * unplug the app, close it, uninstall it - the pedals keep working.
 *
 * Only wired up two pedals? Switch the third off in the app's Settings tab.
 * An unused analog pin floats and echoes its neighbour, so it looks like a
 * pedal that moves on its own; disabling it makes the firmware report 0.
 *
 * Works on any Arduino. On a board with native USB (Leonardo, Pro Micro,
 * Micro, Teensy) it also presents itself to the OS as a game controller, so
 * games see the calibrated axes directly - install the "Joystick" library by
 * Matthew Heironimus and that switches itself on. An Uno or Nano cannot do
 * this: its USB port is a separate serial chip, not the main processor.
 *
 * Wiring (per pedal - potentiometer, hall sensor or load-cell amp output):
 *      5V  ---- sensor VCC / pot outer leg 1
 *      GND ---- sensor GND / pot outer leg 2
 *      A0  ---- sensor signal / pot wiper      (throttle -> X axis)
 *      A1  ---- ...                            (brake    -> Y axis)
 *      A2  ---- ...                            (clutch   -> Z axis)
 *
 * Serial: 115200 baud, newline-terminated ASCII. See docs/PROTOCOL.md.
 */

#include <EEPROM.h>
#include <math.h>

// --------------------------------------------------------------- config

#define NUM_AXES 3
static const uint8_t PEDAL_PIN[NUM_AXES] = { A0, A1, A2 };

// --- game controller output -------------------------------------------
//
// The include below must stay plainly visible to the preprocessor. It is
// tempting to wrap it in __has_include(<Joystick.h>) so the sketch still
// builds without the library - but that quietly breaks everything, because
// of how the Arduino build finds libraries:
//
//   it preprocesses the sketch, notes which headers can't be resolved, adds
//   the libraries that provide them to the include path, and repeats.
//
// On that first pass the Joystick library is not on the include path yet, so
// __has_include reports false, so the #include is skipped, so nothing is
// missing, so the library is never added - and the test stays false forever.
// The sketch then compiles and uploads perfectly happily with no controller
// output at all, which is a miserable thing to debug.
//
// USBCON is safe to test here: it comes from <avr/io.h> by way of Arduino.h
// (it's a register on USB-capable chips), so it resolves correctly on the
// first pass, with or without any library installed. It also has to gate the
// include, because Joystick.h itself #errors on a board without native USB.
//
// Define PEDALCAL_NO_JOYSTICK to force controller output off - useful on a
// 32u4 board if you would rather not install the library at all.

#if defined(USBCON) && !defined(PEDALCAL_NO_JOYSTICK)
  #include <Joystick.h>

  #if defined(JOYSTICK_DEFAULT_REPORT_ID)
    #define USE_JOYSTICK 1
  #else
    #warning "Joystick.h is not ArduinoJoystickLibrary, so there is no game controller output. Remove the library named Joystick by Giuseppe Martini and install the one by Matthew Heironimus: https://github.com/MHeironimus/ArduinoJoystickLibrary"
  #endif
#endif

static const uint16_t PROTOCOL_VERSION = 4;
static const uint16_t ADC_MAX      = 1023;
static const uint16_t HID_MS       = 5;   // 200 controller updates a second
static const uint8_t  FRAMES_PER_STREAM = 4;   // serial telemetry at 50 Hz
static const uint8_t  OVERSAMPLE   = 4;   // averaged reads per sample
static const uint32_t EEPROM_MAGIC = 0x50444C33UL;  // "PDL3"
static const int      EEPROM_ADDR  = 0;

// --- noise filtering ---------------------------------------------------
// A cheap potentiometer wanders by 10-20 counts even when nothing is
// touching it, which reads as the pedal twitching by 1-2%. Three cheap
// measures between them deal with it:
//
//   OVERSAMPLE     averaging a few conversions knocks the edge off
//   EMA_SHIFT      an exponential moving average, 1/8 weight on new samples
//   DEADBAND       ignore movement smaller than this once settled
//
// Filtering costs responsiveness, which is the last thing a pedal wants, so
// FAST_JUMP switches it all off the moment the pedal genuinely moves: a
// change bigger than that snaps straight through with no lag at all. The
// smoothing is then only ever doing work while your foot is still.
static const uint8_t  EMA_SHIFT = 3;
static const uint8_t  DEADBAND  = 4;
static const uint16_t FAST_JUMP = 24;

// --- response curve ----------------------------------------------------
// Evaluated through a small lookup table with linear interpolation rather
// than calling pow() a few hundred times a second. The table is rebuilt only
// when the curve changes. The desktop app runs identical integer arithmetic,
// so the number on screen is the number the game receives.
#define CURVE_POINTS 17
static const uint8_t CURVE_SHIFT = 6;    // ADC_MAX >> 6 == 15, so 16 segments

// ---------------------------------------------------------------- state

struct Cal { uint16_t lo; uint16_t hi; };
struct Store {
  uint32_t magic;
  Cal      axis[NUM_AXES];
  uint8_t  enabled[NUM_AXES];
  int8_t   linearity[NUM_AXES];
};

static Store    store;
static uint16_t curveLut[NUM_AXES][CURVE_POINTS];
static int32_t  emaAcc[NUM_AXES];
static uint16_t settled[NUM_AXES];
static bool     streaming = true;
static char     buf[48];
static uint8_t  buflen = 0;
static uint32_t nextFrame = 0;
static uint8_t  frameCount = 0;

#ifdef USE_JOYSTICK
  // The default constructor, as used by every working example of this
  // library. It advertises 32 buttons, 2 hat switches and every axis. Three
  // pedals need far less, but a descriptor claiming zero buttons and zero hat
  // switches is the configuration Windows is fussy about: the board
  // enumerates as a HID device and yet doesn't reliably show up as a game
  // controller. Unused buttons and axes just read as idle, which costs
  // nothing, so this stays on the well-trodden path.
  //
  // Axis mapping:  X = throttle,  Y = brake,  Z = clutch.
  Joystick_ joystick;
#endif

// ------------------------------------------------------------- helpers

static void buildCurve(uint8_t i) {
  float gamma = pow(2.0f, store.linearity[i] / 50.0f);
  for (uint8_t p = 0; p < CURVE_POINTS; p++) {
    float x = (float)p / (float)(CURVE_POINTS - 1);
    curveLut[i][p] = (uint16_t)(ADC_MAX * pow(x, gamma) + 0.5f);
  }
}

static void buildAllCurves() {
  for (uint8_t i = 0; i < NUM_AXES; i++) buildCurve(i);
}

static void useDefaults() {
  store.magic = EEPROM_MAGIC;
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    store.axis[i].lo = 0;
    store.axis[i].hi = ADC_MAX;
    store.enabled[i] = 1;
    store.linearity[i] = 0;
  }
}

static void loadFromEeprom() {
  EEPROM.get(EEPROM_ADDR, store);
  bool sane = (store.magic == EEPROM_MAGIC);
  for (uint8_t i = 0; sane && i < NUM_AXES; i++) {
    if (store.axis[i].lo >= store.axis[i].hi || store.axis[i].hi > ADC_MAX) {
      sane = false;
    }
    if (store.enabled[i] > 1) sane = false;
    if (store.linearity[i] < -100 || store.linearity[i] > 100) sane = false;
  }
  if (!sane) useDefaults();   // first boot, or corrupted contents
  buildAllCurves();
}

static void saveToEeprom() {
  store.magic = EEPROM_MAGIC;
  EEPROM.put(EEPROM_ADDR, store);   // EEPROM.put only writes changed bytes
}

static uint16_t readAxis(uint8_t i) {
  if (!store.enabled[i]) return 0;   // nothing wired here: report a hard zero

  // The ADC shares one sample-and-hold across every analog pin, so the first
  // reading after switching channels still carries charge from the previous
  // one. On a high-impedance input - a pedal on a long lead, or a pin with
  // nothing attached - that shows up as one axis ghosting another. Throwing
  // the first conversion away lets the capacitor settle on the new channel.
  analogRead(PEDAL_PIN[i]);

  uint16_t total = 0;
  for (uint8_t s = 0; s < OVERSAMPLE; s++) total += analogRead(PEDAL_PIN[i]);
  uint16_t sample = total / OVERSAMPLE;

  int32_t delta = (int32_t)sample - (int32_t)settled[i];
  if (delta > FAST_JUMP || delta < -(int32_t)FAST_JUMP) {
    // Real movement. Drop the filter entirely so there is no lag where it
    // would actually be felt.
    emaAcc[i] = (int32_t)sample << EMA_SHIFT;
    settled[i] = sample;
    return sample;
  }

  emaAcc[i] += (int32_t)sample - (emaAcc[i] >> EMA_SHIFT);
  uint16_t filtered = (uint16_t)(emaAcc[i] >> EMA_SHIFT);
  int32_t drift = (int32_t)filtered - (int32_t)settled[i];
  if (drift >= DEADBAND || drift <= -(int32_t)DEADBAND) settled[i] = filtered;
  return settled[i];
}

// Calibration, then curve. Same arithmetic as the app's pedal_output().
static uint16_t applyCal(uint16_t raw, const Cal &c) {
  if (raw <= c.lo) return 0;
  if (raw >= c.hi) return ADC_MAX;
  return (uint32_t)(raw - c.lo) * ADC_MAX / (c.hi - c.lo);
}

static uint16_t applyCurve(uint16_t value, uint8_t i) {
  if (store.linearity[i] == 0) return value;
  uint8_t index = value >> CURVE_SHIFT;
  if (index >= CURVE_POINTS - 1) return curveLut[i][CURVE_POINTS - 1];
  uint16_t frac = value & ((1 << CURVE_SHIFT) - 1);
  uint16_t low = curveLut[i][index];
  uint16_t high = curveLut[i][index + 1];
  return low + (uint16_t)(((uint32_t)(high - low) * frac) >> CURVE_SHIFT);
}

static uint16_t pedalOutput(uint16_t raw, uint8_t i) {
  return applyCurve(applyCal(raw, store.axis[i]), i);
}

// ---------------------------------------------------------- reporting

static void sendEnabled() {
  Serial.print(F("E"));
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    Serial.print(' '); Serial.print(store.enabled[i] ? 1 : 0);
  }
  Serial.println();
}

static void sendCal() {
  Serial.print(F("C"));
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    Serial.print(' '); Serial.print(store.axis[i].lo);
    Serial.print(' '); Serial.print(store.axis[i].hi);
  }
  Serial.println();
}

static void sendLinearity() {
  Serial.print(F("L"));
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    Serial.print(' '); Serial.print(store.linearity[i]);
  }
  Serial.println();
}

// The important one. Nothing here may ever block.
//
// USB_Send waits up to 250 ms for room in the endpoint, and a frame written
// as eight separate print() calls can therefore stall the loop for two whole
// seconds when the host stops draining the port - which is exactly what
// happens when you close the app while the serial device stays open. The
// controller updates are stuck behind that, and the pedals go to a couple of
// frames a second in game.
//
// So: assemble the line ourselves, check there is room for all of it, and
// write it in one go. No room means we skip this frame, which costs nothing -
// it's only telemetry for a UI that evidently isn't listening.
static void streamFrame(const uint16_t *raw) {
  if (!streaming) return;
#ifdef USBCON
  if (!Serial) return;              // port isn't open: don't even try
#endif
  char line[32];
  int len = snprintf(line, sizeof(line), "D %u %u %u\n",
                     raw[0], raw[1], raw[2]);
  if (len <= 0 || len >= (int)sizeof(line)) return;
  if (Serial.availableForWrite() < len) return;
  Serial.write((const uint8_t *)line, (size_t)len);
}

// ------------------------------------------------------------ commands

static void handleCommand(char *line) {
  if (line[0] == '\0') return;

  if (!strcmp(line, "ID?")) {
    // The third field tells the app whether this board is presenting itself
    // to the OS as a game controller, so it can say so instead of leaving
    // people wondering why the pedals calibrate but no game sees them.
    Serial.print(F("PEDALCAL ")); Serial.print(PROTOCOL_VERSION);
#ifdef USE_JOYSTICK
    Serial.println(F(" hid"));
#else
    Serial.println(F(" nohid"));
#endif
    return;
  }
  if (!strcmp(line, "GET")) { sendCal(); sendEnabled(); sendLinearity(); return; }
  if (!strcmp(line, "LOAD")) {
    loadFromEeprom(); sendCal(); sendEnabled(); sendLinearity(); return;
  }
  if (!strcmp(line, "SAVE")) { saveToEeprom(); Serial.println(F("OK")); return; }

  if (!strncmp(line, "STREAM ", 7)) {
    streaming = (line[7] != '0');
    Serial.println(F("OK"));
    return;
  }

  if (!strncmp(line, "EN ", 3)) {
    char *tok = strtok(line + 3, " ");
    long axis = tok ? atol(tok) : -1;
    tok = strtok(NULL, " ");
    if (axis < 0 || axis >= NUM_AXES || tok == NULL) {
      Serial.println(F("ERR axis"));
      return;
    }
    store.enabled[axis] = (tok[0] != '0') ? 1 : 0;
    Serial.println(F("OK"));
    return;
  }

  if (!strncmp(line, "CURVE ", 6)) {
    char *tok = strtok(line + 6, " ");
    long axis = tok ? atol(tok) : -1;
    tok = strtok(NULL, " ");
    long lin = tok ? atol(tok) : 0;
    if (axis < 0 || axis >= NUM_AXES || tok == NULL) {
      Serial.println(F("ERR axis"));
      return;
    }
    if (lin < -100 || lin > 100) { Serial.println(F("ERR range")); return; }
    store.linearity[axis] = (int8_t)lin;
    buildCurve((uint8_t)axis);
    Serial.println(F("OK"));
    return;
  }

  if (!strncmp(line, "SET ", 4)) {
    char *tok = strtok(line + 4, " ");
    long axis = tok ? atol(tok) : -1;
    tok = strtok(NULL, " ");
    long lo = tok ? atol(tok) : -1;
    tok = strtok(NULL, " ");
    long hi = tok ? atol(tok) : -1;

    if (axis < 0 || axis >= NUM_AXES) { Serial.println(F("ERR axis")); return; }
    if (lo < 0 || hi > ADC_MAX || lo >= hi) { Serial.println(F("ERR range")); return; }

    store.axis[axis].lo = (uint16_t)lo;
    store.axis[axis].hi = (uint16_t)hi;
    Serial.println(F("OK"));
    return;
  }

  Serial.println(F("ERR unknown_command"));
}

static void pumpSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      buf[buflen] = '\0';
      handleCommand(buf);
      buflen = 0;
    } else if (buflen < sizeof(buf) - 1) {
      buf[buflen++] = c;
    } else {
      buflen = 0;   // overlong line: drop it rather than overflow
    }
  }
}

// ---------------------------------------------------------------- main

void setup() {
  Serial.begin(115200);
  loadFromEeprom();
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    uint16_t first = store.enabled[i] ? analogRead(PEDAL_PIN[i]) : 0;
    emaAcc[i] = (int32_t)first << EMA_SHIFT;
    settled[i] = first;
  }

#ifdef USE_JOYSTICK
  joystick.setXAxisRange(0, ADC_MAX);
  joystick.setYAxisRange(0, ADC_MAX);
  joystick.setZAxisRange(0, ADC_MAX);
  joystick.begin(false);   // we call sendState() ourselves
#endif
}

void loop() {
  pumpSerial();

  uint32_t now = millis();
  if ((int32_t)(now - nextFrame) < 0) return;
  nextFrame = now + HID_MS;

  uint16_t raw[NUM_AXES];
  for (uint8_t i = 0; i < NUM_AXES; i++) raw[i] = readAxis(i);

  // The controller update goes first and is never gated on the serial link.
  // A game must not care whether anything is listening on the COM port.
#ifdef USE_JOYSTICK
  joystick.setXAxis(store.enabled[0] ? pedalOutput(raw[0], 0) : 0);
  joystick.setYAxis(store.enabled[1] ? pedalOutput(raw[1], 1) : 0);
  joystick.setZAxis(store.enabled[2] ? pedalOutput(raw[2], 2) : 0);
  joystick.sendState();
#endif

  if (++frameCount >= FRAMES_PER_STREAM) {
    frameCount = 0;
    streamFrame(raw);
  }
}
