import time
from typing import Dict, Any, Optional, Callable

from gamepad_manager import poll_active_gamepad, get_connected_controller_family
from core.logger import get_logger

logger = get_logger("GamepadNavigation")


class GamepadNavigationService:
    """
    Servicio desacoplado responsable del bucle a 40 Hz de sondeo de mandos,
    auto-repetición de cruceta/stick y enrutamiento jerárquico hacia modales o vista principal.
    """

    def __init__(self, app, on_action: Optional[Callable[[str, Any], None]] = None):
        self.app = app
        self.on_action = on_action
        self._prev_buttons: Dict[str, Any] = {}
        self._was_connected: bool = False
        self._last_move_ts: float = 0.0
        self._hold_start_ts: float = 0.0
        self._last_repeat_ts: float = 0.0
        self._last_fam_sync_ts: float = 0.0

    @property
    def was_connected(self) -> bool:
        return self._was_connected

    def tick(self, target_id: str = "any", enable_nav: bool = True) -> None:
        """Ciclo de sondeo a 40 Hz con auto-repetición y enrutamiento a modales prioritarios."""
        try:
            is_conn, dev_name, inputs = poll_active_gamepad(target_id)
            now = time.time()

            # 1. Detección de conexión y sincronización de familia
            if is_conn and not self._was_connected:
                self._was_connected = True
                self.app._sync_controller_family_ui()
                self.app.on_gamepad_connected(dev_name)
            elif not is_conn:
                self._was_connected = False

            if now - self._last_fam_sync_ts > 1.5:
                self._last_fam_sync_ts = now
                self.app._sync_controller_family_ui()

            if not is_conn or not enable_nav:
                self._prev_buttons = {}
                return

            prev = dict(self._prev_buttons)

            # Auto-repetición al mantener pulsada cruceta, stick o bumpers
            held_dirs = ("up", "down", "left", "right", "lb", "rb")
            any_held = any(inputs.get(k, False) for k in held_dirs)
            if not any_held:
                self._hold_start_ts = 0.0
                self._last_repeat_ts = 0.0
            else:
                if not any(prev.get(k, False) for k in held_dirs):
                    self._hold_start_ts = now
                    self._last_repeat_ts = now
                elif (now - self._hold_start_ts > 0.28) and (now - self._last_repeat_ts > 0.14):
                    for k in held_dirs:
                        if inputs.get(k, False):
                            prev[k] = False
                    self._last_repeat_ts = now

            # Actualizar _prev_buttons ANTES de despachar eventos por si algún manejador abre un wait_window() anidado
            self._prev_buttons = dict(inputs)

            # 2. Prioridad absoluta: Enrutamiento al modal o menú desplegable en la cima de la pila
            top_modal = self.app._get_topmost_active_modal()
            if top_modal is not None:
                handled = False
                if hasattr(top_modal, "handle_gamepad_input") and callable(top_modal.handle_gamepad_input):
                    try:
                        handled = bool(top_modal.handle_gamepad_input(inputs, prev))
                    except Exception as ex:
                        logger.error(f"Error procesando gamepad en modal: {ex}", exc_info=True)
                
                # Red de seguridad universal: Si el modal no consumió B o Back, cancelarlo/cerrarlo
                if not handled and ((inputs.get("b", False) and not prev.get("b", False)) or 
                                    (inputs.get("back", False) and not prev.get("back", False))):
                    try:
                        if hasattr(top_modal, "on_cancel") and callable(top_modal.on_cancel):
                            top_modal.on_cancel()
                        elif hasattr(top_modal, "close") and callable(top_modal.close):
                            top_modal.close()
                        elif hasattr(top_modal, "destroy") and callable(top_modal.destroy):
                            top_modal.destroy()
                    except Exception:
                        pass
                return

            # Si el lanzador está minimizado: responder a Select, Start o Guía para restaurar
            if getattr(self.app, "is_minimized", False):
                if (
                    (inputs.get("back", False) and not prev.get("back", False))
                    or (inputs.get("start", False) and not prev.get("start", False))
                    or (inputs.get("guide", False) and not prev.get("guide", False))
                ):
                    self.app.restore_window()
                self._prev_buttons = inputs
                return

            # Botón Guía / Xbox / Nexus: Traer al frente
            if inputs.get("guide", False) and not prev.get("guide", False):
                self.app.restore_window()
                try:
                    self.app.lift()
                    self.app.focus_force()
                except Exception:
                    pass

            # Navegación horizontal en el carrusel Cover Flow
            move_left = inputs.get("left", False)
            move_right = inputs.get("right", False)
            if move_left and not move_right:
                if not prev.get("left", False) or (now - self._last_move_ts > 0.20):
                    self.app.cover_stage.prev_cover()
                    self._last_move_ts = now
            elif move_right and not move_left:
                if not prev.get("right", False) or (now - self._last_move_ts > 0.20):
                    self.app.cover_stage.next_cover()
                    self._last_move_ts = now

            # Cruceta Arriba: En Big Picture abre selector de monitores; en Mini transparente no hace nada
            if inputs.get("up", False) and not prev.get("up", False):
                if not getattr(self.app, "is_mini_mode", False):
                    if hasattr(self.app, "monitor_dropdown"):
                        self.app.monitor_dropdown._toggle_dropdown()
                    else:
                        self.app.toggle_top_menu()

            # Botón A / Cruz: Iniciar juego
            if inputs.get("a", False) and not prev.get("a", False):
                if not getattr(self.app, "_is_launching", False):
                    self.app.launch_current_game()

            # Botón Select / Back: Minimizar y restaurar
            if inputs.get("back", False) and not prev.get("back", False):
                self.app.toggle_minimize()

            # Botón Start: Alternar entre modo transparente y pantalla completa
            if inputs.get("start", False) and not prev.get("start", False):
                self.app.toggle_size_mode()

            # Botón B / Círculo: Volver a modo pequeño si está en pantalla completa
            if inputs.get("b", False) and not prev.get("b", False):
                if not getattr(self.app, "is_mini_mode", False):
                    self.app.set_mini_mode()

            # Botón Y / Triángulo: Confirmar salida
            if inputs.get("y", False) and not prev.get("y", False):
                self.app.open_exit_dialog()

            # Botón X / Cuadrado: Menú de opciones (Solo disponible en Modo Big Picture)
            if inputs.get("x", False) and not prev.get("x", False):
                if not getattr(self.app, "is_mini_mode", False):
                    self.app.toggle_top_menu()

            # LB / RB: Salto de 5 carátulas
            if inputs.get("lb", False) and not prev.get("lb", False):
                n = len(self.app.games)
                if n > 0:
                    cur = int(round(self.app.cover_stage.target_pos))
                    self.app.cover_stage.select_index(max(0, cur - 5))
            if inputs.get("rb", False) and not prev.get("rb", False):
                n = len(self.app.games)
                if n > 0:
                    cur = int(round(self.app.cover_stage.target_pos))
                    self.app.cover_stage.select_index(min(n - 1, cur + 5))

            # LT / RT: Salto alfabético
            if inputs.get("lt", False) and not prev.get("lt", False):
                self.app._on_quick_letter_jump(direction=-1)
            if inputs.get("rt", False) and not prev.get("rt", False):
                self.app._on_quick_letter_jump(direction=1)

            self._prev_buttons = inputs
        except Exception:
            pass
