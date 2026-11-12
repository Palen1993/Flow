import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.platform_layer import (
    is_windows,
    is_linux,
    is_macos,
    win32con,
    win32gui,
    win32api,
    win32ui,
    win32process,
    winreg,
    winsound,
    get_system_drives,
    safe_set_dpi_awareness,
    safe_set_app_user_model_id,
    safe_play_sound
)

class TestPlatformLayer(unittest.TestCase):
    def test_platform_detection(self):
        # En Linux VM, is_linux debe ser True e is_windows False
        self.assertTrue(is_linux())
        self.assertFalse(is_windows())
        self.assertFalse(is_macos())

    def test_win32con_constants(self):
        self.assertEqual(win32con.SW_SHOWMINIMIZED, 2)
        self.assertEqual(win32con.SW_RESTORE, 9)
        self.assertEqual(win32con.GWL_STYLE, -16)
        self.assertEqual(win32con.WS_POPUP, 0x80000000)
        self.assertEqual(win32con.HWND_TOPMOST, -1)

    def test_win32gui_shims(self):
        self.assertTrue(win32gui.ShowWindow(1234, 1))
        self.assertEqual(win32gui.GetWindowLong(1234, -16), 0)
        self.assertTrue(win32gui.SetWindowPos(1234, 0, 0, 0, 100, 100, 0))
        self.assertEqual(win32gui.GetWindowText(1234), "")
        self.assertFalse(win32gui.IsWindowVisible(1234))

    def test_win32api_shims(self):
        self.assertEqual(win32api.GetCursorPos(), (0, 0))
        mon_info = win32api.GetMonitorInfo(1)
        self.assertIn("Monitor", mon_info)
        self.assertIn("Work", mon_info)
        self.assertEqual(mon_info["Monitor"], (0, 0, 1920, 1080))

    def test_winreg_shims(self):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software") as k:
            self.assertIsNotNone(k)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "TestKey") as k:
            self.assertIsNotNone(k)
        winreg.SetValueEx(None, "Val", 0, winreg.REG_SZ, "data")
        val, typ = winreg.QueryValueEx(None, "Val")
        self.assertEqual(typ, winreg.REG_SZ)

    def test_winsound_shims(self):
        self.assertTrue(winsound.PlaySound(b"RIFFdummy", winsound.SND_MEMORY))
        self.assertTrue(safe_play_sound(b"RIFFdummy"))

    def test_get_system_drives(self):
        drives = get_system_drives()
        self.assertIsInstance(drives, list)
        self.assertGreaterEqual(len(drives), 1)
        self.assertIn("/", drives)

    def test_safe_system_calls_no_crash(self):
        self.assertFalse(safe_set_dpi_awareness())  # En Linux retorna False limpiamente sin fallar
        self.assertFalse(safe_set_app_user_model_id("test.app.id"))

if __name__ == "__main__":
    unittest.main()
