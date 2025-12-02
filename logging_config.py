import logging
import sys

def setup_logging():
    """Configures the root logger for the application."""
    logging.basicConfig(
        level=logging.DEBUG,  # Capture all levels of logs from DEBUG upwards
        format="%(asctime)s [%(levelname)s] %(threadName)s - %(message)s (%(filename)s:%(lineno)d)",
        handlers=[
            # Log to a file, overwriting it each time the app starts
            logging.FileHandler("app.log", mode='w'),
            # Also log to the console (standard output)
            logging.StreamHandler(sys.stdout)
        ]
    )