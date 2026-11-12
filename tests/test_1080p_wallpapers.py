import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.cover_downloader import search_wallpaper_candidates, search_google_web_wallpapers

class Test1080pWallpapers(unittest.TestCase):
    def test_search_wallpapers_strictly_1080p_or_higher(self):
        """Verifica que el filtro de wallpapers exige >=1080p y rechaza miniaturas 474x266."""
        import html
        import json
        from unittest.mock import MagicMock, patch
        import core.cover_downloader as cd

        cd._CANDIDATES_CACHE.clear()

        low_meta = html.escape(json.dumps({
            "murl": "https://example.com/wukong_thumb.jpg",
            "turl": "https://example.com/wukong_t.jpg",
            "t": "Black Myth Wukong Thumb",
            "desc": "thumbnail"
        }), quote=True)
        hd_meta = html.escape(json.dumps({
            "murl": "https://example.com/wukong_wallpaper_1080.jpg",
            "turl": "https://example.com/wukong_hd_t.jpg",
            "t": "Black Myth Wukong Wallpaper 1080p",
            "desc": "wallpaper"
        }), quote=True)
        fake_bing_html = (
            f'<a class="iusc" m="{low_meta}" href="/images/search?expw=474&exph=266"></a>'
            f'<a class="iusc" m="{hd_meta}" href="/images/search?expw=1920&exph=1080"></a>'
        ).encode("utf-8")

        def _fake_urlopen(req, timeout=2.0):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "bing.com/images/search" in url:
                resp = MagicMock()
                resp.status = 200
                resp.read.return_value = fake_bing_html
                resp.__enter__ = lambda s: s
                resp.__exit__ = lambda s, *a: False
                return resp
            raise OSError("offline in unit test")

        with patch("urllib.request.urlopen", side_effect=_fake_urlopen), \
             patch("core.steamgriddb_client.fetch_steamgriddb_best_assets", return_value=None):
            results = search_wallpaper_candidates("Black Myth Wukong", max_results=12)

        self.assertGreater(len(results), 0, "Debe encontrar wallpapers válidos")
        for r in results:
            sz = r.get("orig_size")
            w, h = sz if sz else (r.get("width", 0), r.get("height", 0))
            if w > 0 and h > 0:
                self.assertGreaterEqual(w, 1920)
                self.assertGreaterEqual(h, 1080)
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
