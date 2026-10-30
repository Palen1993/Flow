"""Prueba de la lógica principal/secundario simulando dispositivos."""
import gamepad_manager as gm

conn = {}  # dev -> state

def fake_read(dev):
    return conn.get(dev)

gm._read_device = fake_read
gm._read_xinput_slot = lambda s: conn.get(("xinput", s))
gm._read_winmm_dev = lambda d: conn.get(("winmm", d))
gm._enumerate_connected = lambda t="any": [d for d in [("xinput", 0), ("xinput", 1), ("winmm", 0)] if d in conn]
gm.ENUM_INTERVAL_S = 0.0
gm.PRIMARY_GRACE_S = 0.0

S = lambda a=False: dict(gm._EMPTY_STATE, a=a)

# 1. Conecta primero un PlayStation (winmm 0)
conn[("winmm", 0)] = S()
ok, name, st = gm.poll_active_gamepad("any")
assert ok and gm.get_primary_controller() == ("winmm", 0), gm.get_primary_controller()
# 2. Conecta después un Xbox en ranura 0 (ranura más baja) -> NO debe robar el control
conn[("xinput", 0)] = S(a=True)
ok, name, st = gm.poll_active_gamepad("any")
assert gm.get_primary_controller() == ("winmm", 0), "El secundario robó el control"
assert st["a"] is False, "Pulsación del secundario filtrada al principal"
assert gm.get_connected_controller_family() == "playstation"
pads = gm.get_all_gamepads_info()
assert [p["role"] for p in pads] == ["principal", "secundario"], pads
assert pads[1]["device"] == ("xinput", 0)
bat = gm.get_gamepad_battery_info()
assert bat["secondary"] and bat["secondary"]["device"] == ("xinput", 0)
# 3. Se desconecta el principal -> el secundario asciende
del conn[("winmm", 0)]
gm.poll_active_gamepad("any")  # agota gracia
ok, name, st = gm.poll_active_gamepad("any")
assert ok and gm.get_primary_controller() == ("xinput", 0), gm.get_primary_controller()
assert st["a"] is True
# 4. Vuelve el PlayStation -> ahora es secundario
conn[("winmm", 0)] = S(a=True)
ok, name, st = gm.poll_active_gamepad("any")
assert gm.get_primary_controller() == ("xinput", 0)
assert [p["device"] for p in gm.get_all_gamepads_info()] == [("xinput", 0), ("winmm", 0)]
print("OK: principal fijo, secundario solo lectura, promoción al desconectar")
