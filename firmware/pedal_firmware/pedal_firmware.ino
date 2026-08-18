/*
 * Sim Pedal Calibrator - firmware
 * -------------------------------
 * Reads three analog pedals, streams the raw values over USB serial, and
 * accepts min/max calibration from the desktop app. Calibration survives a
 * power cycle because it lives in EEPROM.
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
 *      A0  ---- sensor signal / pot wiper      (throttle)
 *      A1  ---- ...                            (brake)
 *      A2  ---- ...                            (clutch)
 *
 * Serial: 115200 baud, newline-terminated ASCII. See PROTOCOL in the repo.
 */

#include <EEPROM.h>

// --------------------------------------------------------------- config

#define NUM_AXES 3
static const uint8_t PEDAL_PIN[NUM_AXES] = { A0, A1, A2 };

// --- game controller output -------------------------------------------
// Switches itself on when both conditions hold:
//
//   * the board has native USB (Leonardo, Micro, Pro Micro, Teensy). USBCON is
//     defined by the core for exactly those chips; an Uno or Nano uses a
//     separate USB-serial chip and physically cannot present as an HID device.
//
//   * the right Joystick library is installed. Two different libraries are
//     called "Joystick" - the HID one by Matthew Heironimus that this sketch
//     needs, and an unrelated analog-thumbstick reader by Giuseppe Martini
//     which is the one the Library Manager index lists under that name. Both
//     provide <Joystick.h>, so testing for that header alone proves nothing.
//     Only Heironimus's ships DynamicHID, so that is what we look for - and
//     we never include the wrong header, which would fail to compile with a
//     confusing error about Joystick_ not existing.
//
// Define PEDALCAL_NO_JOYSTICK above this line to force controller output off.

#if !defined(PEDALCAL_NO_JOYSTICK) && defined(USBCON)
  #if !defined(__has_include)
    #include <Joystick.h>          // ancient toolchain: hope for the best
    #define USE_JOYSTICK 1
  #elif __has_include(<Joystick.h>) && __has_include(<DynamicHID/DynamicHID.h>)
    #include <Joystick.h>
    #define USE_JOYSTICK 1
  #elif __has_include(<Joystick.h>)
    #warning "The installed Joystick library is the wrong one - no game controller output. Remove the Joystick library by Giuseppe Martini and install ArduinoJoystickLibrary by Matthew Heironimus: https://github.com/MHeironimus/ArduinoJoystickLibrary"
  #else
    #warning "No Joystick library found - no game controller output. Install ArduinoJoystickLibrary by Matthew Heironimus: https://github.com/MHeironimus/ArduinoJoystickLibrary"
  #endif
#endif

#if defined(USE_JOYSTICK) && !defined(JOYSTICK_DEFAULT_REPORT_ID)
  // Belt and braces: the header came from somewhere unexpected.
  #error "Joystick.h does not look like ArduinoJoystickLibrary. Remove any other library named Joystick."
#endif

static const uint16_t PROTOCOL_VERSION = 3;
static const uint16_t ADC_MAX     = 1023;
static const uint16_t STREAM_MS   = 20;     // 20 ms -> 50 frames/second
static const uint8_t  OVERSAMPLE  = 4;      // averaged reads, cheap smoothing
static const uint32_t EEPROM_MAGIC = 0x50444C32UL;  // "PDL2"
static const int      EEPROM_ADDR  = 0;

// ---------------------------------------------------------------- state

struct Cal { uint16_t lo; uint16_t hi; };
struct Store { uint32_t magic; Cal axis[NUM_AXES]; uint8_t enabled[NUM_AXES]; };

static Store store;
static bool     streaming = true;
static char     buf[48];
static uint8_t  buflen = 0;
static uint32_t nextFrame = 0;

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

static void useDefaults() {
  store.magic = EEPROM_MAGIC;
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    store.axis[i].lo = 0;
    store.axis[i].hi = ADC_MAX;
    store.enabled[i] = 1;
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
  }
  if (!sane) useDefaults();   // first boot, or corrupted contents
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
  return total / OVERSAMPLE;
}

// Same maths as scale() in the Python app.
static uint16_t applyCal(uint16_t raw, const Cal &c) {
  if (raw <= c.lo) return 0;
  if (raw >= c.hi) return ADC_MAX;
  return (uint32_t)(raw - c.lo) * ADC_MAX / (c.hi - c.lo);
}

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
  if (!strcmp(line, "GET")) { sendCal(); sendEnabled(); return; }
  if (!strcmp(line, "LOAD")) { loadFromEeprom(); sendCal(); sendEnabled(); return; }
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
  nextFrame = now + STREAM_MS;

  uint16_t raw[NUM_AXES];
  for (uint8_t i = 0; i < NUM_AXES; i++) raw[i] = readAxis(i);

#ifdef USE_JOYSTICK
  joystick.setXAxis(store.enabled[0] ? applyCal(raw[0], store.axis[0]) : 0);
  joystick.setYAxis(store.enabled[1] ? applyCal(raw[1], store.axis[1]) : 0);
  joystick.setZAxis(store.enabled[2] ? applyCal(raw[2], store.axis[2]) : 0);
  joystick.sendState();
#endif

  if (streaming) {
    Serial.print(F("D"));
    for (uint8_t i = 0; i < NUM_AXES; i++) { Serial.print(' '); Serial.print(raw[i]); }
    Serial.println();
  }
}
