import re
import logging
import configparser
import json
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QDialog, QMessageBox,
                             QTextEdit, QLineEdit, QComboBox, QLabel, QGridLayout, QTabWidget, QGroupBox, QSpinBox, QSlider, QDialogButtonBox, QFileDialog)
                             
from PyQt6.QtWidgets import QDoubleSpinBox
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtCore import QThread, pyqtSignal, QSize, Qt, QTimer
from PyQt6.QtGui import QFont


from serial_worker import SerialWorker
from winder_widget import WinderWidget

# --- Application Info ---
__version__ = "1.1.0"
__author__ = "khairil said"
__date__ = "2025-02-13"

class SettingsDialog(QDialog):
    """A dialog for application settings."""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")

        self.layout = QVBoxLayout(self)
        form_layout = QGridLayout()

        # Max Speed Setting
        self.max_speed_input = QSpinBox()
        self.max_speed_input.setRange(1000, 50000)
        self.max_speed_input.setSingleStep(100)
        self.max_speed_input.setValue(self.config.getint('Winder', 'max_speed'))
        form_layout.addWidget(QLabel("Max Winder Speed (steps/sec):"), 0, 0)
        form_layout.addWidget(self.max_speed_input, 0, 1)

        self.layout.addLayout(form_layout)

        # Dialog Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

class MainWindow(QMainWindow):
    # Signal to send a command to the worker thread
    send_command_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        logging.info("Initializing MainWindow.")
        self.load_config()
        self.setWindowTitle("Pickup Winder Control")
        self.setGeometry(100, 100, 900, 700)

        # --- Central Widget and Layout ---
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)

        # --- Create UI Panels ---
        self.create_menu_bar()
        self.create_left_panel()
        self.create_right_panel()

        # Set initial display values from controls
        self.update_speed_display(self.speed_input.value())

        # --- Setup Serial Worker ---
        self.setup_serial_worker()


    def load_config(self):
        """Loads settings from config.ini."""
        self.config = configparser.ConfigParser()
        # Provide default values
        self.config['Winder'] = {'max_speed': '5000'}
        
        if not self.config.read('config.ini'):
            logging.warning("config.ini not found. Creating with default values.")
            with open('config.ini', 'w') as configfile:
                self.config.write(configfile)
        logging.info(f"Loaded config. Max speed: {self.config.getint('Winder', 'max_speed')}")

    def save_config(self):
        """Saves the current config to config.ini."""
        try:
            with open('config.ini', 'w') as configfile:
                self.config.write(configfile)
            logging.info("Configuration saved to config.ini.")
        except IOError as e:
            logging.error(f"Failed to save config.ini: {e}")

    def create_left_panel(self):
        left_layout = QVBoxLayout()

        # --- Connection Group ---
        connection_group = QGroupBox("Serial Connection")
        connection_layout = QGridLayout()
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.connect_button = QPushButton("Connect")
        connection_layout.addWidget(QLabel("COM Port:"), 0, 0)
        connection_layout.addWidget(self.port_combo, 0, 1)
        connection_layout.addWidget(self.refresh_button, 0, 2)
        connection_layout.addWidget(self.connect_button, 1, 0, 1, 3)
        connection_group.setLayout(connection_layout)
        left_layout.addWidget(connection_group)

        # --- Live View ---
        live_view_group = QGroupBox("Live Winder View")
        live_view_layout = QVBoxLayout()
        self.winder_widget = WinderWidget()
        live_view_layout.addWidget(self.winder_widget)
        live_view_group.setLayout(live_view_layout)
        left_layout.addWidget(live_view_group)

        # --- Info Panel ---
        info_group = QGroupBox("Winder Info")
        self.info_layout = QGridLayout()
        self.info_labels = {
            "Turns": QLabel("0 / 0"),
            "Speed": QLabel("0 steps/sec"),
            "Wire Dia": QLabel("0.0 mm"),
            "Bobbin": QLabel("0/0/0 mm"),
            "Est. R": QLabel("0 Ohms"),
        }
        row = 0
        for name, label in self.info_labels.items():
            self.info_layout.addWidget(QLabel(f"{name}:"), row, 0)
            self.info_layout.addWidget(label, row, 1)
            row += 1
        info_group.setLayout(self.info_layout)
        left_layout.addWidget(info_group)

        left_layout.addStretch()
        self.main_layout.addLayout(left_layout, 1)

    def create_right_panel(self):
        right_layout = QVBoxLayout()

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.create_control_tab()
        self.create_calc_tab()
        self.create_test_tab()
        self.create_gui_sweep_tab()
        self.create_servo_config_tab()
        right_layout.addWidget(self.tabs)

        # --- Serial Log ---
        log_group = QGroupBox("Serial Log")
        log_layout = QGridLayout()
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setFont(QFont("Courier", 9))

        self.clear_log_button = QPushButton("Clear Log")
        self.clear_log_button.clicked.connect(self.log_output.clear)

        log_layout.addWidget(self.log_output, 0, 0, 1, 2)
        log_layout.addWidget(self.clear_log_button, 1, 1) # Add button to the bottom-right

        log_group.setLayout(log_layout)
        right_layout.addWidget(log_group, 1)

        self.main_layout.addLayout(right_layout, 2)

    def create_control_tab(self):
        tab = QWidget()
        layout = QGridLayout()

        # Winding controls
        self.start_button = QPushButton("START")
        self.stop_button = QPushButton("STOP")
        self.pause_button = QPushButton("PAUSE")
        self.resume_button = QPushButton("RESUME")
        
        layout.addWidget(self.start_button, 0, 0)
        layout.addWidget(self.stop_button, 0, 1)
        layout.addWidget(self.pause_button, 1, 0)
        layout.addWidget(self.resume_button, 1, 1)

        # Parameters
        self.turns_input = QLineEdit("8000")
        self.speed_input = QSpinBox()
        self.speed_input.setRange(0, self.config.getint('Winder', 'max_speed'))
        self.speed_input.setValue(4000)

        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(0, self.config.getint('Winder', 'max_speed'))
        self.speed_slider.setValue(4000)

        # Connect slider and spinbox
        self.speed_input.valueChanged.connect(self.update_speed_display) # Update display in real-time
        self.speed_input.valueChanged.connect(self.speed_slider.setValue)
        self.speed_slider.valueChanged.connect(self.speed_input.setValue)

        # Send speed update only when interaction is finished
        # to avoid flooding the serial port with commands.
        # This handles both text entry and arrow clicks for the spinbox
        self.speed_slider.sliderReleased.connect(self.update_speed_from_slider)
        self.speed_input.editingFinished.connect(self.update_speed_from_spinbox)
        layout.addWidget(QLabel("Target Turns:"), 2, 0)
        layout.addWidget(self.turns_input, 2, 1, 1, 2)
        layout.addWidget(QLabel("Speed (steps/sec):"), 3, 0)
        layout.addWidget(self.speed_input, 3, 1)
        layout.addWidget(self.speed_slider, 3, 2)
        
        # Winding direction
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Fwd", "Rev"])
        layout.addWidget(QLabel("Direction:"), 4, 0)
        layout.addWidget(self.direction_combo, 4, 1, 1, 1)

        # Sweep Control source
        self.sweep_control_combo = QComboBox()
        self.sweep_control_combo.addItems(["Firmware", "GUI (Live)", "GUI (Pattern)"])
        self.sweep_control_combo.setToolTip("Choose the source of servo sweep control.\nFirmware: Device handles sweep internally.\nGUI: This app calculates and sends servo positions in real-time.")
        layout.addWidget(QLabel("Sweep Control:"), 5, 0)
        layout.addWidget(self.sweep_control_combo, 5, 1, 1, 2)
        self.sweep_control_combo.currentTextChanged.connect(self.update_sweep_control_source)

        # Motor enable/disable controls
        motor_control_group = QGroupBox("Motor Toggles")
        motor_control_layout = QGridLayout()
        
        self.disable_servo_button = QPushButton("Disable Servo")
        self.enable_servo_button = QPushButton("Enable Servo")
        self.disable_stepper_button = QPushButton("Disable Stepper")
        self.enable_stepper_button = QPushButton("Enable Stepper")

        motor_control_layout.addWidget(self.enable_servo_button, 0, 0)
        motor_control_layout.addWidget(self.disable_servo_button, 0, 1)
        motor_control_layout.addWidget(self.enable_stepper_button, 1, 0)
        motor_control_layout.addWidget(self.disable_stepper_button, 1, 1)
        motor_control_group.setLayout(motor_control_layout)
        layout.addWidget(motor_control_group, 6, 0, 1, 3)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "Control")

    def create_calc_tab(self):
        tab = QWidget()
        layout = QGridLayout()
        self.calc_resistance_input = QLineEdit("6.5k")
        self.calc_bobbin_l_input = QLineEdit("60.0")
        self.calc_bobbin_w_input = QLineEdit("4.0")
        self.calc_bobbin_h_input = QLineEdit("9.0")
        self.calc_wire_dia_input = QLineEdit("0.063")
        self.calc_button = QPushButton("Calculate & Set Parameters")
        self.calc_turns_per_layer_label = QLabel("N/A")

        layout.addWidget(QLabel("Target Resistance (e.g. 6.5k):"), 0, 0)
        layout.addWidget(self.calc_resistance_input, 0, 1)
        layout.addWidget(QLabel("Bobbin Length (mm):"), 1, 0)
        layout.addWidget(self.calc_bobbin_l_input, 1, 1)
        layout.addWidget(QLabel("Bobbin Width (mm):"), 2, 0)
        layout.addWidget(self.calc_bobbin_w_input, 2, 1)
        layout.addWidget(QLabel("Bobbin Height (mm):"), 3, 0)
        layout.addWidget(self.calc_bobbin_h_input, 3, 1)
        layout.addWidget(QLabel("Wire Diameter (mm):"), 4, 0)
        layout.addWidget(self.calc_wire_dia_input, 4, 1)
        layout.addWidget(QLabel("<b>Calc. Turns/Layer (Vertical):</b>"), 5, 0)
        layout.addWidget(self.calc_turns_per_layer_label, 5, 1)
        layout.addWidget(self.calc_button, 6, 0, 1, 2)

        # Connect signals for live calculation
        self.calc_bobbin_h_input.textChanged.connect(self.update_turns_per_layer_calc)
        self.calc_wire_dia_input.textChanged.connect(self.update_turns_per_layer_calc)
        # Connect signals to update the live view widget
        self.calc_bobbin_l_input.textChanged.connect(self.update_live_view_dimensions)
        self.calc_bobbin_h_input.textChanged.connect(self.update_live_view_dimensions)
        self.calc_wire_dia_input.textChanged.connect(self.update_live_view_dimensions)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "Calculator")

    def create_test_tab(self):
        tab = QWidget()
        layout = QGridLayout()
        self.test_servo_input = QLineEdit("90")
        self.test_servo_button = QPushButton("Test Servo Angle")
        self.test_stepper_input = QLineEdit("3200")
        self.test_stepper_button = QPushButton("Test Stepper Move")
        
        layout.addWidget(QLabel("Servo Angle:"), 0, 0)
        layout.addWidget(self.test_servo_input, 0, 1)
        layout.addWidget(self.test_servo_button, 0, 2)
        layout.addWidget(QLabel("Stepper Steps:"), 1, 0)
        layout.addWidget(self.test_stepper_input, 1, 1)
        layout.addWidget(self.test_stepper_button, 1, 2)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "Test")

    def create_gui_sweep_tab(self):
        """Creates the tab for configuring GUI-driven sweep parameters."""
        tab = QWidget()
        layout = QGridLayout()
        tab.setToolTip("Configure parameters for when 'Sweep Control' is set to 'GUI'.")

        self.gui_sweep_min_angle_input = QLineEdit("70")
        self.gui_sweep_max_angle_input = QLineEdit("100")
        self.gui_sweep_tpl_input = QLineEdit("45") # Turns Per Layer
        self.gui_sweep_scatter_input = QDoubleSpinBox()
        self.gui_sweep_scatter_input.setRange(0.0, 90.0)
        self.gui_sweep_scatter_input.setSingleStep(0.5)
        self.gui_sweep_scatter_input.setValue(2.0)
        self.gui_sweep_scatter_input.setSuffix(" %")
        self.gui_sweep_scatter_input.setToolTip("Reduces the total sweep width by this percentage to prevent wire buildup at the edges.")

        self.gui_sweep_test_running = False # State for the test button
        self.gui_sweep_info_label = QLabel("Degs/Turn: N/A")
        
        copy_from_servo_btn = QPushButton("Copy from Servo Config")
        copy_from_calc_btn = QPushButton("Copy TPL from Calculator")
        self.test_gui_sweep_btn = QPushButton("Test Current Sweep")
        self.test_gui_sweep_btn.setToolTip("Sends the calculated range (including scatter) to the device for a test sweep.")

        layout.addWidget(QLabel("<b>GUI Sweep Configuration</b>"), 0, 0, 1, 2)
        layout.addWidget(QLabel("Min Angle:"), 1, 0)
        layout.addWidget(self.gui_sweep_min_angle_input, 1, 1)
        layout.addWidget(QLabel("Max Angle:"), 2, 0)
        layout.addWidget(self.gui_sweep_max_angle_input, 2, 1)
        layout.addWidget(QLabel("Turns Per Layer (TPL):"), 3, 0) # Changed row
        layout.addWidget(self.gui_sweep_tpl_input, 3, 1) # Changed row
        layout.addWidget(QLabel("Scatter / Margin:"), 4, 0) # Changed row
        layout.addWidget(self.gui_sweep_scatter_input, 4, 1) # Changed row

        info_group = QGroupBox("Calculated Sweep Info")
        info_layout = QGridLayout()
        info_layout.addWidget(self.gui_sweep_info_label, 0, 0)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group, 5, 0, 1, 2)

        layout.addWidget(self.test_gui_sweep_btn, 6, 0, 1, 2)
        layout.addWidget(copy_from_servo_btn, 7, 0, 1, 2)
        layout.addWidget(copy_from_calc_btn, 8, 0, 1, 2)
        layout.setRowStretch(9, 1) # Add stretch at the bottom

        # --- Connections ---
        copy_from_servo_btn.clicked.connect(lambda: (self.gui_sweep_min_angle_input.setText(self.servo_min_input.text()), self.gui_sweep_max_angle_input.setText(self.servo_max_input.text())))
        copy_from_calc_btn.clicked.connect(lambda: self.gui_sweep_tpl_input.setText(self.calc_turns_per_layer_label.text()))
        self.test_gui_sweep_btn.clicked.connect(self.toggle_gui_sweep_test)

        # Connect signals to update the info label
        self.gui_sweep_min_angle_input.textChanged.connect(self.update_gui_sweep_info)
        self.gui_sweep_max_angle_input.textChanged.connect(self.update_gui_sweep_info)
        self.gui_sweep_tpl_input.textChanged.connect(self.update_gui_sweep_info)
        self.gui_sweep_scatter_input.valueChanged.connect(self.update_gui_sweep_info)
        self.gui_sweep_scatter_input.valueChanged.connect(self.update_scatter_on_the_fly)

        # Initial calculation
        self.update_gui_sweep_info()

        tab.setLayout(layout)
        self.tabs.addTab(tab, "GUI Sweep")

    def create_servo_config_tab(self):
        tab = QWidget()
        layout = QGridLayout()

        self.servo_min_input = QLineEdit("70")
        self.servo_max_input = QLineEdit("100")
        self.set_servo_limits_button = QPushButton("Set Servo Travel Limits")
        self.test_servo_sweep_button = QPushButton("Test Sweep")

        layout.addWidget(QLabel("Min Angle (e.g., 70):"), 0, 0)
        layout.addWidget(self.servo_min_input, 0, 1)
        layout.addWidget(QLabel("Max Angle (e.g., 100):"), 1, 0)
        layout.addWidget(self.servo_max_input, 1, 1)
        layout.addWidget(self.set_servo_limits_button, 2, 0, 1, 2)
        layout.addWidget(self.test_servo_sweep_button, 3, 0, 1, 2)

        # Connect signals
        self.set_servo_limits_button.clicked.connect(self.set_servo_limits)
        self.test_servo_sweep_button.clicked.connect(self.run_servo_config_sweep_test)

        tab.setLayout(layout)
        self.tabs.addTab(tab, "Servo Config")

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        settings_action = file_menu.addAction("Settings")
        settings_action.triggered.connect(self.open_settings_dialog)
        self.restore_defaults_action = file_menu.addAction("Restore Defaults")

        file_menu.addSeparator()

        save_preset_action = file_menu.addAction("Save Winding Preset...")
        save_preset_action.triggered.connect(self.save_preset)
        load_preset_action = file_menu.addAction("Load Winding Preset...")
        load_preset_action.triggered.connect(self.load_preset)

        self.restore_defaults_action.triggered.connect(self.restore_default_settings)
        self.reset_eeprom_action = file_menu.addAction("Reset Device EEPROM")
        self.reset_eeprom_action.triggered.connect(self.reset_device_eeprom)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        help_menu = menu_bar.addMenu("&Help")
        about_action = help_menu.addAction("About")
        about_action.triggered.connect(self.show_about_dialog)

    def save_preset(self):
        """Saves the current winding parameters to a JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Winding Preset", "", "JSON Files (*.json);;All Files (*)")

        if not file_path:
            return

        preset_data = {
            'control': {
                'target_turns': self.turns_input.text(),
                'speed': self.speed_input.value(),
                'direction': self.direction_combo.currentText(),
                'sweep_control': self.sweep_control_combo.currentText(),
            },
            'calculator': {
                'bobbin_length': self.calc_bobbin_l_input.text(),
                'bobbin_width': self.calc_bobbin_w_input.text(),
                'bobbin_height': self.calc_bobbin_h_input.text(),
                'wire_diameter': self.calc_wire_dia_input.text(),
            },
            'gui_sweep': {
                'min_angle': self.gui_sweep_min_angle_input.text(),
                'max_angle': self.gui_sweep_max_angle_input.text(),
                'tpl': self.gui_sweep_tpl_input.text(),
                'scatter': self.gui_sweep_scatter_input.value(),
            }
        }

        try:
            with open(file_path, 'w') as f:
                json.dump(preset_data, f, indent=4)
            logging.info(f"Winding preset saved to {file_path}")
            QMessageBox.information(self, "Preset Saved", f"Successfully saved preset to:\n{file_path}")
        except Exception as e:
            logging.error(f"Failed to save preset: {e}")
            QMessageBox.critical(self, "Error", f"Could not save preset file.\nError: {e}")

    def load_preset(self):
        """Loads winding parameters from a JSON file."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Winding Preset", "", "JSON Files (*.json);;All Files (*)")

        if not file_path:
            return

        try:
            with open(file_path, 'r') as f:
                preset_data = json.load(f)

            # --- Apply loaded values to the UI ---
            self.turns_input.setText(preset_data['control']['target_turns'])
            self.speed_input.setValue(preset_data['control']['speed'])
            self.direction_combo.setCurrentText(preset_data['control']['direction'])
            self.sweep_control_combo.setCurrentText(preset_data['control']['sweep_control'])
            self.calc_bobbin_l_input.setText(preset_data['calculator']['bobbin_length'])
            self.calc_bobbin_w_input.setText(preset_data['calculator']['bobbin_width'])
            self.calc_bobbin_h_input.setText(preset_data['calculator']['bobbin_height'])
            self.calc_wire_dia_input.setText(preset_data['calculator']['wire_diameter'])
            self.gui_sweep_min_angle_input.setText(preset_data['gui_sweep']['min_angle'])
            self.gui_sweep_max_angle_input.setText(preset_data['gui_sweep']['max_angle'])
            self.gui_sweep_tpl_input.setText(preset_data['gui_sweep']['tpl'])
            self.gui_sweep_scatter_input.setValue(preset_data['gui_sweep']['scatter'])

            logging.info(f"Winding preset loaded from {file_path}")
            QMessageBox.information(self, "Preset Loaded", f"Successfully loaded preset from:\n{file_path}")

        except Exception as e:
            logging.error(f"Failed to load preset: {e}")
            QMessageBox.critical(self, "Error", f"Could not load preset file. It may be invalid or corrupted.\nError: {e}")

    def show_about_dialog(self):
        """Shows the application's About box."""
        about_text = f"""<b>Pickup Winder Control GUI</b><br><br>
This application provides a graphical user interface for controlling a CNC pickup winding machine. It allows users to configure winding parameters, monitor the process in real-time, and test hardware components.<br><br>
Version: {__version__}<br>
Author: {__author__}<br>
Date: {__date__}"""
        QMessageBox.about(self, "About Pickup Winder Control", about_text)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            new_max_speed = dialog.max_speed_input.value()
            self.config.set('Winder', 'max_speed', str(new_max_speed))
            self.save_config()
            logging.info(f"Max speed updated to {new_max_speed}. Restart required for some changes to take effect.")
            # Update relevant widgets if needed
            self.speed_input.setRange(0, new_max_speed)
            self.speed_slider.setRange(0, new_max_speed)

    def restore_default_settings(self):
        """Restores all settings to their default values after confirmation."""
        reply = QMessageBox.question(self, 'Restore Default Settings',
                                     "Are you sure you want to restore all settings to their default values?\n"
                                     "This will overwrite your current configuration.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info("User chose to restore default settings.")
            # Re-create the config object with default values
            self.config = configparser.ConfigParser()
            self.config['Winder'] = {'max_speed': '5000'}
            
            self.save_config()
            
            # Update UI elements that depend on config
            max_speed = self.config.getint('Winder', 'max_speed')
            self.speed_input.setRange(0, max_speed)
            self.speed_slider.setRange(0, max_speed)
            QMessageBox.information(self, "Settings Restored", "Default settings have been restored.")

    def reset_device_eeprom(self):
        """Sends a command to the device to reset its EEPROM after confirmation."""
        reply = QMessageBox.question(self, 'Reset Device EEPROM',
                                     "Are you sure you want to reset the device's EEPROM?\n"
                                     "This will erase all saved settings on the winder hardware (like servo limits) "
                                     "and restore them to firmware defaults. The device will likely restart.",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            logging.info("User chose to reset device EEPROM. Sending command.")
            self.send_command_signal.emit("SYS RESET")
            QMessageBox.information(self, "Command Sent", "The command to reset the device EEPROM has been sent.")


    def setup_serial_worker(self):
        self.thread = QThread()
        self.worker = SerialWorker()
        self.worker.moveToThread(self.thread)

        # --- Connect worker signals to GUI slots ---
        logging.debug("Connecting worker signals to GUI slots.")
        self.worker.port_list_updated.connect(self.update_port_list)
        self.worker.serial_data_received.connect(self.handle_serial_data)
        self.worker.connected.connect(lambda: self.update_ui_state(True))
        self.worker.disconnected.connect(lambda: self.update_ui_state(False))

        # --- Connect GUI signals to worker slots ---
        self.connect_button.clicked.connect(self.toggle_connection)
        self.refresh_button.clicked.connect(self.worker.list_ports)
        self.send_command_signal.connect(self.worker.send_command)

        # --- Connect control signals ---
        self.start_button.clicked.connect(self.start_winding)
        self.stop_button.clicked.connect(lambda: self.send_command_signal.emit("WIND STOP"))
        self.pause_button.clicked.connect(lambda: self.send_command_signal.emit("WIND PAUSE"))
        self.resume_button.clicked.connect(lambda: self.send_command_signal.emit("WIND RESUME"))
        self.calc_button.clicked.connect(self.run_calculation)
        self.test_servo_button.clicked.connect(lambda: self.send_command_signal.emit(f"SERVO POS {self.test_servo_input.text()}"))

        # Motor enable/disable buttons
        self.enable_servo_button.clicked.connect(lambda: self.send_command_signal.emit("SERVO ENABLE"))
        self.disable_servo_button.clicked.connect(lambda: self.send_command_signal.emit("SERVO DISABLE"))
        self.enable_stepper_button.clicked.connect(lambda: self.send_command_signal.emit("STEPPER ENABLE"))
        self.disable_stepper_button.clicked.connect(lambda: self.send_command_signal.emit("STEPPER DISABLE"))


        self.test_stepper_button.clicked.connect(lambda: self.send_command_signal.emit(f"STEPPER MOVE {self.test_stepper_input.text()}"))

        self.thread.start()

        # --- Set Initial State and find ports ---
        # This is done after the thread is started and connections are made.
        logging.debug("Setting initial UI state and requesting port list.")
        self.update_ui_state(connected=False)
        self.worker.list_ports()

    def _send_speed_command(self, speed):
        """Sends the current speed to the device."""
        self.info_labels["Speed"].setText(f"{speed} steps/sec")
        if self.worker.running:
            self.send_command_signal.emit(f"WIND SPEED {speed}")

    def update_speed_from_slider(self):
        """Sends speed value from slider when mouse is released."""
        self._send_speed_command(self.speed_slider.value())

    def update_speed_from_spinbox(self):
        """Sends speed value from spinbox when editing is finished."""
        self._send_speed_command(self.speed_input.value())

    def update_speed_display(self, speed):
        """Updates the speed label in the info panel in real-time."""
        self.info_labels["Speed"].setText(f"{speed} steps/sec")

    def update_port_list(self, ports):
        """Updates the COM port dropdown with a list of available ports."""
        current_port = self.port_combo.currentText()
        self.port_combo.clear()
        self.port_combo.addItems(ports)
        logging.info(f"Updated port list: {ports}")

    def toggle_connection(self):
        if self.worker.running:
            logging.info("Disconnect button clicked. Disconnecting...")
            self.worker.disconnect()
        else:
            port = self.port_combo.currentText()
            if port:
                logging.info(f"Connect button clicked. Connecting to {port}...")
                self.worker.connect(port, 115200)
            else:
                logging.warning("Connect button clicked, but no COM port was selected.")

    def update_ui_state(self, connected):
        logging.info(f"Updating UI state. Connected: {connected}")
        
        # --- Control Tab ---
        for widget in [self.start_button, self.stop_button, self.pause_button, self.resume_button, self.turns_input, self.speed_input, self.speed_slider]:
            control_widgets = [self.start_button, self.stop_button, self.pause_button, self.resume_button,
                           self.turns_input, self.speed_input, self.speed_slider, self.direction_combo,
                           self.enable_servo_button, self.disable_servo_button, self.enable_stepper_button, self.disable_stepper_button]
        for widget in control_widgets:
            widget.setEnabled(connected)

        # --- Calculator Tab ---
        for widget in [self.calc_resistance_input, self.calc_bobbin_l_input, self.calc_bobbin_w_input, self.calc_bobbin_h_input, self.calc_wire_dia_input, self.calc_button]:
            widget.setEnabled(connected)

        # --- Test Tab ---
        for widget in [self.test_servo_input, self.test_servo_button, self.test_stepper_input, self.test_stepper_button]:
            widget.setEnabled(connected)

        # --- GUI Sweep Tab ---
        gui_sweep_widgets = [self.gui_sweep_min_angle_input, self.gui_sweep_max_angle_input, self.gui_sweep_tpl_input, self.gui_sweep_scatter_input, self.test_gui_sweep_btn]
        for widget in gui_sweep_widgets: widget.setEnabled(connected)

        # --- Servo Config Tab ---
        for widget in [self.servo_min_input, self.servo_max_input, self.set_servo_limits_button, self.test_servo_sweep_button]:
            widget.setEnabled(connected)

        # Enable/disable all connection controls based on the connection state.
        self.port_combo.setEnabled(not connected)
        self.refresh_button.setEnabled(not connected)

        # Enable/disable menu actions that require a connection
        self.reset_eeprom_action.setEnabled(connected)

        if connected:
            self.connect_button.setText("Disconnect")
            self.send_command_signal.emit("SYS STATUS")  # Get initial status
        else:
            self.connect_button.setText("Connect")

    def handle_serial_data(self, data):
        logging.debug(f"Raw serial data received: {data.strip()}")
        self.log_output.insertPlainText(data)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())
        
        # --- Parse data to update UI ---
        # Example: "  -> Turn: 1 | Servo Pos: 70.03636169"
        match = re.search(r"-> Turn: (\d+) \| Servo Pos: ([\d\.]+)", data)
        if match:
            turn, pos = match.groups()
            self.winder_widget.current_turns = int(turn)
            self.winder_widget.current_servo_pos = float(pos)
            self.info_labels["Turns"].setText(f"{turn} / {self.winder_widget.target_turns}")
            self.winder_widget.update() # Trigger a repaint
            self.calculate_and_send_live_servo_pos(int(turn))

        # Example: "Current Turns: 0"
        match = re.search(r"Current Turns: (\d+)", data)
        if match:
            self.info_labels["Turns"].setText(f"{match.group(1)} / {self.winder_widget.target_turns}")
            return

        # Example: "STATUS: Winding STOPPED" or "STATUS: Winding completed."
        if "STATUS: Winding STOPPED" in data or "STATUS: Winding completed" in data:
            self.winder_widget.winding_active = False
            return

        # Example: "STATUS: Winding PAUSED"
        if "STATUS: Winding PAUSED" in data:
            return

        # Example: "STATUS: Winding RESUMED"
        if "STATUS: Winding RESUMED" in data:
            return
            
        # Example: "Est. DC Resistance: 6503.41 Ohms"
        match = re.search(r"Est. DC Resistance: ([\d\.]+) Ohms", data)
        if match:
            self.info_labels["Est. R"].setText(f"{match.group(1)} Ohms")
            return
            
        # Example: "Required Turns: 8455"
        match = re.search(r"Required Turns:\s*(\d+)", data)
        if match:
            turns = match.group(1)
            logging.info(f"Received required turns from calculator: {turns}. Updating control tab.")
            self.turns_input.setText(turns)
            return

    def start_winding(self):
        turns = self.turns_input.text()
        direction_cmd="FWD"
        if not (turns.isdigit() and int(turns) > 0):
            logging.warning("Start winding called with invalid turns.")
            return
        
        self.winder_widget.reset_view()

        # If using GUI Pattern mode, send the compiled pattern data first.
        if self.sweep_control_combo.currentText() == "GUI (Pattern)":
            try:
                min_a = self.gui_sweep_min_angle_input.text()
                max_a = self.gui_sweep_max_angle_input.text()
                tpl = self.gui_sweep_tpl_input.text()
                scatter = self.gui_sweep_scatter_input.value()
                pattern_cmd = f"WIND PATTERN {min_a} {max_a} {tpl} {scatter}"
                self.send_command_signal.emit(pattern_cmd)
            except (ValueError, ZeroDivisionError) as e:
                QMessageBox.warning(self, "Invalid GUI Sweep Data", f"Could not start with GUI (Pattern) mode. Please check the values in the GUI Sweep tab.\nError: {e}")
                return

        
        # --- Send latest parameters to ensure sync ---
        # This ensures the device has the correct bobbin and wire info for the servo sweep.
        bobbin_cmd = f"BOBBIN {self.calc_bobbin_l_input.text()} {self.calc_bobbin_w_input.text()} {self.calc_bobbin_h_input.text()}"
        self.send_command_signal.emit(bobbin_cmd)
        self.send_command_signal.emit(f"WIRE_DIA {self.calc_wire_dia_input.text()}")
        
        # --- Set winding parameters and start ---
        speed = self.speed_input.value()
        self.winder_widget.target_turns = int(turns)
        self.winder_widget.winding_active = True
        self.send_command_signal.emit(f"WIND SPEED {speed}")
        self.send_command_signal.emit(f"WIND COUNT {turns}")
        self.send_command_signal.emit(f"WIND DIR {self.direction_combo.currentText().upper()}")
        self.send_command_signal.emit("WIND START -V") # Start with verbose mode to get live updates

    def run_calculation(self):
        resistance_text = self.calc_resistance_input.text().strip().lower()
        resistance_val = 0
        try:
            if not resistance_text.endswith('k') and not resistance_text.endswith('r'):
                resistance_val = float(resistance_text)
                # Add 'r' suffix for clarity if it was just a number
                #self.calc_resistance_input.setText(f"{resistance_text}r")
                resistance_text += "r"
            else:
                resistance_val = float(resistance_text[:-1])
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", f"Invalid resistance value: '{self.calc_resistance_input.text()}'.\nPlease use formats like '6.5k', '5000', or '5000r'.")
            return

        self.send_command_signal.emit(f"WIRE_DIA {self.calc_wire_dia_input.text()}")
        bobbin_cmd = f"BOBBIN {self.calc_bobbin_l_input.text()} {self.calc_bobbin_w_input.text()} {self.calc_bobbin_h_input.text()}"
        self.send_command_signal.emit(bobbin_cmd)
        self.send_command_signal.emit(f"CALC {resistance_text}")
        # After calculation, the firmware will report the new turn count. We can grab it from the log.
        # A more robust solution would parse "Required Turns" and update the control tab input.

    def set_servo_limits(self):
        min_angle_str = self.servo_min_input.text()
        max_angle_str = self.servo_max_input.text()
        try:
            min_angle = float(min_angle_str)
            max_angle = float(max_angle_str)
            # Update winder widget for visualization
            self.winder_widget.servo_min_angle = min_angle
            self.winder_widget.servo_max_angle = max_angle
            # Send command to firmware
            self.send_command_signal.emit(f"SERVO CALIBRATE {min_angle} {max_angle}")
        except ValueError:
            logging.warning(f"Invalid servo limits entered: '{min_angle_str}', '{max_angle_str}'")

    def calculate_and_send_live_servo_pos(self, current_turn):
        """Calculates and sends the servo position for the next turn if in GUI (Live) mode."""
        if not (self.winder_widget.winding_active and self.sweep_control_combo.currentText() == "GUI (Live)"):
            return

        try:
            tpl = int(self.gui_sweep_tpl_input.text())
            min_angle = float(self.gui_sweep_min_angle_input.text())
            max_angle = float(self.gui_sweep_max_angle_input.text())
            scatter_percent = self.gui_sweep_scatter_input.value()

            if tpl <= 1: return

            # This logic mirrors the firmware's updateServoPosition function
            angle_range = max_angle - min_angle
            scatter_amount = angle_range * (scatter_percent / 100.0)
            effective_min = min_angle + (scatter_amount / 2.0)
            effective_max = max_angle - (scatter_amount / 2.0)
            effective_range = effective_max - effective_min
            pitch_angle = effective_range / (tpl - 1)

            # We calculate for the *next* turn, which is current_turn + 1
            next_turn = current_turn
            layer = next_turn // tpl
            turn_in_layer = next_turn % tpl

            if layer % 2 == 0: # Even layers (0, 2, 4...): move from min to max
                servo_pos = effective_min + (turn_in_layer * pitch_angle)
            else: # Odd layers (1, 3, 5...): move from max to min
                servo_pos = effective_max - (turn_in_layer * pitch_angle)

            # Ensure position is within the effective bounds
            servo_pos = max(effective_min, min(servo_pos, effective_max))

            self.send_command_signal.emit(f"SERVO POS {servo_pos:.4f}")

        except (ValueError, ZeroDivisionError) as e:
            logging.error(f"Error calculating live servo position: {e}")

    def set_servo_limits(self):
        min_angle_str = self.servo_min_input.text()
        max_angle_str = self.servo_max_input.text()
        try:
            min_angle = float(min_angle_str)
            max_angle = float(max_angle_str)
            # Update winder widget for visualization
            self.winder_widget.servo_min_angle = min_angle
            self.winder_widget.servo_max_angle = max_angle
            # Send command to firmware
            self.send_command_signal.emit(f"SERVO CALIBRATE {min_angle} {max_angle}")
        except ValueError:
            logging.warning(f"Invalid servo limits entered: '{min_angle_str}', '{max_angle_str}'")

    def run_servo_config_sweep_test(self):
        """Sends a sequence of SERVO_POS commands based on the Servo Config tab values."""
        try:
            min_angle = float(self.servo_min_input.text())
            max_angle = float(self.servo_max_input.text())

            logging.info(f"Running Servo Config sweep test from {min_angle:.2f}° to {max_angle:.2f}°")

            # Define the sequence of movements using SERVO_POS
            cmd1 = f"SERVO POS {min_angle:.2f}"
            cmd2 = f"SERVO POS {max_angle:.2f}"

            # Send commands with a delay between them to allow the servo to move
            self.send_command_signal.emit(cmd1)
            QTimer.singleShot(750, lambda: self.send_command_signal.emit(cmd2))
            QTimer.singleShot(1500, lambda: self.send_command_signal.emit(cmd1))
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please ensure Min/Max angles in the Servo Config tab are valid numbers before testing.")

    def update_turns_per_layer_calc(self):
        """Calculates and displays the theoretical vertical turns per layer."""
        try:
            bobbin_height = float(self.calc_bobbin_h_input.text())
            wire_diameter = float(self.calc_wire_dia_input.text())

            if wire_diameter > 0:
                turns_per_layer = int(bobbin_height / wire_diameter)
                self.calc_turns_per_layer_label.setText(str(turns_per_layer))
                self.winder_widget.turns_per_layer = turns_per_layer
            else:
                self.calc_turns_per_layer_label.setText("N/A")
                self.winder_widget.turns_per_layer = 0
        except ValueError:
            # If input is not a valid number, just show N/A
            self.calc_turns_per_layer_label.setText("N/A")
            self.winder_widget.turns_per_layer = 0

    def update_sweep_control_source(self, source_text):
        """Sends the selected sweep control source to the firmware."""
        # Map GUI text to firmware command
        if source_text == "Firmware":
            mode = "FIRMWARE"
        elif source_text == "GUI (Live)":
            mode = "GUI"
        elif source_text == "GUI (Pattern)":
            mode = "PATTERN"
        else:
            return # Should not happen
        cmd = f"WIND SWEEP {mode}"
        self.send_command_signal.emit(cmd)

    def toggle_gui_sweep_test(self):
        """Starts or stops the GUI sweep test sequence."""
        if self.gui_sweep_test_running:
            self.cancel_gui_sweep_test()
        else:
            self.run_gui_sweep_test()

    def run_gui_sweep_test(self):
        """Starts a test that simulates one full layer of the GUI sweep."""
        try:
            tpl = int(self.gui_sweep_tpl_input.text())
            min_angle = float(self.gui_sweep_min_angle_input.text())
            max_angle = float(self.gui_sweep_max_angle_input.text())
            scatter_percent = self.gui_sweep_scatter_input.value()

            if tpl <= 1:
                QMessageBox.information(self, "Test Skipped", "Turns Per Layer must be greater than 1 to run a sweep test.")
                return

            self.gui_sweep_test_running = True
            self.test_gui_sweep_btn.setText("Cancel Test")
            logging.info(f"Starting GUI sweep test for {tpl} steps.")

            # Calculate the effective range after applying scatter/margin
            angle_range = max_angle - min_angle
            scatter_amount = angle_range * (scatter_percent / 100.0)
            effective_min = min_angle + (scatter_amount / 2.0)
            effective_max = max_angle - (scatter_amount / 2.0)

            # Start the recursive step function
            self._execute_sweep_test_step(0, tpl, effective_min, effective_max)
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please ensure Min/Max angles are valid numbers before testing.")
            self.cancel_gui_sweep_test()

    def _execute_sweep_test_step(self, current_step, total_steps, min_pos, max_pos):
        """Executes a single step of the sweep test and schedules the next one."""
        # Check for cancellation or completion
        if not self.gui_sweep_test_running or current_step >= total_steps:
            self.cancel_gui_sweep_test()
            return

        # Calculate position for the current step (simulating one layer)
        progress = current_step / (total_steps - 1)
        pos = min_pos + (max_pos - min_pos) * progress
        
        # Send the command
        self.send_command_signal.emit(f"SERVO POS {pos:.2f}")

        # Schedule the next step
        delay_ms = 100 # Delay between steps
        QTimer.singleShot(delay_ms, lambda: self._execute_sweep_test_step(current_step + 1, total_steps, min_pos, max_pos))

    def cancel_gui_sweep_test(self):
        """Stops the GUI sweep test and resets the button."""
        if self.gui_sweep_test_running:
            logging.info("GUI sweep test cancelled by user or finished.")
        self.gui_sweep_test_running = False
        self.test_gui_sweep_btn.setText("Test Current Sweep")

    def update_scatter_on_the_fly(self, value):
        """Sends a scatter update command to the device if winding is active."""
        # Only send updates if winding is active and the control source is a GUI pattern
        if self.winder_widget.winding_active and self.sweep_control_combo.currentText() == "GUI (Pattern)":
            logging.info(f"Sending live scatter update: {value}")
            cmd = f"WIND SCATTER {value}"
            self.send_command_signal.emit(cmd)


    def update_gui_sweep_info(self):
        """Calculates and displays the degrees per turn for the GUI sweep."""
        try:
            # Get all relevant values from the UI
            min_angle = float(self.gui_sweep_min_angle_input.text())
            max_angle = float(self.gui_sweep_max_angle_input.text())
            tpl = int(self.gui_sweep_tpl_input.text())
            scatter_percent = self.gui_sweep_scatter_input.value()

            # Calculate the effective range after applying scatter/margin
            angle_range = max_angle - min_angle
            scatter_amount = angle_range * (scatter_percent / 100.0)
            effective_min = min_angle + (scatter_amount / 2.0)
            effective_max = max_angle - (scatter_amount / 2.0)
            effective_range = effective_max - effective_min

            # Calculate the step per turn
            degs_per_turn = effective_range / (tpl - 1) if tpl > 1 else 0

            # Format the detailed info string using HTML for layout
            info_text = (f"<b>Range:</b> {effective_min:.2f}° ↔ {effective_max:.2f}°<br>"
                         f"<b>Total Travel:</b> {effective_range:.2f}°<br>"
                         f"<b>Step:</b> ~{degs_per_turn:.4f}°/turn over {tpl} turns")
            self.gui_sweep_info_label.setText(info_text)
        except (ValueError, ZeroDivisionError):
            self.gui_sweep_info_label.setText("Invalid Input")


    def closeEvent(self, event):
        """Ensure the worker thread is cleaned up on exit."""
        logging.info("Close event triggered. Shutting down serial worker and thread.")
        self.worker.disconnect()
        self.thread.quit()
        self.thread.wait()
        super().closeEvent(event)

    def update_live_view_dimensions(self):
        """
        Parses bobbin and wire dimensions from the calculator tab
        and updates the WinderWidget for live visualization.
        """
        try:
            bobbin_l = float(self.calc_bobbin_l_input.text())
            bobbin_h = float(self.calc_bobbin_h_input.text())
            wire_dia = float(self.calc_wire_dia_input.text())

            self.winder_widget.bobbin_length = bobbin_l
            self.winder_widget.bobbin_height = bobbin_h
            self.winder_widget.wire_diameter = wire_dia

            # Update info panel
            self.info_labels["Wire Dia"].setText(f"{wire_dia:.3f} mm")
            self.info_labels["Bobbin"].setText(f"{bobbin_l:.1f}/{self.calc_bobbin_w_input.text()}/{bobbin_h:.1f} mm")

            self.winder_widget.update() # Trigger a repaint
        except ValueError:
            # Ignore errors from partially entered text
            pass