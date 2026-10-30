import sys
import os
sys.path.insert(0, os.path.abspath("."))
import tkinter as tk
import customtkinter as ctk

from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog
from ui.dialogs.external_import_dialog import ExternalImportDialog

print("Testing GlassFolderBrowserDialog and ExternalImportDialog Gamepad Support...")

root = ctk.CTk()
root.geometry("1020x720")
root.update()

# -------------------------------------------------------------
# 1. Test GlassFolderBrowserDialog
# -------------------------------------------------------------
dlg = GlassFolderBrowserDialog(root, title="Test Selector Carpeta", initial_dir="D:\\Juegos")
dlg.update_idletasks()
dlg.update()

print(f"Browser dimensions: {dlg.winfo_width()}x{dlg.winfo_height()}")
assert dlg.winfo_width() >= 750, f"Expected width >= 750, got {dlg.winfo_width()}"
assert dlg.winfo_height() >= 550, f"Expected height >= 550, got {dlg.winfo_height()}"

# Check detected drives
print(f"Detected drives: {dlg.drives}")
assert len(dlg.drives) >= 1

# Test drive cycling with RB
initial_path = dlg.current_path
if len(dlg.drives) > 1:
    dlg.handle_gamepad_input({"rb": True}, {"rb": False})
    dlg.update_idletasks()
    print(f"Cycled to: {dlg.current_path}")
    assert dlg.current_path != initial_path

# Test jump to games folder with Y
dlg.handle_gamepad_input({"y": True}, {"y": False})
dlg.update_idletasks()
print(f"Jumped to games folder: {dlg.current_path}")
assert "Juegos" in dlg.current_path or "D:" in dlg.current_path or "C:" in dlg.current_path

# Test dynamic button text on selection
dlg._navigate_list(1)
confirm_txt = dlg.btn_confirm_selection.cget("text")
print(f"Confirm button text on item 1: '{confirm_txt}'")
assert "Seleccionar" in confirm_txt

# Test smart selection with Start
dlg.handle_gamepad_input({"start": True}, {"start": False})
print(f"Selected path: {dlg.selected_path}")
assert dlg.selected_path is not None

# -------------------------------------------------------------
# 2. Test ExternalImportDialog Gamepad LB and RB
# -------------------------------------------------------------
import_dlg = ExternalImportDialog(root, on_import_callback=lambda games: None)
import_dlg.update_idletasks()
import_dlg.update()

assert import_dlg.btn_scan_folder.cget("image") is not None, "btn_scan_folder must have LB icon!"
assert import_dlg.btn_manual.cget("image") is not None, "btn_manual must have RB icon!"

# Test RB opens manual add
called_manual = []
import_dlg._open_manual_add = lambda: called_manual.append(True)
handled_rb = import_dlg.handle_gamepad_input({"rb": True}, {"rb": False})
assert handled_rb is True, "RB must be handled by ExternalImportDialog!"
assert len(called_manual) == 1, "_open_manual_add must be called on RB!"

# Test LB opens scan folder
called_scan = []
import_dlg._scan_custom_folder = lambda: called_scan.append(True)
handled_lb = import_dlg.handle_gamepad_input({"lb": True}, {"lb": False})
assert handled_lb is True, "LB must be handled by ExternalImportDialog!"
assert len(called_scan) == 1, "_scan_custom_folder must be called on LB!"

import_dlg.close()
root.destroy()

print("=================================================")
print("ALL FOLDER BROWSER & MANUAL ADD TESTS PASSED 100%!")
print("=================================================")
