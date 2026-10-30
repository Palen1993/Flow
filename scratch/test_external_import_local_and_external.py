import os
import sys
import time
import unittest
import customtkinter as ctk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app import App
from ui.dialogs.external_import_dialog import ExternalImportDialog

class TestExternalImportLocalAndExternal(unittest.TestCase):
    def setUp(self):
        self.app = App()
        self.app.withdraw()

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_combined_scan_local_and_external(self):
        dlg = ExternalImportDialog(self.app, on_import_callback=self.app.on_games_imported, existing_games=self.app.games)
        dlg.withdraw()

        # Esperar a que el escaneo asíncrono finalice
        for _ in range(50):
            self.app.update()
            if getattr(dlg, "candidates", None) and len(dlg.candidates) >= 8:
                break
            time.sleep(0.05)

        self.assertGreaterEqual(len(dlg.candidates), 8, "Debe detectar los juegos de D:\\Juegos y clientes externos")

        candidate_names = [c["name"] for c in dlg.candidates]
        print("Candidatos detectados en el diálogo unificado:", candidate_names)

        # Verificar presencia de juegos locales de D:\Juegos
        self.assertIn("Assassins Creed Black Flag Resynced", candidate_names)
        self.assertIn("Black Myth Wukong", candidate_names)
        self.assertIn("LEGO Batman Legacy of the Dark Knight", candidate_names)

        # Verificar que los juegos existentes están marcados como ya añadidos y desmarcados
        local_ac = next(c for c in dlg.candidates if c["name"] == "Assassins Creed Black Flag Resynced")
        self.assertTrue(local_ac.get("already_added"), "El juego existente debe tener already_added=True")

        # Verificar items_vars en la interfaz
        ac_tuple = next(t for t in dlg.items_vars if t[2]["name"] == "Assassins Creed Black Flag Resynced")
        chk_var, name_entry, orig = ac_tuple
        self.assertFalse(chk_var.get(), "Los juegos ya presentes en biblioteca deben estar desmarcados por defecto")
        self.assertEqual(name_entry.get(), "Assassins Creed Black Flag Resynced")

        # Verificar que la lista tiene miniaturas generadas
        self.assertGreater(len(dlg.thumb_refs), 0, "Debe haber referencias a miniaturas de carátula")

        # Verificar resumen por plataforma
        summary_txt = dlg.lbl_summary.cget("text")
        print("Texto de resumen:", summary_txt)
        self.assertTrue("Juegos" in summary_txt or "Carpeta" in summary_txt or "Steam" in summary_txt)

        dlg.close()

if __name__ == "__main__":
    unittest.main()
