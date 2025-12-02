import serial
import serial.tools.list_ports
import time
from PyQt6.QtCore import QObject, pyqtSignal, QThread
import logging, threading

class SerialWorker(QObject):
    """
    Manages serial communication in a separate thread.
    """
    # Signals to send data back to the main GUI thread
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    serial_data_received = pyqtSignal(str)
    port_list_updated = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.serial_port = None
        self.running = False

    def list_ports(self):
        """Emits a list of available COM ports."""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        logging.info(f"Found available ports: {ports}")
        self.port_list_updated.emit(ports)

    def connect(self, port, baudrate):
        """Connects to the specified serial port."""
        try:
            logging.info(f"Attempting to connect to {port} at {baudrate} baud.")
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            self.running = True
            self.connected.emit()
            
            # Start the reading loop in its own thread
            read_thread = threading.Thread(target=self.read_loop, daemon=True)
            read_thread.start()

        except serial.SerialException as e:
            logging.error(f"Failed to connect to {port}: {e}")
            self.serial_data_received.emit(f"ERROR: Could not open port {port}: {e}\n")
            self.disconnected.emit()

    def read_loop(self):
        """Continuously reads from the serial port."""
        logging.debug("Serial read_loop started.")
        while self.running and self.serial_port and self.serial_port.is_open:
            try:
                line = self.serial_port.readline().decode('utf-8').strip()
                if line:
                    self.serial_data_received.emit(line + '\n')
            except (serial.SerialException, TypeError):
                # Port was closed
                logging.warning("Serial port disconnected unexpectedly during read.")
                self.disconnect()
                break
        logging.debug("Serial read_loop finished.")

    def send_command(self, command):
        """Sends a command to the serial port."""
        if self.serial_port and self.serial_port.is_open:
            logging.debug(f"Sending command: '{command}'")
            self.serial_port.write((command + '\n').encode('utf-8'))

    def disconnect(self):
        """Disconnects from the serial port."""
        self.running = False
        if self.serial_port and self.serial_port.is_open:
            logging.info(f"Closing serial port {self.serial_port.name}.")
            self.serial_port.close()
        self.disconnected.emit()