import ctypes
from ctypes import wintypes
import sys

# Windows Constants
DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = -1

class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8)
    ]

class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_size_t)
    ]

class HIDD_ATTRIBUTES(ctypes.Structure):
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

def scan_sony_controllers():
    hid = ctypes.windll.hid
    setupapi = ctypes.windll.setupapi
    kernel32 = ctypes.windll.kernel32

    hid_guid = GUID()
    hid.HidD_GetHidGuid(ctypes.byref(hid_guid))

    h_dev_info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(hid_guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE
    )
    if h_dev_info == INVALID_HANDLE_VALUE:
        return []

    devices_found = []
    index = 0
    dev_interface_data = SP_DEVICE_INTERFACE_DATA()
    dev_interface_data.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)

    while setupapi.SetupDiEnumDeviceInterfaces(
        h_dev_info, None, ctypes.byref(hid_guid), index, ctypes.byref(dev_interface_data)
    ):
        index += 1
        required_size = wintypes.DWORD()
        setupapi.SetupDiGetDeviceInterfaceDetailW(
            h_dev_info, ctypes.byref(dev_interface_data), None, 0, ctypes.byref(required_size), None
        )
        if required_size.value == 0:
            continue

        detail_buffer = ctypes.create_string_buffer(required_size.value)
        # On Windows x64: cbSize is 8 bytes; on x86: 5 or 6 bytes
        ctypes.cast(detail_buffer, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 5

        if setupapi.SetupDiGetDeviceInterfaceDetailW(
            h_dev_info, ctypes.byref(dev_interface_data), detail_buffer, required_size.value, None, None
        ):
            device_path = ctypes.wstring_at(ctypes.addressof(detail_buffer) + 4)
            h_file = kernel32.CreateFileW(
                device_path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                None, OPEN_EXISTING, 0, None
            )
            if h_file != INVALID_HANDLE_VALUE:
                try:
                    attrs = HIDD_ATTRIBUTES()
                    attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
                    if hid.HidD_GetAttributes(h_file, ctypes.byref(attrs)):
                        vid = attrs.VendorID
                        pid = attrs.ProductID
                        if vid == SONY_VID and pid in SONY_PIDS:
                            devices_found.append({
                                "path": device_path,
                                "name": SONY_PIDS[pid],
                                "pid": pid,
                                "handle": h_file
                            })
                            continue
                except Exception:
                    pass
                kernel32.CloseHandle(h_file)

    setupapi.SetupDiDestroyDeviceInfoList(h_dev_info)
    return devices_found

print("Scanning for connected Sony PlayStation controllers...")
found = scan_sony_controllers()
print(f"Found {len(found)} Sony controller(s):")
for d in found:
    print(f" - {d['name']} (PID: 0x{d['pid']:04X})")
    ctypes.windll.kernel32.CloseHandle(d["handle"])
