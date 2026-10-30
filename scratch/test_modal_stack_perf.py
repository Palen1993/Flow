import sys
import os
import time
import unittest
import tkinter as tk
import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from ui.dialogs.base_dialog import BaseGlassDialog, register_modal_stack, unregister_modal_stack

class MockApp(ctk.CTk):
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

class TestModalStackPerformance(unittest.TestCase):
    def setUp(self):
        self.app = MockApp()
        self.app.update()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_01_empty_modal_stack_speed(self):
        """Verifica que el chequeo de modal en reposo tarda menos de 0.005 ms (5 µs)."""
        t0 = time.perf_counter()
        for _ in range(1000):
            res = self.app._get_topmost_active_modal()
            self.assertIsNone(res)
        avg_us = ((time.perf_counter() - t0) / 1000.0) * 1_000_000.0
        print(f"\n  [Perf] Chequeo de modal stack en reposo: {avg_us:.3f} µs por llamada")
        self.assertLess(avg_us, 5.0)

    def test_02_dialog_push_pop(self):
        """Verifica que BaseGlassDialog se registra y desregistra automáticamente en tiempo O(1)."""
        dlg = BaseGlassDialog(self.app, title="Test Modal", width=300, height=200, auto_grab=False)
        self.app.update()

        # El diálogo debe estar en la cima de la pila
        top = self.app._get_topmost_active_modal()
        self.assertEqual(top, dlg)

        # Al destruirse, debe desaparecer de la pila
        dlg.destroy()
        self.app.update()
        self.assertIsNone(self.app._get_topmost_active_modal())

    def test_03_nested_dropdown_stack_order(self):
        """Verifica el orden LIFO: un dropdown encima de un diálogo tiene prioridad de input."""
        dlg1 = BaseGlassDialog(self.app, title="Dialog 1", width=300, height=200, auto_grab=False)
        dlg2 = BaseGlassDialog(self.app, title="Dialog 2 (Top)", width=200, height=150, auto_grab=False)
        self.app.update()

        # dlg2 está encima de dlg1
        self.assertEqual(self.app._get_topmost_active_modal(), dlg2)

        dlg2.destroy()
        self.app.update()
        # Ahora dlg1 vuelve a ser el activo
        self.assertEqual(self.app._get_topmost_active_modal(), dlg1)

        dlg1.destroy()
        self.app.update()
        self.assertIsNone(self.app._get_topmost_active_modal())

if __name__ == "__main__":
    unittest.main()
