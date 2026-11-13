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
    _Win32ConShim,
    _Win32GuiShim,
    _Win32ApiShim,
    _WinRegShim,
    _WinSoundShim,
    get_system_drives,
    safe_set_dpi_awareness,
    safe_set_app_user_model_id,
    safe_play_sound
)

class TestPlatformLayer(unittest.TestCase):
    def test_platform_detection(self):
        if is_windows():
            self.assertTrue(is_windows())
            self.assertFalse(is_linux())
            self.assertFalse(is_macos())
        elif sys.platform.startswith("linux"):
            self.assertTrue(is_linux())
            self.assertFalse(is_windows())
            self.assertFalse(is_macos())
        elif sys.platform == "darwin":
            self.assertTrue(is_macos())
            self.assertFalse(is_windows())

    def test_win32con_constants(self):
        for mod in (win32con, _Win32ConShim):
            self.assertEqual(mod.SW_SHOWMINIMIZED, 2)
            self.assertEqual(mod.SW_RESTORE, 9)
            self.assertEqual(mod.GWL_STYLE, -16)
            self.assertEqual(mod.WS_POPUP & 0xFFFFFFFF, 0x80000000)
            self.assertEqual(mod.HWND_TOPMOST, -1)

    def test_win32gui_shims(self):
        self.assertTrue(hasattr(win32gui, "ShowWindow"))
        self.assertTrue(hasattr(win32gui, "SetWindowPos"))
        self.assertTrue(_Win32GuiShim.ShowWindow(1234, 1))
        self.assertEqual(_Win32GuiShim.GetWindowLong(1234, -16), 0)
        self.assertTrue(_Win32GuiShim.SetWindowPos(1234, 0, 0, 0, 100, 100, 0))
        self.assertEqual(_Win32GuiShim.GetWindowText(1234), "")
        self.assertFalse(_Win32GuiShim.IsWindowVisible(1234))

    def test_win32api_shims(self):
        self.assertTrue(hasattr(win32api, "GetCursorPos"))
        self.assertTrue(hasattr(win32api, "GetMonitorInfo"))
        self.assertEqual(_Win32ApiShim.GetCursorPos(), (0, 0))
        mon_info = _Win32ApiShim.GetMonitorInfo(1)
        self.assertIn("Monitor", mon_info)
        self.assertIn("Work", mon_info)
        self.assertEqual(mon_info["Monitor"], (0, 0, 1920, 1080))

    def test_winreg_shims(self):
        self.assertTrue(hasattr(winreg, "OpenKey"))
        with _WinRegShim.OpenKey(_WinRegShim.HKEY_CURRENT_USER, "Software") as k:
            self.assertIsNotNone(k)
        with _WinRegShim.CreateKey(_WinRegShim.HKEY_CURRENT_USER, "TestKey") as k:
            self.assertIsNotNone(k)
        _WinRegShim.SetValueEx(None, "Val", 0, _WinRegShim.REG_SZ, "data")
        val, typ = _WinRegShim.QueryValueEx(None, "Val")
        self.assertEqual(typ, _WinRegShim.REG_SZ)

    def test_winsound_shims(self):
        self.assertTrue(hasattr(winsound, "PlaySound"))
        self.assertTrue(_WinSoundShim.PlaySound(b"RIFFdummy", _WinSoundShim.SND_MEMORY))
        if not is_windows():
            self.assertTrue(safe_play_sound(b"RIFFdummy"))

    def test_get_system_drives(self):
        drives = get_system_drives()
        self.assertIsInstance(drives, list)
        self.assertGreaterEqual(len(drives), 1)
        if is_windows():
            self.assertTrue(any(len(d) >= 2 and d[1] == ":" for d in drives))
        else:
            self.assertIn("/", drives)

    def test_safe_system_calls_no_crash(self):
        dpi_res = safe_set_dpi_awareness()
        aumid_res = safe_set_app_user_model_id("test.app.id")
        self.assertIsInstance(dpi_res, bool)
        self.assertIsInstance(aumid_res, bool)
        if not is_windows():
            self.assertFalse(dpi_res)
            self.assertFalse(aumid_res)

if __name__ == "__main__":
    unittest.main()
