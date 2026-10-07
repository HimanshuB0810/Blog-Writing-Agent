import logging
import os
from datetime import datetime

LOGS_DIR="logs"
os.makedirs(LOGS_DIR,exist_ok=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE=os.path.join(LOGS_DIR,f"logs_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.logs")

logging.basicConfig(
    filename=LOG_FILE,
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
)

def get_logger(name):
    logger=logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger