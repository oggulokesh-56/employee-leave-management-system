import logging
import os

def setup_logging():

    log_format = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler("app.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger("leave_management")
    logger.info("Logging initialized successfully.")
    return logger