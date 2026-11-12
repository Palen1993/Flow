"""Prueba unitaria de la lógica de mando principal/secundario simulando dispositivos."""
import os
import sys
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import gamepad_manager as gm


class TestDualGamepadPriority(unittest.TestCase):
    def setUp(self):
        self._orig_read = gm._read_device
        self._orig_xinput = gm._read_xinput_slot
        self._orig_winmm = gm._read_winmm_dev
        self._orig_enum = gm._enumerate_connected
        self._orig_interval = gm.ENUM_INTERVAL_S
        self._orig_grace = gm.PRIMARY_GRACE_S

    def tearDown(self):
        gm._read_device = self._orig_read
        gm._read_xinput_slot = self._orig_xinput
        gm._read_winmm_dev = self._orig_winmm
        gm._enumerate_connected = self._orig_enum
        gm.ENUM_INTERVAL_S = self._orig_interval
        gm.PRIMARY_GRACE_S = self._orig_grace

    def test_primary_sticky_secondary_readonly_and_promotion(self):
        conn = {}
        gm._read_device = lambda dev: conn.get(dev)
        gm._read_xinput_slot = lambda s: conn.get(("xinput", s))
        gm._read_winmm_dev = lambda d: conn.get(("winmm", d))
        gm._enumerate_connected = lambda t="any": [d for d in [("xinput", 0), ("xinput", 1), ("winmm", 0)] if d in conn]
        gm.ENUM_INTERVAL_S = 0.0
        gm.PRIMARY_GRACE_S = 0.0

        S = lambda a=False: dict(gm._EMPTY_STATE, a=a)

        # 1. Conecta primero un PlayStation (winmm 0)
        conn[("winmm", 0)] = S()
        ok, _, _ = gm.poll_active_gamepad("any")
        self.assertTrue(ok)
        self.assertEqual(gm.get_primary_controller(), ("winmm", 0))

        # 2. Conecta después un Xbox en ranura 0 -> NO debe robar el control
        conn[("xinput", 0)] = S(a=True)
        ok, _, st = gm.poll_active_gamepad("any")
        self.assertEqual(gm.get_primary_controller(), ("winmm", 0))
        self.assertFalse(st["a"])
        self.assertEqual(gm.get_connected_controller_family(), "playstation")
        pads = gm.get_all_gamepads_info()
        self.assertEqual([p["role"] for p in pads], ["principal", "secundario"])
        self.assertEqual(pads[1]["device"], ("xinput", 0))
        bat = gm.get_gamepad_battery_info()
        self.assertTrue(bat["secondary"] and bat["secondary"]["device"] == ("xinput", 0))

        # 3. Se desconecta el principal -> el secundario asciende
        del conn[("winmm", 0)]
        gm.poll_active_gamepad("any")
        ok, _, st = gm.poll_active_gamepad("any")
        self.assertTrue(ok)
        self.assertEqual(gm.get_primary_controller(), ("xinput", 0))
        self.assertTrue(st["a"])

        # 4. Vuelve el PlayStation -> ahora es secundario
        conn[("winmm", 0)] = S(a=True)
        gm.poll_active_gamepad("any")
        self.assertEqual(gm.get_primary_controller(), ("xinput", 0))
        self.assertEqual([p["device"] for p in gm.get_all_gamepads_info()], [("xinput", 0), ("winmm", 0)])


if __name__ == "__main__":
    unittest.main()
