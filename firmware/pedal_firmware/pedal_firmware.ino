/*
 * Sim Pedal Calibrator - firmware
 * -------------------------------
 * Reads three analog pedals, streams the raw values over USB serial, and
 * accepts min/max calibration from the desktop app. Calibration survives a
 * power cycle because it lives in EEPROM.
 *
 * Works on any Arduino. On a board with native USB (Leonardo, Pro Micro,
 * Micro, Teensy) you can also uncomment USE_JOYSTICK below and the board
 * will appear to Windows as a game controller, so games see the calibrated
 * axes directly.
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

// Uncomment on a native-USB board *after* installing the "Joystick" library
// by Matthew Heironimus (Library Manager -> search "Joystick").
// #define USE_JOYSTICK

static const uint16_t PROTOCOL_VERSION = 1;
static const uint16_t ADC_MAX     = 1023;
static const uint16_t STREAM_MS   = 20;     // 20 ms -> 50 frames/second
static const uint8_t  OVERSAMPLE  = 4;      // averaged reads, cheap smoothing
static const uint32_t EEPROM_MAGIC = 0x50444C31UL;  // "PDL1"
static const int      EEPROM_ADDR  = 0;

// ---------------------------------------------------------------- state

struct Cal { uint16_t lo; uint16_t hi; };
struct Store { uint32_t magic; Cal axis[NUM_AXES]; };

static Store store;
static bool     streaming = true;
static char     buf[48];
static uint8_t  buflen = 0;
static uint32_t nextFrame = 0;

#ifdef USE_JOYSTICK
  #include <Joystick.h>
  Joystick_ joystick(JOYSTICK_DEFAULT_REPORT_ID, JOYSTICK_TYPE_JOYSTICK,
                     0, 0,                 // no buttons, no hat switch
                     true, true, true,     // X, Y, Z  = throttle, brake, clutch
                     false, false, false, false, false, false, false, false);
#endif

// ------------------------------------------------------------- helpers

static void useDefaults() {
  store.magic = EEPROM_MAGIC;
  for (uint8_t i = 0; i < NUM_AXES; i++) {
    store.axis[i].lo = 0;
    store.axis[i].hi = ADC_MAX;
  }
}

static void loadFromEeprom() {
  EEPROM.get(EEPROM_ADDR, store);
  bool sane = (store.magic == EEPROM_MAGIC);
  for (uint8_t i = 0; sane && i < NUM_AXES; i++) {
    if (store.axis[i].lo >= store.axis[i].hi || store.axis[i].hi > ADC_MAX) {
      sane = false;
    }
  }
  if (!sane) useDefaults();   // first boot, or corrupted contents
}

static void saveToEeprom() {
  store.magic = EEPROM_MAGIC;
  EEPROM.put(EEPROM_ADDR, store);   // EEPROM.put only writes changed bytes
}

static uint16_t readAxis(uint8_t i) {
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
    Serial.print(F("PEDALCAL ")); Serial.println(PROTOCOL_VERSION);
    return;
  }
  if (!strcmp(line, "GET")) { sendCal(); return; }
  if (!strcmp(line, "LOAD")) { loadFromEeprom(); sendCal(); return; }
  if (!strcmp(line, "SAVE")) { saveToEeprom(); Serial.println(F("OK")); return; }

  if (!strncmp(line, "STREAM ", 7)) {
    streaming = (line[7] != '0');
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
  joystick.setXAxis(applyCal(raw[0], store.axis[0]));
  joystick.setYAxis(applyCal(raw[1], store.axis[1]));
  joystick.setZAxis(applyCal(raw[2], store.axis[2]));
  joystick.sendState();
#endif

  if (streaming) {
    Serial.print(F("D"));
    for (uint8_t i = 0; i < NUM_AXES; i++) { Serial.print(' '); Serial.print(raw[i]); }
    Serial.println();
  }
}
