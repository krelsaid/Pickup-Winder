# Name:     pickup winder control GUI
# Author:   khairil said
# Date:     12/2/2025
# Version:  1.0

import sys
import logging
from PyQt6.QtWidgets import QApplication
from gui import MainWindow
from logging_config import setup_logging

if __name__ == '__main__':
    # Setup logging as the very first thing
    setup_logging()
    logging.info("Application starting up...")

    # Create the application instance
    app = QApplication(sys.argv)
    
    # Set a modern style for the UI
    app.setStyle("Fusion")
    
    # Create and show the main window
    window = MainWindow()
    window.show()
    
    # Start the event loop
    exit_code = app.exec()
    logging.info(f"Application exiting with code {exit_code}.")
    sys.exit(exit_code)