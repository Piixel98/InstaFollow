import time
import random
import logging
import sys

def setup_logging():
    # Create logger
    logger = logging.getLogger('InstaFollow')
    logger.setLevel(logging.DEBUG)

    # Create a file handler
    file_handler = logging.FileHandler('log.txt', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # Create a console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)

    # Create a formatter and add it to handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger

def human_sleep(a=0.7, b=1.8):
    time.sleep(random.uniform(a, b))

def long_pause():
    time.sleep(random.uniform(3, 6))
