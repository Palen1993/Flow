import unittest
from typing import Optional, Dict, Any

# Sony IDs
SONY_VID = 0x054C
SONY_PIDS = {
    0x0CE6: "DualSense Wireless Controller (PS5)",
    0x0DF2: "DualSense Edge Controller (PS5)",
    0x05C4: "DualShock 4 Controller (PS4 v1)",
    0x09CC: "DualShock 4 Controller (PS4 v2)",
    0x0BA0: "DualShock 4 USB Wireless Adapter"
}

def decode_playstation_hid_report(pid: int, report: bytes) -> Optional[Dict[str, Any]]:
    """
    Decodifica el estado de carga y nivel de batería para DualSense (PS5) y DualShock 4 (PS4).
    Compatible con reportes USB (0x01) y Bluetooth (0x31 para DualSense, 0x11 para DualShock 4).
    """
    if not report or len(report) < 31:
        return None

    rep_id = report[0]
    is_dualsense = (pid in (0x0CE6, 0x0DF2))
    
    if is_dualsense:
        if rep_id == 0x31 and len(report) >= 55:
            val = report[54]
        elif rep_id == 0x01 and len(report) >= 54:
            val = report[53]
        else:
            return None
        bat_level = val & 0x0F
        charging_code = (val >> 4) & 0x0F
        is_charging = (charging_code in (0x1, 0x2))
        is_full = (charging_code == 0x2 or bat_level >= 10)
    else:
        # DualShock 4
        if rep_id == 0x11 and len(report) >= 33:
            val = report[32]
        elif rep_id == 0x01 and len(report) >= 31:
            val = report[30]
        else:
            return None
        bat_level = val & 0x0F
        is_charging = bool(val & 0x10)
        is_full = (bat_level >= 10 and is_charging)

    percent = 100 if is_full else min(100, bat_level * 10)

    if is_charging:
        icon = "⚡"
        if percent >= 100 or is_full:
            text = "100% (Cargado)"
            level = "full"
        else:
            text = f"{percent}% (Cargando)"
            level = "charging"
    else:
        if percent <= 15:
            icon = "🪫"
            level = "empty" if percent <= 5 else "low"
        elif percent <= 40:
            icon = "🪫"
            level = "low"
        elif percent <= 80:
            icon = "🔋"
            level = "medium"
        else:
            icon = "🔋"
            level = "full"
        text = f"{percent}%"

    return {
        "connected": True,
        "is_wired": bool(is_charging and rep_id == 0x01),
        "is_charging": is_charging,
        "level": level,
        "percent": percent,
        "icon": icon,
        "text": text
    }


class TestPlayStationHIDDecoding(unittest.TestCase):
    def test_dualsense_usb_charging(self):
        # 64 bytes, rep_id=0x01, byte 53: 0x18 (80%, charging)
        buf = bytearray(64)
        buf[0] = 0x01
        buf[53] = 0x18
        res = decode_playstation_hid_report(0x0CE6, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 80)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["icon"], "⚡")
        self.assertEqual(res["text"], "80% (Cargando)")
        self.assertEqual(res["level"], "charging")

    def test_dualsense_usb_full(self):
        # 64 bytes, rep_id=0x01, byte 53: 0x2A (100%, full charged)
        buf = bytearray(64)
        buf[0] = 0x01
        buf[53] = 0x2A
        res = decode_playstation_hid_report(0x0CE6, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 100)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["icon"], "⚡")
        self.assertEqual(res["text"], "100% (Cargado)")
        self.assertEqual(res["level"], "full")

    def test_dualsense_usb_discharging(self):
        # 64 bytes, rep_id=0x01, byte 53: 0x07 (70%, not charging)
        buf = bytearray(64)
        buf[0] = 0x01
        buf[53] = 0x07
        res = decode_playstation_hid_report(0x0CE6, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 70)
        self.assertFalse(res["is_charging"])
        self.assertEqual(res["icon"], "🔋")
        self.assertEqual(res["text"], "70%")
        self.assertEqual(res["level"], "medium")

    def test_dualsense_bt_charging(self):
        # 78 bytes, rep_id=0x31, byte 54: 0x16 (60%, charging)
        buf = bytearray(78)
        buf[0] = 0x31
        buf[54] = 0x16
        res = decode_playstation_hid_report(0x0DF2, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 60)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["text"], "60% (Cargando)")

    def test_dualshock4_usb_discharging(self):
        # 64 bytes, rep_id=0x01, byte 30: 0x05 (50%, not charging)
        buf = bytearray(64)
        buf[0] = 0x01
        buf[30] = 0x05
        res = decode_playstation_hid_report(0x05C4, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 50)
        self.assertFalse(res["is_charging"])
        self.assertEqual(res["text"], "50%")

    def test_dualshock4_bt_charging(self):
        # 78 bytes, rep_id=0x11, byte 32: 0x1A (100% full, charging)
        buf = bytearray(78)
        buf[0] = 0x11
        buf[32] = 0x1A
        res = decode_playstation_hid_report(0x09CC, bytes(buf))
        self.assertIsNotNone(res)
        self.assertEqual(res["percent"], 100)
        self.assertTrue(res["is_charging"])
        self.assertEqual(res["text"], "100% (Cargado)")
        self.assertEqual(res["icon"], "⚡")

if __name__ == "__main__":
    unittest.main()
