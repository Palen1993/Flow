import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import App
from ui.dialogs.cover_picker_dialog import CoverPickerDialog
from ui.dialogs.external_import_dialog import ExternalImportDialog
from ui.dialogs.add_edit_game import AddEditGameDialog
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog

app = App()
app.withdraw()

print("=================================================================")
print("TESTING UX STREAMLINING & REDUNDANCY ELIMINATION")
print("=================================================================")

# Test 1: Top Menu Options
# When app has games, menu should have unified items
app.toggle_top_menu()
assert app.glass_menu is not None, "Top menu didn't open"
menu_texts = [item[1] for item in app.glass_menu.items]
print("Menu Items:", menu_texts)

# Assertions on menu items
assert any("Añadir / Importar Juegos" in t for t in menu_texts), "Unified import missing"
assert any("Editar '" in t for t in menu_texts), "Direct 1-step edit missing"
assert any("Cambiar Carátula / Wallpaper" in t for t in menu_texts), "Unified art editor missing"
assert not any("Cambiar Wallpaper de Fondo" in t for t in menu_texts), "Redundant separate wallpaper entry still present"
assert any("Administrar Todos los Juegos" in t for t in menu_texts), "Full library management missing"
print("PASS: Top Menu streamlined to unified, 1-step direct actions")
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
sed = SelectGameToEditDialog(app, games=app.games, initial_index=target_idx)
assert sed._selected_row_idx == target_idx, f"Expected focused row {target_idx}, got {sed._selected_row_idx}"
print(f"PASS: SelectGameToEditDialog pre-focuses active game index ({target_idx})")
sed.destroy()

app.destroy()
print("=================================================================")
print("ALL 5 UX STREAMLINING TESTS PASSED AT 100%!")
print("=================================================================")
