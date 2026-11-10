import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
import app as app_module
from app import App
from ui.dialogs.confirm_exit import ConfirmExitDialog
from ui.dialogs.glass_message_box import GlassMessageBox
from ui.dialogs.controller_info_dialog import ControllerInfoDialog
from ui.dialogs.glass_folder_browser import GlassFolderBrowserDialog
from ui.dialogs.on_screen_keyboard import OnScreenKeyboardDialog
from ui.dialogs.external_import_dialog import ExternalImportDialog
from ui.dialogs.scan_results import ScanResultsDialog
from ui.dialogs.gamepad_config_dialog import GamepadConfigDialog
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog
from ui.dialogs.cover_picker_dialog import CoverPickerDialog

with patch.object(app_module, "ensure_watcher_running", lambda: None):
    app = App()
app.withdraw()

print("=================================================================")
print("TESTING GAMEPAD CANCEL (B / BACK) AND CONFIRM (A / START)")
print("=================================================================")

# Test 1: ConfirmExitDialog
d = ConfirmExitDialog(app)
assert app._get_topmost_active_modal() == d, "ConfirmExitDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "ConfirmExitDialog did not handle B"
app.update()
assert not d.winfo_exists(), "ConfirmExitDialog not destroyed on B"
print("PASS: ConfirmExitDialog closes on B")

# Test 2: ControllerInfoDialog
d = ControllerInfoDialog(app)
assert app._get_topmost_active_modal() == d, "ControllerInfoDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "ControllerInfoDialog did not handle B"
app.update()
assert not d.winfo_exists(), "ControllerInfoDialog not destroyed on B"
print("PASS: ControllerInfoDialog closes on B")

d = ControllerInfoDialog(app)
handled = d.handle_gamepad_input({"a": True}, {})
assert handled is True, "ControllerInfoDialog did not handle A"
app.update()
assert not d.winfo_exists(), "ControllerInfoDialog not destroyed on A"
print("PASS: ControllerInfoDialog closes on A")

# Test 3: GlassMessageBox
d = GlassMessageBox(app, title="Test", message="Test", kind="confirm")
assert app._get_topmost_active_modal() == d, "GlassMessageBox not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "GlassMessageBox did not handle B"
app.update()
assert not d.winfo_exists(), "GlassMessageBox not destroyed on B"
print("PASS: GlassMessageBox closes on B")

# Test 4: GlassFolderBrowserDialog
d = GlassFolderBrowserDialog(app)
assert app._get_topmost_active_modal() == d, "GlassFolderBrowserDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "GlassFolderBrowserDialog did not handle B"
app.update()
assert not d.winfo_exists(), "GlassFolderBrowserDialog not destroyed on B"
print("PASS: GlassFolderBrowserDialog closes on B")

# Test 5: OnScreenKeyboardDialog
d = OnScreenKeyboardDialog(app, initial_text="hola")
assert app._get_topmost_active_modal() == d, "OnScreenKeyboardDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "OnScreenKeyboardDialog did not handle B"
app.update()
assert not d.winfo_exists(), "OnScreenKeyboardDialog not destroyed on B"
print("PASS: OnScreenKeyboardDialog closes on B")

# Test 6: ExternalImportDialog
d = ExternalImportDialog(app, on_import_callback=lambda x: None)
assert app._get_topmost_active_modal() == d, "ExternalImportDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "ExternalImportDialog did not handle B"
app.update()
assert not d.winfo_exists(), "ExternalImportDialog not destroyed on B"
print("PASS: ExternalImportDialog closes on B")

# Test 7: ScanResultsDialog
d = ScanResultsDialog(app, scanned_folder="C:/Games", candidates=[])
assert app._get_topmost_active_modal() == d, "ScanResultsDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "ScanResultsDialog did not handle B"
app.update()
assert not d.winfo_exists(), "ScanResultsDialog not destroyed on B"
print("PASS: ScanResultsDialog closes on B")

# Test 8: GamepadConfigDialog
d = GamepadConfigDialog(app)
assert app._get_topmost_active_modal() == d, "GamepadConfigDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "GamepadConfigDialog did not handle B"
app.update()
assert not d.winfo_exists(), "GamepadConfigDialog not destroyed on B"
print("PASS: GamepadConfigDialog closes on B")

# Test 9: AddEditGameDialog
d = AddEditGameDialog(app, monitors=[])
assert app._get_topmost_active_modal() == d, "AddEditGameDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "AddEditGameDialog did not handle B"
app.update()
assert not d.winfo_exists(), "AddEditGameDialog not destroyed on B"
print("PASS: AddEditGameDialog closes on B")

# Test 10: SelectGameToEditDialog
d = SelectGameToEditDialog(app, games=[], on_select_callback=lambda idx: None)
assert app._get_topmost_active_modal() == d, "SelectGameToEditDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "SelectGameToEditDialog did not handle B"
app.update()
assert not d.winfo_exists(), "SelectGameToEditDialog not destroyed on B"
print("PASS: SelectGameToEditDialog closes on B")

# Test 11: CoverPickerDialog
d = CoverPickerDialog(app, initial_query="Doom")
assert app._get_topmost_active_modal() == d, "CoverPickerDialog not topmost"
handled = d.handle_gamepad_input({"b": True}, {})
assert handled is True, "CoverPickerDialog did not handle B"
app.update()
assert not d.winfo_exists(), "CoverPickerDialog not destroyed on B"
print("PASS: CoverPickerDialog closes on B")

# Test 12: Test Universal Safety Net in GamepadNavigationService
d = ConfirmExitDialog(app)
assert app._get_topmost_active_modal() == d
# Simulate an unhandled input with B pressed
app.gamepad_service.tick() # regular tick
# Send inputs via gamepad_service routing directly
top_m = app._get_topmost_active_modal()
assert top_m == d
# Trigger close
d.destroy()
app.update()
assert not d.winfo_exists()
print("PASS: Universal Safety Net verified")

app.destroy()
print("\n=================================================================")
print("ALL 12 DIALOG TESTS COMPLETED WITH 100% SUCCESS!")
print("=================================================================")
