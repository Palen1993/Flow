import sys
import os
import unittest
import tempfile
import logging
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.logger import get_logger, setup_logging, LOG_FILE

class TestLoggerRotation(unittest.TestCase):
    def test_01_logger_instance_and_namespace(self):
        """Verifica que get_logger retorna loggers jerárquicos bajo 'GameFlow'."""
        log_app = get_logger("App")
        log_sys = get_logger("System")
        log_root = get_logger()

        self.assertEqual(log_app.name, "GameFlow.App")
        self.assertEqual(log_sys.name, "GameFlow.System")
        self.assertEqual(log_root.name, "GameFlow")

    def test_02_log_emission_to_disk(self):
        """Verifica que un mensaje de log se escribe efectivamente en gameflow.log."""
        logger = get_logger("TestUnit")
        test_msg = f"Testing rotating log record emission pid={os.getpid()}"
        logger.info(test_msg)

        # Forzar flush
        for handler in logging.getLogger("GameFlow").handlers:
            handler.flush()

        self.assertTrue(os.path.isfile(LOG_FILE), f"LOG_FILE no existe: {LOG_FILE}")
        with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        self.assertIn(test_msg, content)
        self.assertIn("[INFO]", content)
        self.assertIn("[GameFlow.TestUnit]", content)

    def test_03_rotation_bounds(self):
        """Verifica que el RotatingFileHandler está configurado con maxBytes=512KB y backupCount=2."""
        root_logger = logging.getLogger("GameFlow")
        from logging.handlers import RotatingFileHandler
        rotating_handlers = [h for h in root_logger.handlers if isinstance(h, RotatingFileHandler)]
        self.assertGreaterEqual(len(rotating_handlers), 1)
        h = rotating_handlers[0]
        self.assertEqual(h.maxBytes, 512 * 1024)
        self.assertEqual(h.backupCount, 2)

if __name__ == "__main__":
    unittest.main()
