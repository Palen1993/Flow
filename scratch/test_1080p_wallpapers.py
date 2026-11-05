import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.cover_downloader import search_wallpaper_candidates, search_google_web_wallpapers

class Test1080pWallpapers(unittest.TestCase):
    def test_search_wallpapers_strictly_1080p_or_higher(self):
        """Verifica que todos los wallpapers devueltos por el buscador tienen al menos 1080p (w>=1920, h>=1080)."""
        games_to_test = ["Black Myth Wukong", "The Witcher 3"]
        for g in games_to_test:
            results = search_wallpaper_candidates(g, max_results=12)
            self.assertGreater(len(results), 0, f"Debe encontrar wallpapers para '{g}'")
            print(f"\n[TEST 1080p] '{g}': {len(results)} wallpapers encontrados:")
            for idx, r in enumerate(results):
                sz = r.get("orig_size")
                w, h = sz if sz else (r.get("width", 0), r.get("height", 0))
                print(f"  [{idx}] {w}x{h} | {r.get('name')[:35]} | {r.get('source')} | {r.get('poster_url')[:50]}")
                self.assertGreaterEqual(w, 1920, f"El ancho debe ser >= 1920 pero es {w} ({r.get('name')})")
                self.assertGreaterEqual(h, 1080, f"La altura debe ser >= 1080 pero es {h} ({r.get('name')})")
                # Asegurar que nunca se identifique como 474x266
                self.assertNotEqual((w, h), (474, 266), "Ningún wallpaper debe ser la miniatura de 474x266")

    def test_candidate_orig_size_preserved_against_thumb_size(self):
        """Verifica que cuando CoverPickerDialog prepara y carga miniaturas, no degrada orig_size a 474x266."""
        import tkinter as tk
        from PIL import Image
        from ui.dialogs.cover_picker_dialog import CoverPickerDialog

        root = tk.Tk()
        root.withdraw()
        try:
            dlg = CoverPickerDialog(root, initial_query="Test Game", game_name="Test Game", initial_mode="wallpaper")
            dlg.asset_mode = "wallpaper"
            
            # Simulamos un candidato con tamaño original 1080p
            mock_cand = {
                "id": "wp_test_1",
                "name": "Test Wallpaper 1080p",
                "poster_url": "https://example.com/wp_1080.jpg",
                "thumb_url": "https://example.com/wp_thumb.jpg",
                "orig_size": (1920, 1080),
                "source": "Wallpaper 1080p"
            }
            dlg.filtered_candidates = [mock_cand]
            
            # Simulamos que la miniatura descargada mide 474x266
            thumb_pil = Image.new("RGB", (474, 266), (20, 30, 40))
            preview_im, card_thumb, orig_sz = dlg._prepare_card_and_preview_images(thumb_pil, is_wp=True, card_w=200)
            
            # Se aplica la miniatura a la tarjeta
            dlg._apply_thumbnail_to_card(0, preview_im, card_thumb, orig_size=(474, 266), gen=dlg._search_generation)
            
            # El tamaño en la tarjeta DEBE seguir siendo 1080p (1920, 1080), no (474, 266)
            final_sz = dlg.filtered_candidates[0].get("orig_size")
            self.assertEqual(final_sz, (1920, 1080), "orig_size no debe ser degradado a (474, 266)")
            dlg.destroy()
        finally:
            root.destroy()

if __name__ == "__main__":
    unittest.main()
