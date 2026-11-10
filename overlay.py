"""
Punto de Entrada Autónomo para el In-Game Overlay de GameFlow Launcher.

Permite invocar el menú flotante en juego tanto desde el centinela o watcher en segundo plano
como de forma directa o mediante atajo de mando.
"""

import os
import sys
import customtkinter as ctk

# Asegurar raíz del proyecto en sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.theme import setup_customtkinter_theme
from ui.dialogs.in_game_overlay import InGameOverlayDialog
from core.platform_layer import safe_set_dpi_awareness, safe_set_app_user_model_id


def launch_main_launcher():
    """Arranca o restaura el lanzador principal GameFlow."""
    try:
        from gamepad_watcher import launch_or_focus
        launch_or_focus()
    except Exception:
        pythonw = sys.executable
        launcher_script = os.path.join(BASE_DIR, "lanzador.py")
        if os.path.isfile(launcher_script):
            import subprocess
            subprocess.Popen([pythonw, launcher_script], cwd=BASE_DIR)


def main():
    safe_set_dpi_awareness()
    safe_set_app_user_model_id("gameflow.overlay.v1")

    # Ventana raíz oculta mínima para albergar el diálogo Toplevel de CustomTkinter
    root = ctk.CTk()
    root.withdraw()
    setup_customtkinter_theme()

    def _on_resume():
        root.quit()

    def _on_return():
        launch_main_launcher()
        root.quit()

    def _on_exit():
        launch_main_launcher()
        root.quit()

    overlay = InGameOverlayDialog(
        parent=root,
        on_resume_callback=_on_resume,
        on_return_to_launcher_callback=_on_return,
        on_exit_game_callback=_on_exit
    )
    overlay.protocol("WM_DELETE_WINDOW", _on_resume)

    root.mainloop()


if __name__ == "__main__":
    main()
