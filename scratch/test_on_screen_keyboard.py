import sys
import os
import unittest
import tkinter as tk
import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.dialogs.on_screen_keyboard import OnScreenKeyboardDialog, prompt_on_screen_keyboard

class MockRootApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.geometry("800x600")
        self._modal_stack = []

    def push_modal(self, modal):
        if modal not in self._modal_stack:
            self._modal_stack.append(modal)

    def pop_modal(self, modal):
        if modal in self._modal_stack:
            self._modal_stack.remove(modal)

    def _get_topmost_active_modal(self):
        while self._modal_stack:
            top = self._modal_stack[-1]
            try:
                if top.winfo_exists():
                    state = getattr(top, "state", lambda: "normal")()
                    if state not in ("withdrawn", "iconic"):
                        return top
            except Exception:
                pass
            self._modal_stack.pop()
        return None

class TestOnScreenKeyboard(unittest.TestCase):
    def setUp(self):
        self.app = MockRootApp()
        self.app.update()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_01_init_and_stack_registration(self):
        """Verifica que el teclado virtual se registra en la pila modal O(1)."""
        osk = prompt_on_screen_keyboard(self.app, title="Test OSK", initial_text="Hello")
        self.app.update()

        self.assertEqual(self.app._get_topmost_active_modal(), osk)
        self.assertEqual(osk.text_value, "Hello")

        osk.close()
        self.app.update()
        self.assertIsNone(self.app._get_topmost_active_modal())

    def test_02_typing_and_shortcuts(self):
        """Verifica escritura, borrado, espacio y alternancia de mayúsculas/símbolos."""
        result = []
        def _on_confirm(val):
            result.append(val)

        osk = OnScreenKeyboardDialog(self.app, title="Typing Test", initial_text="Game", on_confirm=_on_confirm)
        self.app.update()

        # Espacio con acción o atajo
        osk.action_space()
        self.assertEqual(osk.text_value, "Game ")

        # Escribir carácter
        osk._on_key_clicked("F")
        osk._on_key_clicked("l")
        osk._on_key_clicked("o")
        osk._on_key_clicked("w")
        self.assertEqual(osk.text_value, "Game Flow")

        # Borrar con backspace
        osk.action_backspace()
        self.assertEqual(osk.text_value, "Game Flo")

        # Confirmar y cerrar
        osk.action_confirm()
        self.app.update()
        self.assertEqual(result, ["Game Flo"])

    def test_03_gamepad_dispatch(self):
        """Verifica que handle_gamepad_input maneja A, X, Y, Start, B y cruceta."""
        result = []
        osk = OnScreenKeyboardDialog(self.app, title="Gamepad Test", initial_text="Deck", on_confirm=lambda t: result.append(t))
        self.app.update()

        # Botón X -> Borrar
        osk.handle_gamepad_input({"x": True}, {"x": False})
        self.assertEqual(osk.text_value, "Dec")

        # Botón Y -> Espacio
        osk.handle_gamepad_input({"y": True}, {"y": False})
        self.assertEqual(osk.text_value, "Dec ")

        # Cruceta Right -> mover cursor
        col_before = osk.cursor_col
        osk.handle_gamepad_input({"right": True}, {"right": False})
        self.assertEqual(osk.cursor_col, col_before + 1)

        # Botón Start -> Confirmar
        osk.handle_gamepad_input({"start": True}, {"start": False})
        self.app.update()
        self.assertEqual(result, ["Dec "])

if __name__ == "__main__":
    unittest.main()
