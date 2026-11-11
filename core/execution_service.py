import threading
from typing import Dict, Any, Callable, Optional

from core.launcher import launch_game_thread
from core.feedback import feedback_launch
from core.logger import get_logger

logger = get_logger("ExecutionService")


class GameExecutionService:
    """
    Servicio desacoplado encargado de orquestar el lanzamiento de videojuegos:
    - Verificación de exclusión (evitar lanzamientos duplicados simultáneos).
    - Feedback háptico y acústico cálido.
    - Lanzamiento en hilo desacoplado con prioridades de proceso.
    - Enrutamiento de callbacks de estado, éxito y error.
    """

    def __init__(self):
        self._is_launching: bool = False

    @property
    def is_launching(self) -> bool:
        return self._is_launching

    def launch(
        self,
        game: Dict[str, Any],
        status_cb: Optional[Callable[[str], None]] = None,
        on_success_cb: Optional[Callable[[], None]] = None,
        on_error_cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """Lanza el juego en un hilo en segundo plano con control de concurrencia."""
        if self._is_launching:
            logger.warning(f"Lanzamiento cancelado: ya hay un juego iniciando ('{game.get('name')}')")
            return False

        self._is_launching = True
        try:
            feedback_launch()
        except Exception:
            pass

        def _wrapped_success():
            self._is_launching = False
            if on_success_cb:
                on_success_cb()

        def _wrapped_error(err_msg: str):
            self._is_launching = False
            if on_error_cb:
                on_error_cb(err_msg)

        path = game.get("path", "")
        monitor = int(game.get("monitor", 0) or 0)
        high_priority = bool(game.get("high_priority", True))
        custom_args = game.get("launch_args", "")
        emulator_path = game.get("emulator_path", "")
        is_rom = bool(game.get("is_rom", False))
        system_id = game.get("system_id", "")

        logger.info(f"Iniciando ejecución de '{game.get('name')}' (Monitor {monitor}, Prioridad={high_priority}, ROM={is_rom})")

        threading.Thread(
            target=launch_game_thread,
            args=(path, monitor, high_priority),
            kwargs={
                "status_cb": status_cb,
                "on_success_cb": _wrapped_success,
                "on_error_cb": _wrapped_error,
                "custom_args": custom_args,
                "emulator_path": emulator_path,
                "is_rom": is_rom,
                "system_id": system_id
            },
            daemon=True
        ).start()
        return True

    def reset(self) -> None:
        """Restablece el indicador de lanzamiento en caso de cancelación o recuperación."""
        self._is_launching = False
