import logging

def setup_logger(name):
    logger = logging.getLogger(name)
    
    # Only set handlers if they haven't been set up already
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # File handler
        file_handler = logging.FileHandler('app.log')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.setLevel(logging.INFO)
    
    return logger