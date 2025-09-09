import logging
import os

# Create logs folder if not exists
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logger
logger = logging.getLogger("projects_logger")
logger.setLevel(logging.INFO)

# File handler
file_handler = logging.FileHandler(os.path.join(LOG_DIR, "projects.log"))
file_handler.setLevel(logging.INFO)

# Console handler (optional, for debugging)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Formatter
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers (avoid duplicate handlers)
if not logger.handlers:
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
