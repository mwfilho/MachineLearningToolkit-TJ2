import logging
from datetime import date
import os

class Logs:
    def __init__(self, filename=None):
        if filename is None:
            filename = f'logs/log-{date.today().strftime("%Y-%m-%d")}.log'
            
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
            
        # Configure logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(filename),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def record(self, message, type='info', colorize=False):
        """
        Record a log message with the specified type.
        
        Args:
            message (str): The message to log
            type (str): The type of log ('info', 'error', 'warning', 'debug')
            colorize (bool): Whether to add color to console output
        """
        if type == 'error':
            self.logger.error(message)
        elif type == 'warning':
            self.logger.warning(message)
        elif type == 'debug':
            self.logger.debug(message)
        else:
            self.logger.info(message)
