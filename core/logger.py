"""
Central Logging System for GameFlow Launcher.
Provides bounded rotating file logging (max 512 KB, 2 backups) and console fallback.
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from typing import Optional

try:
    from core.config import STORAGE_DIR
except Exception:
    if getattr(sys, 'frozen', False):
        STORAGE_DIR = os.path.dirname(sys.executable)
    else:
        STORAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_FILE = os.path.join(STORAGE_DIR, "gameflow.log")
_INITIALIZED = False

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Configura el sistema de logging raíz de GameFlow con rotación automática."""
    global _INITIALIZED
    root_logger = logging.getLogger("GameFlow")
    
    if _INITIALIZED:
        return root_logger
    _INITIALIZED = True

    root_logger.setLevel(level)
    root_logger.propagate = False

    # Evitar acumular handlers duplicados
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    # 1. Rotating File Handler (512 KB por archivo, 2 rotaciones = máx 1.5 MB en disco)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=512 * 1024,
            backupCount=2,
            encoding="utf-8",
            delay=True
        )
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        try:
            sys.stderr.write(f"[GameFlow] Error al iniciar rotating log: {e}\n")
        except Exception:
            pass

    # 2. Console Handler (solo si hay terminal activa y válida)
    if sys.stdout and hasattr(sys.stdout, "write") and not getattr(sys, 'frozen', False):
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_formatter = logging.Formatter("[%(levelname)s] [%(name)s] %(message)s")
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(level)
            root_logger.addHandler(console_handler)
        except Exception:
            pass

    return root_logger

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Obtiene un logger hijo namespaced bajo 'GameFlow'.
    Ejemplo: get_logger('Launcher') -> 'GameFlow.Launcher'
    """
    if not _INITIALIZED:
        setup_logging()
    if name:
        return logging.getLogger(f"GameFlow.{name}")
    return logging.getLogger("GameFlow")
