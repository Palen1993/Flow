"""
Subsistema nativo Windows HID (hid.dll / setupapi.dll) para mandos Sony PlayStation
(DualSense PS5, DualSense Edge y DualShock 4 PS4 por USB y Bluetooth).
Extrae el porcentaje real de batería y estado de carga sin requerir permisos exclusivos.
"""
import time
import ctypes
from ctypes import wintypes
from typing import Dict, Any, Optional, Tuple

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]


class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", _GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t)
    ]


class _HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT)
    ]


SONY_VID = 0x054C
SONY_PIDS = {
    0x0CE6: "DualSense Wireless Controller (PS5)",
    0x0DF2: "DualSense Edge Controller (PS5)",
    0x05C4: "DualShock 4 Controller (PS4 v1)",
    0x09CC: "DualShock 4 Controller (PS4 v2)",
    0x0BA0: "DualShock 4 USB Wireless Adapter"
}

_PS_BATTERY_CACHE: Dict[int, Tuple[float, Optional[Dict[str, Any]]]] = {}
_PS_CACHE_TTL_S = 1.5


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


def _query_sony_hid_battery(sony_index: int = 0) -> Optional[Dict[str, Any]]:
    """
    Sondea directamente vía Windows HID (hid.dll y setupapi.dll) los mandos Sony conectados
    para extraer el nivel de batería real y el estado de carga (⚡).
    """
    try:
        hid = ctypes.windll.hid
        setupapi = ctypes.windll.setupapi
        kernel32 = ctypes.windll.kernel32

        hid_guid = _GUID()
        hid.HidD_GetHidGuid(ctypes.byref(hid_guid))

        h_dev_info = setupapi.SetupDiGetClassDevsW(
            ctypes.byref(hid_guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
        )
        if h_dev_info == -1 or h_dev_info == 0xFFFFFFFFFFFFFFFF:
            return None

        dev_interface_data = _SP_DEVICE_INTERFACE_DATA()
        dev_interface_data.cbSize = ctypes.sizeof(_SP_DEVICE_INTERFACE_DATA)

        sony_controllers_seen = []
        current_index = 0

        while setupapi.SetupDiEnumDeviceInterfaces(
            h_dev_info, None, ctypes.byref(hid_guid), current_index, ctypes.byref(dev_interface_data)
        ):
            current_index += 1
            req_size = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(
                h_dev_info, ctypes.byref(dev_interface_data), None, 0, ctypes.byref(req_size), None
            )
            if req_size.value == 0:
                continue

            detail_buf = ctypes.create_string_buffer(req_size.value)
            cb_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 5
            ctypes.cast(detail_buf, ctypes.POINTER(wintypes.DWORD))[0] = cb_size

            if setupapi.SetupDiGetDeviceInterfaceDetailW(
                h_dev_info, ctypes.byref(dev_interface_data), detail_buf, req_size.value, None, None
            ):
                device_path = ctypes.wstring_at(ctypes.addressof(detail_buf) + 4)
                path_up = device_path.upper()
                if "VID_054C" not in path_up and "054C" not in path_up:
                    continue

                # Abrir sin requerir permisos exclusivos
                h_file = kernel32.CreateFileW(
                    device_path, 0, 0x00000001 | 0x00000002, None, 3, 0, None
                )
                if h_file == -1 or h_file == 0xFFFFFFFFFFFFFFFF:
                    h_file = kernel32.CreateFileW(
                        device_path, 0x80000000, 0x00000001 | 0x00000002, None, 3, 0, None
                    )
                if h_file == -1 or h_file == 0xFFFFFFFFFFFFFFFF:
                    continue

                try:
                    attrs = _HIDD_ATTRIBUTES()
                    attrs.Size = ctypes.sizeof(_HIDD_ATTRIBUTES)
                    if hid.HidD_GetAttributes(h_file, ctypes.byref(attrs)):
                        vid = attrs.VendorID
                        pid = attrs.ProductID
                        if vid == SONY_VID and pid in SONY_PIDS:
                            base_id = path_up.split("&COL")[0]
                            if base_id not in sony_controllers_seen:
                                sony_controllers_seen.append(base_id)

                            controller_order = len(sony_controllers_seen) - 1
                            if controller_order == sony_index:
                                is_ds = (pid in (0x0CE6, 0x0DF2))
                                res = None
                                if is_ds:
                                    buf = ctypes.create_string_buffer(78)
                                    buf[0] = 0x31
                                    if hid.HidD_GetInputReport(h_file, buf, 78):
                                        res = decode_playstation_hid_report(pid, bytes(buf.raw[:78]))
                                    if not res:
                                        buf = ctypes.create_string_buffer(64)
                                        buf[0] = 0x01
                                        if hid.HidD_GetInputReport(h_file, buf, 64):
                                            res = decode_playstation_hid_report(pid, bytes(buf.raw[:64]))
                                else:
                                    buf = ctypes.create_string_buffer(78)
                                    buf[0] = 0x11
                                    if hid.HidD_GetInputReport(h_file, buf, 78):
                                        res = decode_playstation_hid_report(pid, bytes(buf.raw[:78]))
                                    if not res:
                                        buf = ctypes.create_string_buffer(64)
                                        buf[0] = 0x01
                                        if hid.HidD_GetInputReport(h_file, buf, 64):
                                            res = decode_playstation_hid_report(pid, bytes(buf.raw[:64]))

                                if res is not None:
                                    kernel32.CloseHandle(h_file)
                                    setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)
                                    return res
                except Exception:
                    pass
                finally:
                    kernel32.CloseHandle(h_file)

        setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)
    except Exception:
        pass
    return None


def _get_playstation_hid_battery(sony_index: int = 0) -> Optional[Dict[str, Any]]:
    """Consulta la batería de un mando PlayStation con caché de 1.5s para 0 saturación del bus USB/Bluetooth."""
    global _PS_BATTERY_CACHE
    now = time.monotonic()
    cached = _PS_BATTERY_CACHE.get(sony_index)
    if cached is not None:
        cache_time, cache_val = cached
        if now - cache_time < _PS_CACHE_TTL_S:
            return cache_val
    val = _query_sony_hid_battery(sony_index)
    _PS_BATTERY_CACHE[sony_index] = (now, val)
    return val
