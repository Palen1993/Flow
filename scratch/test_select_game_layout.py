import sys
import os
sys.path.insert(0, os.path.abspath("."))
import tkinter as tk
import customtkinter as ctk
from ui.dialogs.select_game_to_edit import SelectGameToEditDialog

print("Testing SelectGameToEditDialog layout and monitor badge...")

root = ctk.CTk()
root.geometry("1020x720")
root.update()

dummy_games = [
    {
        "name": "Assassins Creed Black Flag Resynced with Very Long Subtitle Edition",
        "path": "D:\\Juegos\\Assassins Creed Resynced\\Binaries\\Win64\\ACBlackFlag.exe",
        "monitor": 2,
        "high_priority": True,
        "cover": "default.png"
    },
    {
        "name": "Black Myth Wukong",
        "path": "D:\\Juegos\\Black Myth Wukong\\b1\\Binaries\\Win64\\b1-Win64-Shipping.exe",
        "monitor": 1,
        "high_priority": False,
        "cover": "default.png"
    }
]

dlg = SelectGameToEditDialog(root, dummy_games)
dlg.update_idletasks()
dlg.update()

print(f"Dialog dimensions: {dlg.winfo_width()}x{dlg.winfo_height()}")
assert dlg.winfo_width() >= 900, f"Expected width >= 900, got {dlg.winfo_width()}"
assert dlg.winfo_height() >= 620, f"Expected height >= 620, got {dlg.winfo_height()}"

# Verify rows were created
assert len(dlg._card_rows) == 2, f"Expected 2 rows, got {len(dlg._card_rows)}"

# Test cycling monitor for game 0
old_mon = dummy_games[0]["monitor"]
dlg._on_cycle_single_monitor(0)
new_mon = dummy_games[0]["monitor"]
print(f"Game 0 monitor cycled: {old_mon} -> {new_mon}")

# Test gamepad Y input
dlg.handle_gamepad_input({"y": True}, {"y": False})
post_y_mon = dummy_games[dlg._selected_row_idx]["monitor"]
print(f"Gamepad Y toggled selected row monitor to: {post_y_mon}")

dlg.destroy()
root.destroy()
print("ALL SELECT GAME TO EDIT TESTS PASSED!")
