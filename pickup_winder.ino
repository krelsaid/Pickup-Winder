// Name:    pickup_winder.ino
// Author:  khairil said
// Date:    1/12/2025
// Version: 1.0

// --- FIRMWARE OVERVIEW ---
// This firmware controls a guitar pickup coil winder using an Arduino and a CNC shield.
//
// Core Components:
// - Stepper Motor (Y-Axis): Manages the main rotation of the winder.
// - Servo Motor: Guides the wire back and forth across the bobbin.
// - Serial Command Interface: All operations are controlled by text-based commands sent
//   over the serial monitor (e.g., START, STOP, PAUSE, BOBBIN, CALC).
//
// Key Features:
// - S-Curve Acceleration: Implements smooth motion for the stepper motor during the
//   first and last rotations to prevent jerking and ensure even winding.
// - Pause/Resume: Winding can be paused and resumed without losing progress.
// - Turn Count Calculation: The 'CALC' command iteratively calculates the required
//   number of turns to achieve a target DC resistance, accounting for the changing
//   bobbin diameter as wire builds up.
// - Dynamic Winding Parameters: Automatically calculates the servo's travel increment
//   per rotation based on bobbin height and wire diameter.
// - EEPROM Storage: Saves all critical settings (servo calibration, speed, acceleration,
//   bobbin dimensions, wire diameter, etc.) so they persist after a power cycle.
// - Comprehensive Testing Suite: Includes commands to test individual components
//   (TEST_SERVO, TEST_STEPPER_MOVE) and winding patterns (TEST_LAYER) without
//   committing to a full wind.
// - Safety Timeout: Automatically disables motors if no command is received for a set
//   period, preventing the machine from being left in an active state.
// - Robust Command Parsing: Commands for setting bobbin dimensions, wire diameter,
//   and other parameters include validation to prevent invalid inputs.

#include <Servo.h>
#include <EEPROM.h>

// -----------------------------
// CNC SHIELD Y-AXIS
// -----------------------------
const int STEP_PIN = 3;
const int DIR_PIN  = 6;
const int EN_PIN   = 8;

// -----------------------------
// SERVO
// -----------------------------
const int SERVO_PIN = 10;
Servo layServo;

// -----------------------------
// SETTINGS
// -----------------------------
long targetTurns = 0;
long currentSteps = 0;
int stepsPerTurn = 3200;       // full-step NEMA17, multiply by microsteps if needed
bool running = false;
bool paused = false;
bool verboseMode = false;

// Stepper direction
bool stepperForward = true;

// Servo calibration / sweep
float servoMinAngle = 70;    
float servoMaxAngle = 100;
float servoPos = servoMinAngle;
float servoIncrementPerTurn = 0.0;

// Pickup & wire
float bobbinHeight = 9.0;      // mm, traversable height between flatwork
float wireDiameter = 0.2;      // mm
long turnsPerLayer = 45;       // calculated
float bobbinLength = 60.0;     // mm, length of the bobbin core
float bobbinWidth = 4.0;       // mm, width/thickness of the bobbin core
float avgTurnLength = 140.0;   // mm, average length of one turn around the bobbin
float lastCalcRequestedResistance = 0.0; // Ohms, stores the last target resistance from CALC command

// Timeout
unsigned long lastCommandTime = 0;
unsigned long timeoutLimit = 10000; // 10s default
bool outputsEnabled = true;

// Acceleration
long stepCount = 0;
long totalSteps = 0;
int initialStepDelay = 1000;      // µs
int minStepDelay = 300;           // µs
long accelSteps = 400;           // steps for accel/decel. A longer ramp prevents jerking.

// Serial input buffer (replaces String object to save memory)
const byte MAX_CMD_LENGTH = 64;
char inputBuffer[MAX_CMD_LENGTH];
byte inputIndex = 0;

// ==========================
// EEPROM Addresses
// ==========================
int addr = 0;
#define ADDR_SERVO_MIN      (addr)
#define ADDR_SERVO_MAX      (addr += sizeof(float))         // After servo min (float)
#define ADDR_WIRE_DIAM      (addr += sizeof(float))         // After servo max (float)
#define ADDR_STEP_DELAY     (addr += sizeof(float))         // After wire diam (float)
#define ADDR_TIMEOUT        (addr += sizeof(int))           // After step delay (int)
#define ADDR_ACCEL_STEPS    (addr += sizeof(unsigned long)) // After timeout (unsigned long)
#define ADDR_BOBBIN_LEN     (addr += sizeof(long))          // After accel steps (long)
#define ADDR_BOBBIN_WID     (addr += sizeof(float))         // After bobbin len (float)
#define ADDR_BOBBIN_H       (addr += sizeof(float))         // After bobbin wid (float)
#define ADDR_LAST_CALC_R    (addr += sizeof(float))         // After bobbin h (float)
#define EEPROM_SIZE         (addr + sizeof(float))          // Final size after all addresses
// Note: ADDR_STEPS_PER_TURN is not saved/loaded, so it doesn't need an address.
// The next available address would be (addr += sizeof(unsigned long))


// ==========================
// SETUP
// ==========================
void setup() {
  Serial.begin(115200);

  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  pinMode(EN_PIN, OUTPUT);

  // Start with outputs disabled for safety.
  // enableOutputs() will attach the servo when needed.
  digitalWrite(EN_PIN, HIGH);
  outputsEnabled = false;
  
  loadSettings();             // Load from EEPROM
  computeWindingParameters(); // Initial calculation with loaded/default values

  Serial.println(F("\n--- Initial Settings Loaded ---"));
  printStatus();

  Serial.println(F("Pickup Coil Winder READY"));
}

// ==========================
// ENABLE / DISABLE OUTPUTS
// ==========================
void enableOutputs() {
  digitalWrite(EN_PIN, LOW); // enable stepper
  if (!layServo.attached()) { layServo.attach(SERVO_PIN); delay(50); } // Add small delay for servo to initialize
  outputsEnabled = true;
  Serial.println(F("STATUS: Outputs ENABLED"));
}

void disableOutputs() {
  digitalWrite(EN_PIN, HIGH); // disable stepper
  if (layServo.attached()) layServo.detach();
  outputsEnabled = false;
  Serial.println(F("STATUS: Outputs DISABLED"));
}

// ==========================
// ENABLE / DISABLE SERVO ONLY
// ==========================
void enableServo() {
  if (!layServo.attached()) { 
    layServo.attach(SERVO_PIN); 
    delay(50); // Add small delay for servo to initialize
  }
}

void disableServo() {
  if (layServo.attached()) layServo.detach();
}

// ==========================
// COMPUTE SERVO INCREMENT
// ==========================
void updateAndValidate() {
  // Re-run sanity checks on values that might have been changed by commands
  bool anglesInvalid = false;
  if (isnan(servoMinAngle) || servoMinAngle < 0 || servoMinAngle > 180 || servoMinAngle >= servoMaxAngle) {
    servoMinAngle = 77.0;
    anglesInvalid = true;
  }
  if (isnan(servoMaxAngle) || servoMaxAngle < 0 || servoMaxAngle > 180 || servoMinAngle >= servoMaxAngle) {
    servoMaxAngle = 103.0;
    anglesInvalid = true;
  }
  if (anglesInvalid) Serial.println(F("WARN: Invalid servo angles detected, resetting to defaults."));

  if (isnan(wireDiameter) || wireDiameter <= 0.0) {
    wireDiameter = 0.2; // Reset to a safe default
    Serial.println(F("WARN: Invalid wire diameter detected, resetting to default."));
  }

  // Now that values are safe, perform the calculation
  computeWindingParameters();
}

void computeWindingParameters() {
  turnsPerLayer = (long)(bobbinHeight / wireDiameter); 
  if (turnsPerLayer <= 0) turnsPerLayer = 1; // Avoid division by zero
  float sweepAngle = servoMaxAngle - servoMinAngle;
  servoIncrementPerTurn = sweepAngle / turnsPerLayer;
  servoPos = servoMinAngle;
  // Don't move servo here, commands will handle positioning.
}

// ==========================
// TIMEOUT CHECK
// ==========================
void checkTimeout() {
  if (millis() - lastCommandTime > timeoutLimit) {
    if (outputsEnabled) {
      disableOutputs();
      running = false;
      Serial.println(F("STATUS: AUTO-TIMEOUT - Outputs disabled"));
    }
  }
}

// ==========================
// EEPROM FUNCTIONS
// ==========================
void saveSettings() {
  EEPROM.put(ADDR_SERVO_MIN, servoMinAngle);
  EEPROM.put(ADDR_SERVO_MAX, servoMaxAngle);
  EEPROM.put(ADDR_WIRE_DIAM, wireDiameter);
  EEPROM.put(ADDR_STEP_DELAY, initialStepDelay);
  EEPROM.put(ADDR_TIMEOUT, timeoutLimit);
  EEPROM.put(ADDR_ACCEL_STEPS, accelSteps);
  EEPROM.put(ADDR_BOBBIN_LEN, bobbinLength);
  EEPROM.put(ADDR_BOBBIN_WID, bobbinWidth);
  EEPROM.put(ADDR_BOBBIN_H, bobbinHeight);
  EEPROM.put(ADDR_LAST_CALC_R, lastCalcRequestedResistance);
  Serial.println(F("STATUS: Settings saved to EEPROM"));
}

void clearEEPROM() {
  Serial.println(F("INFO: Clearing EEPROM..."));
  for (int i = 0; i < EEPROM_SIZE; i++) {
    EEPROM.write(i, 0xFF); // Write 0xFF to each byte, which is an invalid state for floats
  }
  Serial.println(F("STATUS: EEPROM cleared."));
}

void loadSettings() {
  EEPROM.get(ADDR_SERVO_MIN, servoMinAngle);
  EEPROM.get(ADDR_SERVO_MAX, servoMaxAngle);
  EEPROM.get(ADDR_WIRE_DIAM, wireDiameter);
  EEPROM.get(ADDR_STEP_DELAY, initialStepDelay);
  EEPROM.get(ADDR_TIMEOUT, timeoutLimit);
  EEPROM.get(ADDR_ACCEL_STEPS, accelSteps);
  EEPROM.get(ADDR_BOBBIN_LEN, bobbinLength);
  EEPROM.get(ADDR_BOBBIN_WID, bobbinWidth);
  EEPROM.get(ADDR_BOBBIN_H, bobbinHeight);
  EEPROM.get(ADDR_LAST_CALC_R, lastCalcRequestedResistance);

  // --- Sanity Checks for all loaded values ---

  // Check servo angles
  bool servoAnglesInvalid = false;
  if (isnan(servoMinAngle) || servoMinAngle < 0 || servoMinAngle > 180) {
    servoMinAngle = 77.0; // Default value
    servoAnglesInvalid = true;
  }
  if (isnan(servoMaxAngle) || servoMaxAngle < 0 || servoMaxAngle > 180) {
    servoMaxAngle = 103.0; // Default value
    servoAnglesInvalid = true;
  }
  if (servoMinAngle >= servoMaxAngle) {
    servoMinAngle = 77.0;
    servoMaxAngle = 103.0;
    servoAnglesInvalid = true;
  }
  if (servoAnglesInvalid) {
    Serial.println(F("WARN: Invalid servo angles in EEPROM, reset to defaults."));
  }

  // Check wire diameter
  if (isnan(wireDiameter) || wireDiameter <= 0.0) {
    wireDiameter = 0.2; // Reset to a safe default
    Serial.println(F("WARN: Invalid wire diameter in EEPROM, reset to default."));
  }

  // Check step delay (speed)
  if (initialStepDelay <= minStepDelay || initialStepDelay > 20000) {
    initialStepDelay = 1000; // Reset to a safe default
    Serial.println(F("WARN: Invalid step delay in EEPROM, reset to default."));
  }

  // Check timeout limit
  if (timeoutLimit < 1000) { // Must be at least 1 second
    timeoutLimit = 10000; // Reset to default
    Serial.println(F("WARN: Invalid timeout in EEPROM, reset to default."));
  }

  // Check acceleration steps
  if (accelSteps <= 0 || accelSteps > 10000) {
    accelSteps = 400; // Reset to a safe default
    Serial.println(F("WARN: Invalid accel steps in EEPROM, reset to default."));
  }

  // Check bobbin dimensions
  if (isnan(bobbinLength) || bobbinLength <= 0.0 || bobbinLength > 1000.0) {
    bobbinLength = 60.0;
    Serial.println(F("WARN: Invalid bobbin length in EEPROM, reset to default."));
  }
  if (isnan(bobbinWidth) || bobbinWidth <= 0.0 || bobbinWidth > 1000.0) {
    bobbinWidth = 4.0;
    Serial.println(F("WARN: Invalid bobbin width in EEPROM, reset to default."));
  }
  if (isnan(bobbinHeight) || bobbinHeight <= 0.0 || bobbinHeight > 100.0) {
    bobbinHeight = 9.0;
    Serial.println(F("WARN: Invalid bobbin height in EEPROM, reset to default."));
  }
  // Check lastCalcRequestedResistance
  if (isnan(lastCalcRequestedResistance) || lastCalcRequestedResistance < 0.0) {
    lastCalcRequestedResistance = 0.0;
    Serial.println(F("WARN: Invalid last calculated resistance in EEPROM, reset to default."));
  }

  Serial.println(F("STATUS: Settings loaded from EEPROM"));

  // Calculate avgTurnLength from loaded bobbin dimensions
  calculateAvgTurnLength();
}

// ==========================
// S-CURVE DELAY CALCULATION
// ==========================
int calculateSCurveDelay(long currentStepInRamp, long totalRampSteps) {
  // Uses a cosine function to create a smooth S-curve for acceleration/deceleration.
  float cos_input = (float)currentStepInRamp / totalRampSteps;
  float cos_output = cos(cos_input * PI); // cos() goes from 1 to -1 as input goes from 0 to PI
  float multiplier = (1.0 - cos_output) / 2.0; // Scale to a 0.0 to 1.0 range

  int delayRange = initialStepDelay - minStepDelay;
  return initialStepDelay - (int)(delayRange * multiplier);
}

// ==========================
// ACCELERATED STEP FUNCTION
// ==========================
int stepWithAcceleration() {
  // This function now applies accel/decel only on the first and last rotations.
  int delayNow;
  long currentTurn = stepCount / stepsPerTurn; // Which rotation are we on?
  long stepsIntoTurn = stepCount % stepsPerTurn; // How many steps into the current rotation?

  if(currentTurn == 0 && stepsIntoTurn < accelSteps) {
    // ACCELERATE: Only on the first part of the first rotation
    delayNow = calculateSCurveDelay(stepsIntoTurn, accelSteps);
  } 
  else if(currentTurn == (targetTurns - 1) && stepsIntoTurn >= (stepsPerTurn - accelSteps)) {
    // DECELERATE: Only on the last part of the last rotation
    long decelStepCount = stepsIntoTurn - (stepsPerTurn - accelSteps);
    delayNow = calculateSCurveDelay(accelSteps - decelStepCount, accelSteps);
  } 
  else {
    // CONSTANT SPEED
    delayNow = minStepDelay;
  }

  // Ensure delay doesn't go below the minimum
  if (delayNow < minStepDelay) delayNow = minStepDelay;

  digitalWrite(STEP_PIN, HIGH);
  delayMicroseconds(delayNow);
  digitalWrite(STEP_PIN, LOW);
  delayMicroseconds(delayNow);

  stepCount++;

  return delayNow;
}

void calculateAvgTurnLength() {
  if (bobbinLength <= 0 || bobbinWidth <= 0 || wireDiameter <= 0 || targetTurns <= 0) {
    avgTurnLength = 0; // Not enough info to calculate
    return;
  }

  // Calculate the perimeter of the core (first turn)
  float corePerimeter = (2 * bobbinLength) + (PI * bobbinWidth);

  // Estimate the thickness of the wire winding on one side
  long turnsPerLayerNow = (long)(bobbinHeight / wireDiameter);
  if (turnsPerLayerNow <= 0) turnsPerLayerNow = 1;
  float totalLayers = (float)targetTurns / turnsPerLayerNow;
  float windingThickness = totalLayers * wireDiameter;

  // Calculate the perimeter of the fully wound coil (last turn)
  float finalPerimeter = (2 * bobbinLength) + (PI * (bobbinWidth + 2 * windingThickness));
  avgTurnLength = (corePerimeter + finalPerimeter) / 2.0;
}

bool checkSerial() {
  // More memory-efficient serial reading
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { // Handle newline or carriage return
      if (inputIndex > 0) {
        inputBuffer[inputIndex] = '\0'; // Null-terminate the string
        inputIndex = 0; // Reset for next command
        return true; // Command is ready
      }
    } else if (inputIndex < (MAX_CMD_LENGTH - 1)) {
      // Convert command to uppercase as it's typed
      inputBuffer[inputIndex++] = toupper(c);
    }
  }
  return false; // No command ready
}

void printStatus() {
  Serial.println(F("--- CURRENT STATUS ---"));
  Serial.print(F("Outputs Enabled: ")); Serial.println(outputsEnabled ? F("YES") : F("NO"));
  Serial.print(F("Winding Active: ")); Serial.print(running ? F("YES") : F("NO"));
  if (paused) Serial.print(F(" (PAUSED)"));
  Serial.println();
  Serial.print(F("Target Turns: ")); Serial.println(targetTurns);
  Serial.print(F("Current Turns: ")); Serial.println(stepCount / stepsPerTurn);

  // Calculate max speed from minStepDelay
  long speed_sps = 0;
  if (minStepDelay > 0) speed_sps = 1000000UL / (minStepDelay * 2);
  Serial.print(F("Max Speed: ")); Serial.print(speed_sps); Serial.println(F(" steps/sec"));
  Serial.print(F("Initial/Final Speed Delay: ")); Serial.print(initialStepDelay); Serial.println(F(" us"));
  Serial.print(F("Acceleration Steps: ")); Serial.println(accelSteps);

  Serial.print(F("Turns per Layer: ")); Serial.println(turnsPerLayer);
  Serial.print(F("Wire Diameter: ")); Serial.println(wireDiameter);
  if (wireDiameter > 0) {
    const float COPPER_RESISTIVITY = 1.68E-8; // Ohm-meters (Ω·m)
    float radius_m = (wireDiameter / 2.0) / 1000.0;
    float area_m2 = PI * radius_m * radius_m;
    float ohm_per_meter = COPPER_RESISTIVITY / area_m2;
    Serial.print(F("Wire Resistance: ")); Serial.print(ohm_per_meter, 2); Serial.println(F(" Ohm/meter"));
  }

  Serial.print(F("Bobbin L/W/H: ")); Serial.print(bobbinLength); Serial.print(F("/")); Serial.print(bobbinWidth); Serial.print(F("/")); Serial.println(bobbinHeight);

  Serial.print(F("Servo Min/Max: ")); Serial.print(servoMinAngle); Serial.print(F("/")); Serial.println(servoMaxAngle);
  Serial.print(F("Servo Increment/Turn: ")); Serial.println(servoIncrementPerTurn, 8);
  Serial.print(F("Avg Turn Length: ")); Serial.print(avgTurnLength); Serial.println(F(" mm"));

  // --- Last CALC command info ---
  if (lastCalcRequestedResistance > 0) {
    Serial.print(F("Last CALC Target R: ")); Serial.print(lastCalcRequestedResistance, 2); Serial.println(F(" Ohms"));
  }

  // --- Calculate and display estimated DC Resistance ---
  if (targetTurns > 0 && wireDiameter > 0 && avgTurnLength > 0) {
    const float COPPER_RESISTIVITY = 1.68E-8; // Ohm-meters (Ω·m)
    
    // Calculate total wire length in meters
    float totalLength_m = (float)targetTurns * avgTurnLength / 1000.0;
    Serial.print(F("Est. Wire Length: ")); Serial.print(totalLength_m, 2); Serial.println(F(" meters"));

    // Calculate wire cross-sectional area in square meters
    float radius_m = (wireDiameter / 2.0) / 1000.0;
    float area_m2 = PI * radius_m * radius_m;

    // Calculate resistance: R = ρ * (L/A)
    float resistance = COPPER_RESISTIVITY * (totalLength_m / area_m2);
    Serial.print(F("Est. DC Resistance: ")); Serial.print(resistance, 2); Serial.println(F(" Ohms"));
  }
  Serial.println(F("----------------------"));
}

// ==========================
// SERIAL COMMANDS
// ==========================
void processCommand(char* cmd) {
  lastCommandTime = millis(); 

  if (strncmp(cmd, "START", 5) == 0) {
    // Check for verbose flag "-V"
    if (strstr(cmd, "-V") != NULL) {
      verboseMode = true;
      Serial.println(F("INFO: Verbose mode enabled."));
    } else {
      verboseMode = false;
    }

    // Show the status before starting
    printStatus();
	digitalWrite(DIR_PIN, stepperForward ? HIGH : LOW);
    // A new START command always begins from scratch.    
    enableOutputs();
    servoPos = servoMinAngle; // Reset servo to start position
    layServo.write((int)servoPos); // Immediately move servo to the start position
    delay(300); // Give the servo a moment to reach its start position
    totalSteps = targetTurns * stepsPerTurn;
    stepCount = 0; // Reset acceleration counter
    running = true; 
    paused = false;
    Serial.println(F("STATUS: Winding STARTED"));
    return;
  }

  if (strcmp(cmd, "PAUSE") == 0) {
    if (running) {
      running = false;
      paused = true;
      Serial.println(F("STATUS: Winding PAUSED"));
    }
    return;
  }

  if (strcmp(cmd, "RESUME") == 0) {
    if (paused) {
      enableOutputs();
      running = true;
      paused = false;
      Serial.println(F("STATUS: Winding RESUMED"));
    }
    return;
  }

  if (strcmp(cmd, "STOP") == 0) { 
    running = false; 
    verboseMode = false; // Disable verbose mode on stop
    Serial.println(F("STATUS: Winding STOPPED")); 
    return; 
  }
  if (strncmp(cmd, "COUNT ", 6) == 0) { 
    targetTurns = atol(cmd + 6); 
    stepCount = 0; 
    calculateAvgTurnLength(); // Recalculate with new turn count
    lastCalcRequestedResistance = 0.0; // Reset, as COUNT overrides CALC
    Serial.print(F("PARAM: Target turns = ")); Serial.println(targetTurns); return; 
  }  
  if (strncmp(cmd, "S ", 2) == 0) {
    int speed = atoi(cmd + 2);
    if (speed > 0) {
      minStepDelay = 1000000UL / speed / 2;
      Serial.print(F("PARAM: Speed set to ")); Serial.print(speed); Serial.print(F(" steps/sec (delay: ")); Serial.print(minStepDelay); Serial.println(F("us)"));
    }
    return;
  }

  if (strncmp(cmd, "ACCEL ", 6) == 0) {
    long steps = atol(cmd + 6);
    if (steps > 0) {
      accelSteps = steps;
      Serial.print(F("PARAM: Acceleration steps set to ")); Serial.println(accelSteps);
    }
    return;
  }

  if (strncmp(cmd, "SPEED ", 6) == 0) {
    int delay = atoi(cmd + 6);
    if (delay > minStepDelay) { // Must be slower than max speed
      initialStepDelay = delay;
      Serial.print(F("PARAM: Initial step delay set to ")); Serial.print(initialStepDelay); Serial.println(F("us"));
    } else {
      Serial.println(F("ERROR: Initial delay must be greater than min step delay."));
    }
    return;
  }

  if (strncmp(cmd, "CALIBRATE_SERVO ", 16) == 0) {
    char* minStr = cmd + 16;
    enableOutputs();
    char* maxStr = strchr(minStr, ' ');
    if (maxStr == NULL) { Serial.println(F("ERROR: Invalid CALIBRATE_SERVO format")); return; }
    *maxStr = '\0'; // Split the string
    float minA = atof(minStr);
    float maxA = atof(maxStr + 1);
    servoMinAngle = minA; servoMaxAngle = maxA; 
    updateAndValidate(); // Validate new values and re-calculate
    Serial.print(F("PARAM: Servo Min Angle = ")); Serial.println(servoMinAngle);
    Serial.print(F("PARAM: Servo Max Angle = ")); Serial.println(servoMaxAngle);
    layServo.write((int)servoMinAngle); delay(200);
    layServo.write((int)servoMaxAngle); delay(200);
    layServo.write((int)servoMinAngle);
    disableOutputs();
    return;
  }

  if (strncmp(cmd, "TEST_SERVO ", 11) == 0) {
    enableServo();
    layServo.write(atoi(cmd + 11));
    Serial.println(F("STATUS: Servo moved."));
    delay(500); // Give servo time to move to position before detaching
    disableServo();
    return;
  }
  if (strncmp(cmd, "TEST_LAYER", 10) == 0) {
    // Default test values, using current configuration
    long testTurns = turnsPerLayer;
    int testMinStepDelay = minStepDelay;
    float testMinAngle = servoMinAngle;
    float testMaxAngle = servoMaxAngle;
    bool resume = false;

    // New parser for arguments like C8000 S50 A20
    char* args = cmd + 10;
    char* token = strtok(args, " "); // Use a local running flag for parsing
    while (token != NULL) {
        switch (token[0]) {
            case 'S': // Speed (Steps/sec)
                {
                    int speed = atoi(token + 1);
                    if (speed > 0) testMinStepDelay = 1000000UL / speed / 2;
                }
                break;
            case 'C': // Turns (Count)
                testTurns = atol(token + 1);
                break;
            case 'A': // Angle (servo sweep)
                {
                    float sweepAngle = atof(token + 1);
                    if (sweepAngle > 0 && sweepAngle <= 180) {
                        float center = (servoMinAngle + servoMaxAngle) / 2.0;
                        testMinAngle = center - sweepAngle / 2.0;
                        testMaxAngle = center + sweepAngle / 2.0;
                    }
                }
                break;
            case 'R': // Resume
                if (strcmp(token + 1, "1") == 0) {
                    resume = true;
                }
                break;
        }
        token = strtok(NULL, " ");
    }

    // --- FIX: Calculate a local servo increment for this specific test ---
    float testSweepAngle = testMaxAngle - testMinAngle;
    float testServoIncrement = testSweepAngle / testTurns;
    if (testTurns <= 0) testServoIncrement = 0; // Avoid division by zero
    // ---

    if (!resume) {
        servoPos = testMinAngle; // Reset servo to start position unless resuming
        layServo.write((int)servoPos); // Immediately move servo to the start position
    }

    enableOutputs();
    Serial.println(F("INFO: Testing 1 layer..."));
    Serial.print(F("  - Turns: ")); Serial.println(testTurns);
    Serial.print(F("  - Speed Delay (us): ")); Serial.println(testMinStepDelay);
    Serial.print(F("  - Servo Sweep: ")); Serial.print(testMinAngle); Serial.print(F(" to ")); Serial.println(testMaxAngle);

    totalSteps = testTurns * stepsPerTurn;
    stepCount = 0;

    digitalWrite(DIR_PIN, stepperForward ? HIGH : LOW);
    running = true; // Set running flag for the test
    while(stepCount < totalSteps && running) {
        if (checkSerial()) { // Check for STOP command
            // Only process STOP or Speed commands during test, ignore others.
            if (strcmp(inputBuffer, "STOP") == 0 || strncmp(inputBuffer, "S ", 2) == 0) {
                processCommand(inputBuffer);
                if (strncmp(inputBuffer, "S ", 2) == 0) testMinStepDelay = minStepDelay; // Update test speed
            }
        }
        if (!running) break; // Exit loop immediately if STOP was received
        
        int delayNow = testMinStepDelay; // For simplicity, test runs at constant speed
        digitalWrite(STEP_PIN, HIGH); delayMicroseconds(delayNow);
        digitalWrite(STEP_PIN, LOW); delayMicroseconds(delayNow);
        stepCount++;


        // Print status for every completed turn
        if (stepCount > 0 && stepCount % stepsPerTurn == 0) {
            long currentTurn = stepCount / stepsPerTurn;
            Serial.print(F("  -> Turn: "));
            Serial.print(currentTurn);
            Serial.print(F(" | Servo Pos: "));
            Serial.println(servoPos);

            // Move servo to position for the NEXT turn
            servoPos += testServoIncrement;
            if (servoPos >= testMaxAngle || servoPos <= testMinAngle) { testServoIncrement = -testServoIncrement; }
            layServo.write((int)servoPos);
        }
    }
    Serial.println(running ? F("STATUS: Layer test done.") : F("STATUS: Test STOPPED."));
    running = false; // Ensure running is false after test
    disableOutputs();
    return;
  }  

  if (strcmp(cmd, "ENABLE") == 0) { enableOutputs(); return; }
  if (strcmp(cmd, "DISABLE") == 0) { disableOutputs(); return; }
  if (strcmp(cmd, "DISABLE_STEPPER") == 0) { digitalWrite(EN_PIN,HIGH); Serial.println(F("STATUS: Stepper DISABLED")); return; }
  if (strcmp(cmd, "ENABLE_STEPPER") == 0) { digitalWrite(EN_PIN,LOW); Serial.println(F("STATUS: Stepper ENABLED")); return; }
  if (strcmp(cmd, "DISABLE_SERVO") == 0) { if(layServo.attached()) layServo.detach(); Serial.println(F("STATUS: Servo DISABLED")); return; }
  if (strcmp(cmd, "ENABLE_SERVO") == 0) { if(!layServo.attached()) layServo.attach(SERVO_PIN); Serial.println(F("STATUS: Servo ENABLED")); return; }

  if (strcmp(cmd, "SAVE") == 0) { saveSettings(); return; }
  if (strcmp(cmd, "LOAD") == 0) { loadSettings(); updateAndValidate(); return; }

  if (strncmp(cmd, "TIMEOUT ", 8) == 0) { timeoutLimit = atol(cmd + 8); Serial.print(F("PARAM: Timeout = ")); Serial.println(timeoutLimit); return; }

  if (strncmp(cmd, "DIR ", 4) == 0) { stepperForward = (strcmp(cmd + 4, "FWD") == 0); Serial.print(F("PARAM: Stepper direction = ")); Serial.println(stepperForward ? "FWD" : "REV"); return; }

  if (strncmp(cmd, "WIRE_DIA ", 9) == 0) {
    wireDiameter = atof(cmd + 9);
    updateAndValidate(); // Validate & re-calculate dependent params
    calculateAvgTurnLength(); // Recalculate turn length    
    Serial.print(F("PARAM: Wire diameter = ")); Serial.println(wireDiameter);
    return;
  }
  
  if (strncmp(cmd, "BOBBIN ", 7) == 0) {
    char* l_str = cmd + 7;
    char* w_str = strchr(l_str, ' ');
    char* h_str = (w_str != NULL) ? strchr(w_str + 1, ' ') : NULL;

    if (h_str == NULL) {
      Serial.println(F("ERROR: Invalid BOBBIN format. Use: BOBBIN <len> <wid> <hgt>"));
      return;
    }
    *w_str = '\0';
    *h_str = '\0'; // h_str points to the space before the height value

    // --- FIX: Validate that all three values are present before assigning ---
    float l = atof(l_str);
    float w = atof(w_str + 1);
    float h = atof(h_str + 1);

    if (l <= 0 || w <= 0 || h <= 0) {
      Serial.println(F("ERROR: Bobbin dimensions must be positive numbers."));
      return;
    }

    bobbinLength = l;
    bobbinWidth = w;
    bobbinHeight = h;

    updateAndValidate(); // Validate new dimensions and re-calc turnsPerLayer
    calculateAvgTurnLength(); // Calculate the avg turn length from new dimensions

    Serial.println(F("PARAM: Bobbin dimensions updated:"));
    Serial.print(F("  - Length: ")); Serial.print(bobbinLength); Serial.println(F(" mm"));
    Serial.print(F("  - Width: ")); Serial.print(bobbinWidth); Serial.println(F(" mm"));
    Serial.print(F("  - Height: ")); Serial.print(bobbinHeight); Serial.println(F(" mm"));    
    if (avgTurnLength > 0) {
      Serial.print(F("  - Calculated Avg Turn Length: ")); Serial.print(avgTurnLength); Serial.println(F(" mm"));
    } else {
      Serial.println(F("  - Avg Turn Length will be calculated after setting COUNT."));
    }
    return;
  }

  if (strncmp(cmd, "CALC ", 5) == 0) {
    // --- Intelligent check for required parameters ---
    bool ready = true;
    if (bobbinLength <= 0 || bobbinWidth <= 0 || bobbinHeight <= 0) {
      Serial.println(F("ERROR: Bobbin dimensions not set. Use: BOBBIN <L> <W> <H>"));
      ready = false;
    }
    if (wireDiameter <= 0) {
      Serial.println(F("ERROR: Wire diameter not set. Use: WIRE_DIA <mm>"));
      ready = false;
    }
    if (!ready) return;
    // ---

    char* val_str = cmd + 5;
    float targetResistance = atof(val_str);
    char unit = toupper(val_str[strlen(val_str) - 1]);

    if (unit == 'K') {
      targetResistance *= 1000.0;
    } else if (unit != 'R') {
      Serial.println(F("ERROR: Invalid CALC format. Use: CALC <value>R or CALC <value>K"));
      return;
    }

    if (targetResistance <= 0) {
      Serial.println(F("ERROR: Target resistance must be positive."));
      return;
    }

    Serial.print(F("INFO: Calculating turns for ")); Serial.print(targetResistance, 2); Serial.println(F(" Ohms..."));
    lastCalcRequestedResistance = targetResistance; // Store the requested resistance

    // --- Iterative calculation to find targetTurns ---
    const float COPPER_RESISTIVITY = 1.68E-8; // Ohm-meters (Ω·m)
    float radius_m = (wireDiameter / 2.0) / 1000.0;
    float area_m2 = PI * radius_m * radius_m;

    long calculatedTurns = 1000; // Start with a guess
    for (int i = 0; i < 10; i++) { // Iterate a few times for convergence
      // Temporarily set targetTurns to calculate the avgTurnLength for this iteration
      targetTurns = calculatedTurns;
      calculateAvgTurnLength();

      if (avgTurnLength <= 0) { // Should not happen if params are set
        Serial.println(F("ERROR: Could not calculate average turn length."));
        targetTurns = 0; // Reset
        return;
      }

      // Reverse the resistance formula to solve for turns
      // R = ρ * (L/A) => L = R*A/ρ
      // L = turns * avg_len => turns = L / avg_len
      float totalLength_m = (targetResistance * area_m2) / COPPER_RESISTIVITY;
      calculatedTurns = (long)((totalLength_m * 1000.0) / avgTurnLength);
    }

    // Final update with the calculated turns
    targetTurns = calculatedTurns;
    calculateAvgTurnLength(); // Final calculation for avgTurnLength
    float finalLength_m = (float)targetTurns * avgTurnLength / 1000.0;

    Serial.println(F("--- CALCULATION RESULTS ---"));
    Serial.println(F("  Inputs:"));
    Serial.print(F("  - Target Resistance: ")); Serial.print(targetResistance, 2); Serial.println(F(" Ohms"));
    Serial.print(F("  - Bobbin (L/W/H):  ")); Serial.print(bobbinLength); Serial.print(F("/")); Serial.print(bobbinWidth); Serial.print(F("/")); Serial.print(bobbinHeight); Serial.println(F(" mm"));
    Serial.print(F("  - Wire Diameter:     ")); Serial.print(wireDiameter); Serial.println(F(" mm"));
    float ohm_per_meter = COPPER_RESISTIVITY / area_m2;
    Serial.print(F("  - Wire Resistance:   ")); Serial.print(ohm_per_meter, 2); Serial.println(F(" Ohm/meter"));
    Serial.println(F("  Outputs:"));
    Serial.print(F("  - Required Turns:    ")); Serial.println(targetTurns);
    Serial.print(F("  - Est. Wire Length:  ")); Serial.print(finalLength_m, 2); Serial.println(F(" meters"));
    Serial.println(F("---------------------------"));
    Serial.println(F("STATUS: Target turns updated."));

    return;
  }

  if (strcmp(cmd, "TEST_STEPPER") == 0) {
    enableOutputs();
    Serial.println(F("INFO: Stepper buzz test (50 steps)..."));
    digitalWrite(DIR_PIN, HIGH); // Use a consistent direction
    for(int i=0; i<50; i++){
      digitalWrite(STEP_PIN,HIGH); delayMicroseconds(500);
      digitalWrite(STEP_PIN,LOW); delayMicroseconds(500);
    }
    Serial.println(F("STATUS: Stepper buzz test done."));
    disableOutputs();
    return;
  }

  // TEST_STEPPER_MOVE with SPEED support
  if (strncmp(cmd, "TEST_STEPPER_MOVE ", 18) == 0) {
    long stepsToMove = 1600; // Default: one revolution at 1/8 microstepping
    int speed = 1000; // Default speed in steps/sec
    bool dirFwd = true;

    char* args = cmd + 18;
    char* token = strtok(args, " ");
    while (token != NULL) {
        if (strcmp(token, "FWD") == 0) dirFwd = true;
        else if (strcmp(token, "REV") == 0) dirFwd = false;
        else if (token[0] == 'S' && isdigit(token[1])) speed = atoi(token + 1);
        else if (isdigit(token[0])) stepsToMove = atol(token);
        token = strtok(NULL, " ");
    }

    if (speed <= 0) speed = 1000; // Safety check for speed
    unsigned long stepDelayHalf = 1000000UL / speed / 2;

    Serial.print(F("INFO: Stepper moving ")); Serial.print(stepsToMove); Serial.print(F(" steps ")); Serial.print(dirFwd ? "FWD" : "REV"); Serial.print(F(" at ")); Serial.print(speed); Serial.println(F(" steps/sec"));

    enableOutputs();
    digitalWrite(DIR_PIN, dirFwd ? HIGH : LOW);
    for(long i=0; i < stepsToMove; i++){
      digitalWrite(STEP_PIN,HIGH);
      delayMicroseconds(stepDelayHalf);
      digitalWrite(STEP_PIN,LOW);
      delayMicroseconds(stepDelayHalf);
    }
    Serial.println(F("STATUS: Stepper test move completed."));
    disableOutputs();
    return;
  }

  if (strcmp(cmd, "RESTORE_DEFAULTS") == 0) {
    Serial.println(F("INFO: Restoring all settings to factory defaults."));
    clearEEPROM();
    // Re-initialize variables to their hardcoded defaults by calling setup functions
    loadSettings(); // This will now load defaults due to sanity checks on cleared EEPROM
    lastCalcRequestedResistance = 0.0; // Explicitly clear this
    updateAndValidate();
    saveSettings(); // Persist the fresh defaults
    return;
  }
  if (strcmp(cmd, "STATUS") == 0) {
    printStatus();
    return;
  }

  if (strcmp(cmd, "HELP") == 0) {
    Serial.println(F(
      "Commands:\nSTART [-V]\nSTOP\nPAUSE\nRESUME\nSTATUS\nRESTORE_DEFAULTS\nCOUNT <turns>\nS <steps/sec>\nSPEED <delay_us>\nACCEL <steps>\nCALIBRATE_SERVO <min> <max>\nTEST_SERVO <angle>\nTEST_LAYER [S<speed>] [C<turns>] [A<angle>] [R1]\nENABLE\nDISABLE\nSAVE\nLOAD\nTIMEOUT <ms>\nDIR <FWD/REV>\nWIRE_DIA <mm>\nBOBBIN <L> <W> <H>\nCALC <val>R/K\nHELP"
    ));
    return;
  }

  Serial.println(F("ERROR: Unknown command."));
}

// ==========================
// MAIN LOOP
// ==========================
void loop() {
  if (checkSerial()) {
    processCommand(inputBuffer);
  }

  checkTimeout();

  if(running && outputsEnabled && stepCount < totalSteps){
    // This loop is now non-blocking because the main winding logic is handled one step at a time per main loop() iteration.
    if(running && outputsEnabled){
      int currentDelay = stepWithAcceleration();

      // Print status for every completed turn if in verbose mode
      if (verboseMode && stepCount > 0 && stepCount % stepsPerTurn == 0) {
        long currentTurn = stepCount / stepsPerTurn;
        Serial.print(F("  -> Turn: "));
        Serial.print(currentTurn);
        Serial.print(F(" | Servo Pos: "));
        Serial.println(servoPos);
      }
      
      if (stepCount > 0 && stepCount % stepsPerTurn == 0) {
        // Move servo to position for the NEXT turn
        servoPos += servoIncrementPerTurn;
        if (servoPos >= servoMaxAngle || servoPos <= servoMinAngle) { servoIncrementPerTurn = -servoIncrementPerTurn; }
        layServo.write(servoPos);
      }
    }
    
    if(stepCount >= totalSteps){ 
      running=false; 
      verboseMode = false; // Disable verbose mode on completion
      Serial.println(F("STATUS: Winding completed.")); 
      disableOutputs(); 
    }    
  }
}