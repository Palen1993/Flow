"""
Modal Stack Manager for GameFlow Launcher.
Provides O(1) modal tracking and gamepad dispatch decoupling.
"""
from typing import Any
import tkinter as tk

def register_modal_stack(widget: Any):
    """Registra una ventana modal o popup flotante en la pila LIFO O(1) de la ventana raíz."""
    curr = getattr(widget, "master", None) or getattr(widget, "parent", None)
    while curr:
        if hasattr(curr, "push_modal"):
            curr.push_modal(widget)
            return
        curr = getattr(curr, "master", None) or getattr(curr, "parent", None)

def unregister_modal_stack(widget: Any):
    """Elimina una ventana modal o popup flotante de la pila LIFO O(1) de la ventana raíz."""
    curr = getattr(widget, "master", None) or getattr(widget, "parent", None)
    while curr:
        if hasattr(curr, "pop_modal"):
            curr.pop_modal(widget)
            return
        curr = getattr(curr, "master", None) or getattr(curr, "parent", None)
