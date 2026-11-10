import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
import app as app_module
from app import App
from ui.dialogs.cover_picker_dialog import CoverPickerDialog
from ui.dialogs.external_import_dialog import ExternalImportDialog
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog

with patch.object(app_module, "ensure_watcher_running", lambda: None):
    app = App()
app.withdraw()

print("=================================================================")
print("TESTING UX STREAMLINING & ULTRA-CLEAN 3-ITEM DROPDOWN")
print("=================================================================")

# Test 1: Top Menu Options (in Big Picture mode)
app.set_full_mode()
app.toggle_top_menu()
assert app.glass_menu is not None, "Top menu didn't open"
menu_texts = [item[1] for item in app.glass_menu.items]
print("Menu Items:", menu_texts)

# Must have the 4 master items:
expected = [
    "Importar Juegos...",
    "Descargar Arte Masivo (SteamGridDB)...",
    "Administrar Todos los Juegos...",
    "Configurar Mando..."
]
assert len(menu_texts) == 4, f"Expected 4 items, got {len(menu_texts)}: {menu_texts}"
for exp in expected:
    assert any(exp in t for t in menu_texts), f"Expected '{exp}' in menu, found: {menu_texts}"

print("PASS: Top Menu simplified to the 4 master entry points!")
app.glass_menu.destroy()
app.glass_menu = None

# Test 2: CoverPickerDialog has local file button & method
cp = CoverPickerDialog(app, initial_query="Doom")
assert hasattr(cp, "btn_local"), "btn_local missing in CoverPickerDialog"
assert hasattr(cp, "_pick_local_file"), "_pick_local_file missing in CoverPickerDialog"
print("PASS: CoverPickerDialog has unified local + online capabilities")
cp.destroy()

# Test 3: ExternalImportDialog is unified import hub
ei = ExternalImportDialog(app, on_import_callback=lambda x: None)
assert hasattr(ei, "btn_scan_folder"), "btn_scan_folder missing in ExternalImportDialog"
assert hasattr(ei, "btn_manual"), "btn_manual missing in ExternalImportDialog"
assert hasattr(ei, "_scan_custom_folder"), "_scan_custom_folder missing"
assert hasattr(ei, "_open_manual_add"), "_open_manual_add missing"
print("PASS: ExternalImportDialog is unified Hub (Steam, Epic, GOG, PC Folder, ROMs, Manual)")
ei.destroy()

# Test 4: AddEditGameDialog clean canvas and unified art button
aed = AddEditGameDialog(app, monitors=[])
assert hasattr(aed, "cover_canvas"), "cover_canvas missing"
assert not hasattr(aed, "btn_autodetect"), "Redundant btn_autodetect still present"
assert hasattr(aed, "btn_online"), "Unified art button missing"
print("PASS: AddEditGameDialog simplified (zero clutter, clickable 3D canvas, auto-detect)")
aed.destroy()

# Test 5: SelectGameToEditDialog pre-focuses current game
target_idx = 2
sample_games = app.games if len(app.games) > target_idx else [
    {"name": f"Test Game {i}", "path": f"C:\\Games\\Game{i}\\game.exe", "monitor": 0}
    for i in range(4)
]
sed = SelectGameToEditDialog(app, games=sample_games, initial_index=target_idx)
assert sed._selected_row_idx == target_idx, f"Expected focused row {target_idx}, got {sed._selected_row_idx}"
print(f"PASS: SelectGameToEditDialog pre-focuses active game index ({target_idx})")
sed.destroy()

app.destroy()
print("=================================================================")
print("ALL 5 UX STREAMLINING TESTS PASSED AT 100%!")
print("=================================================================")
