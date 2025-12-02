# Guitar Pickup Winder Controller

A desktop application for controlling a DIY guitar pickup winder, featuring a real-time visualization of the winding process. Built with Python and PyQt6.

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Core Component: The Winder Widget](#core-component-the-winder-widget)
- [How It Works](#how-it-works)
- [Hardware & Firmware Controller (Arduino Uno)](#hardware--firmware-controller-arduino-uno)
- [Dependencies](#dependencies)
- [Setup and Installation](#setup-and-installation)
- [Usage](#usage)
- [Future Development](#future-development)
- [Contributing](#contributing)

## Overview

This project is the software controller for a homemade guitar pickup winder. Winding pickups requires precise control over the number of turns and the distribution of the copper wire across the bobbin. This application provides a graphical user interface (GUI) to:

1.  **Configure** winding parameters (e.g., bobbin dimensions, target turns).
2.  **Control** the winder's motors (stepper for rotation, servo for wire guide).
3.  **Monitor** the winding process in real-time with a detailed visual representation.

The heart of the user interface is the `WinderWidget`, a custom PyQt6 widget that displays a dynamic cross-section of the pickup bobbin as it's being wound.

## Features

- **Graphical User Interface**: Easy-to-use interface built with PyQt6.
- **Real-time Winding Visualization**:
    - Displays a cross-section of the bobbin.
    - Shows the wire guide (servo) position.
    - Visualizes the wire building up in layers.
    - Renders dimension lines for bobbin length and height.
- **Configurable Winding Parameters**:
    - Bobbin Length & Height
    - Wire Diameter
    - Target Number of Turns
    - Turns Per Layer
    - Servo Travel Limits (Min/Max Angle)
- **Live Progress Tracking**: See the current turn count and its relation to the target.
- **Accurate Layer Simulation**: The visualization correctly models the back-and-forth traversal of the wire guide for each layer.

## Core Component: The Winder Widget

The file `winder_widget.py` contains the `WinderWidget` class, which is responsible for all the graphics.

### How it Renders:

1.  **Bobbin**: Draws a brown, T-shaped cross-section representing the bobbin's top and bottom flanges. The drawing is scaled to fit the widget's size.
2.  **Wire Guide**: A cyan line and circle at the top represent the wire guide, which is controlled by a servo. Its horizontal position is calculated based on the winding progress.
3.  **Winding Progress (`pos_ratio`)**: The widget calculates a `pos_ratio` (a value from 0.0 to 1.0) that represents the guide's position across the bobbin. It intelligently determines the direction of travel:
    - On even-numbered layers (0, 2, 4...), it moves from left to right (0.0 → 1.0).
    - On odd-numbered layers (1, 3, 5...), it moves from right to left (1.0 → 0.0).
4.  **Wire Buildup**: As the winding progresses, the widget draws vertical "gold" lines to represent the strands of wire. A new line is added only when the guide has moved a distance equivalent to one wire diameter, creating a realistic depiction of the coil.
5.  **Live Wire**: A single line is drawn from the wire guide down to the bobbin, showing the path of the wire currently being laid.

## How It Works

The application operates on a simple but effective principle:

1.  **User Input**: The user enters the physical characteristics of their pickup bobbin and the desired number of turns into the GUI.
2.  **Calculation**: The software calculates the number of turns that will fit in a single layer (`turns_per_layer`).
3.  **Motor Control**:
    - A **stepper motor** is commanded to turn the bobbin. It counts each rotation.
    - A **servo motor** is used to move the wire guide back and forth across the bobbin's length.
4.  **Synchronization**: The application synchronizes the servo's position with the stepper's turn count. The `pos_ratio` from the widget is mapped to the servo's angular range (`servo_min_angle` to `servo_max_angle`) and sent to the physical controller (e.g., an Arduino or ESP32).
5.  **Feedback**: The `WinderWidget` receives live data (current turns, servo position) from the controller part of the application and updates the display, giving the user immediate visual feedback.

## Hardware & Firmware Controller (Arduino Uno)

The Python application acts as the "brain," but the Arduino Uno is the "muscle," responsible for the real-time control of the motors.

### Role of the Firmware

- **Receives Commands**: Listens for commands sent over the serial port from the Python GUI (e.g., start/stop winding, set parameters).
- **Controls Motors**:
    - **Stepper Motor**: Precisely rotates the pickup bobbin. It uses a library like `AccelStepper` for smooth acceleration and constant speed.
    - **Servo Motor**: Moves the wire guide back and forth. Its position is updated continuously based on the winding progress.
- **Sends Feedback**: Reports the current turn count and status back to the Python application for live monitoring.

### Required Hardware

- **Microcontroller**: Arduino Uno.
- **Stepper Motor Driver**: A4988 or DRV8825. These drivers are ideal for controlling a stepper motor with an Arduino.
- **Stepper Motor**: NEMA 17 is a popular size for this application.
- **Servo Motor**: A standard SG90 micro servo is sufficient, but a more robust metal-gear servo (like an MG996R) is recommended for durability.

### Serial Communication Protocol

A simple text-based protocol is used for communication between the PC and the microcontroller.

**Commands from PC to Arduino (sent from Python):**

- `START:<target_turns>:<servo_min>:<servo_max>`: Starts the winding process.
    - Example: `START:8000:70:100`
- `STOP`: Immediately halts the winding process.
- `RESET`: Resets the turn counter to zero.

**Feedback from Arduino to PC (read by Python):**

- `TURN:<count>`: Reports the current number of turns.
    - Example: `TURN:1234`
- `STATUS:<message>`: Reports the current state.
    - Examples: `STATUS:IDLE`, `STATUS:WINDING`, `STATUS:DONE`

### Firmware Setup

1.  **Install Arduino IDE or PlatformIO**: Choose your preferred development environment.
2.  **Install Libraries**: From the library manager, install:
    - `AccelStepper` (by Mike McCauley)
    - `Servo` (usually built-in)
3.  **Configure Pins**: Open the `.ino` sketch and modify the pin definitions at the top of the file to match your hardware wiring.
4.  **Upload**: Compile and upload the sketch to your microcontroller board.

## Dependencies

This project requires Python 3 and the following library:

- **PyQt6**: For the graphical user interface.

```bash
pip install PyQt6
```

The physical winder itself would likely be controlled by a microcontroller (like an Arduino or ESP32) running its own firmware, communicating with this Python application over a serial port.

## Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/krelsaid/Pickup-Winder.git
    cd pickup-winder
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: You may need to create a `requirements.txt` file containing `PyQt6`)*

## Usage

1.  Run the main application file:
    ```bash
    python main_window.py
    ```
    *(Assuming the main entry point is `main_window.py`)*

2.  Connect to the winder hardware via the appropriate serial port in the GUI.
3.  Enter your bobbin and wire specifications in the settings panel.
4.  Set the target number of turns.
5.  Click the "Start Winding" button to begin the process.
6.  Monitor the progress on the visualization widget.

## Future Development

- [ ] Implement serial communication to control an Arduino/ESP32.
- [ ] Add presets for common pickup types (Strat, Tele, P-90, Humbucker).
- [ ] Add scatter winding options for a more "hand-wound" sound.
- [ ] Graph winding tension if a load cell is added to the hardware.
- [ ] Save and load winding job configurations to a file.

