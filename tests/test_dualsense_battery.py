import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import patch, MagicMock
import time
import customtkinter as ctk

from gamepad_manager import (
    decode_playstation_hid_report,
    _get_playstation_hid_battery,
    _battery_for_device,
    _PS_BATTERY_CACHE,
    _WINMM_CAPS_CACHE
)
from ui.dialogs.controller_info_dialog import _ControllerRow


class TestDualSenseBattery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = ctk.CTk()
            cls.root.withdraw()
        except Exception:
            cls.root = None

    @classmethod
    def tearDownClass(cls):
        if cls.root:
            try:
                cls.root.destroy()
            except Exception:
                pass

    def setUp(self):
        _PS_BATTERY_CACHE.clear()

    def test_01_dualsense_usb_charging_and_full(self):
        # DualSense USB Report 0x01
        # Byte 53: 0x18 -> 80% charging
        buf_charging = bytearray(64)
        buf_charging[0] = 0x01
        buf_charging[53] = 0x18
        res = decode_playstation_hid_report(0x0CE6, bytes(buf_charging))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 80)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["icon"], "⚡")
        self.assertEqual(res["text"], "80% (Cargando)")

        # Byte 53: 0x2A -> 100% full
        buf_full = bytearray(64)
        buf_full[0] = 0x01
        buf_full[53] = 0x2A
        res_full = decode_playstation_hid_report(0x0CE6, bytes(buf_full))
        self.assertIsNotNone(res_full)
        self.assertEqual(res_full["percent"], 100)
        self.assertTrue(res_full["is_charging"])
        self.assertEqual(res_full["icon"], "⚡")
        self.assertEqual(res_full["text"], "100% (Cargado)")

    def test_02_dualsense_bt_discharging(self):
        # DualSense BT Report 0x31
        # Byte 54: 0x04 -> 40% discharging
        buf = bytearray(78)
        buf[0] = 0x31
        buf[54] = 0x04
        res = decode_playstation_hid_report(0x0DF2, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 40)
        self.assertFalse(res["is_charging"])
        self.assertEqual(res["icon"], "🪫")
        self.assertEqual(res["text"], "40%")

    def test_03_dualshock4_usb_and_bt(self):
        # DualShock 4 USB Report 0x01
        # Byte 30: 0x09 -> 90% discharging
        buf_usb = bytearray(64)
        buf_usb[0] = 0x01
        buf_usb[30] = 0x09
        res_usb = decode_playstation_hid_report(0x05C4, bytes(buf_usb))
        self.assertIsNotNone(res_usb)
        self.assertEqual(res_usb["percent"], 90)
        self.assertFalse(res_usb["is_charging"])
        self.assertEqual(res_usb["icon"], "🔋")
        self.assertEqual(res_usb["text"], "90%")

        # DualShock 4 BT Report 0x11
        # Byte 32: 0x17 -> 70% charging
        buf_bt = bytearray(78)
        buf_bt[0] = 0x11
        buf_bt[32] = 0x17
        res_bt = decode_playstation_hid_report(0x09CC, bytes(buf_bt))
        self.assertIsNotNone(res_bt)
        self.assertEqual(res_bt["percent"], 70)
        self.assertTrue(res_bt["is_charging"])
        self.assertEqual(res_bt["icon"], "⚡")
        self.assertEqual(res_bt["text"], "70% (Cargando)")

    def test_04_cache_ttl_behavior(self):
        with patch("core.gamepad_hid._query_sony_hid_battery") as mock_query:
            mock_query.return_value = {
                "connected": True, "percent": 75, "is_charging": False,
                "level": "medium", "icon": "🔋", "text": "75%"
            }
            # First call queries HID
            res1 = _get_playstation_hid_battery(0)
            self.assertEqual(mock_query.call_count, 1)
            self.assertEqual(res1["percent"], 75)

            # Second immediate call uses cache (call count remains 1)
            res2 = _get_playstation_hid_battery(0)
            self.assertEqual(mock_query.call_count, 1)
            self.assertEqual(res2["percent"], 75)

    def test_05_battery_for_device_integration(self):
        # Simulate WinMM PlayStation device
        with patch("gamepad_manager._read_winmm_dev", return_value={"a": False}), \
             patch("gamepad_manager._winmm_caps", return_value=(0x054C, 0x0CE6, "Wireless Controller")), \
             patch("gamepad_manager._get_playstation_hid_battery") as mock_ps_bat:
            
            mock_ps_bat.return_value = {
                "connected": True,
                "is_wired": False,
                "is_charging": True,
                "level": "charging",
                "percent": 80,
                "icon": "⚡",
                "text": "80% (Cargando)"
            }
            dev = ("winmm", 0)
            bat = _battery_for_device(dev)
            self.assertTrue(bat["connected"])
            self.assertTrue(bat["is_charging"])
            self.assertEqual(bat["percent"], 80)
            self.assertEqual(bat["icon"], "⚡")
            self.assertEqual(bat["text"], "80% (Cargando)")

    def test_06_controller_row_charging_ui(self):
        if not self.root:
            self.skipTest("No GUI display available")
        row = _ControllerRow(self.root, "TEST MANDO")
        info = {
            "connected": True,
            "device_name": "DualSense Wireless Controller",
            "family": "playstation",
            "is_charging": True,
            "level": "charging",
            "percent": 65
        }
        row.update_info(info)
        self.assertEqual(row.lbl_percent.cget("text"), "65%")
        self.assertIn("Cargando", row.lbl_state.cget("text"))


if __name__ == "__main__":
    unittest.main()
