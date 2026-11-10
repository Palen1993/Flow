"""
Servicio de Control de Volumen Maestro para GameFlow.

Proporciona lectura y ajuste en tiempo real del volumen del sistema (0 a 100%) y estado de silencio (mute),
compatible con mandos de consola (D-pad izquierda/derecha o botones superiores LB/RB).
En Windows utiliza las interfaces nativas de Windows Core Audio (IAudioEndpointVolume) mediante ctypes
con respaldo por teclado virtual (VK_VOLUME_UP/DOWN) y stubs seguros para entornos Linux / CI.
"""

import sys
import ctypes
from typing import Tuple, Optional
from core.platform_layer import is_windows

# ---------------------------------------------------------------------------
# Constantes y Shims de Windows
# ---------------------------------------------------------------------------

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002

_simulated_volume: int = 70
_simulated_muted: bool = False

# Caché del puntero de interfaz para evitar llamadas repetidas a CoCreateInstance
_endpoint_volume_ptr = None
_com_initialized = False


def _init_windows_endpoint_volume():
    """Inicializa la interfaz COM IAudioEndpointVolume de Windows Core Audio mediante ctypes puro."""
    global _endpoint_volume_ptr, _com_initialized
    if not is_windows():
        return None

    if _endpoint_volume_ptr is not None:
        return _endpoint_volume_ptr

    windll = getattr(ctypes, "windll", None)
    if not windll or not hasattr(windll, "ole32"):
        return None

    try:
        from ctypes import wintypes, Structure, POINTER, c_float, c_long, c_void_p, byref

        class GUID(Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8),
            ]

            def __init__(self, d1, d2, d3, d4_list):
                super().__init__()
                self.Data1 = d1
                self.Data2 = d2
                self.Data3 = d3
                for i, b in enumerate(d4_list):
                    self.Data4[i] = b

        if not _com_initialized:
            # 0x0 = COINIT_APARTMENTTHREADED, 0x2 = COINIT_MULTITHREADED
            windll.ole32.CoInitialize(None)
            _com_initialized = True

        # CLSIDs e IIDs de Core Audio
        CLSID_MMDeviceEnumerator = GUID(0xBCDE0395, 0xE52F, 0x467C, [0x8D, 0x3D, 0xC4, 0x57, 0x92, 0x91, 0x69, 0x2E])
        IID_IMMDeviceEnumerator = GUID(0xA95664D2, 0x9614, 0x4F35, [0xA7, 0x46, 0xDE, 0x8D, 0xB6, 0x36, 0x17, 0xE6])
        IID_IAudioEndpointVolume = GUID(0x5BC64874, 0x38B4, 0x4B22, [0x88, 0xA7, 0x26, 0xE5, 0xD7, 0x72, 0x4E, 0x00])

        enumerator = c_void_p()
        CLSCTX_ALL = 23
        hr = windll.ole32.CoCreateInstance(
            byref(CLSID_MMDeviceEnumerator),
            None,
            CLSCTX_ALL,
            byref(IID_IMMDeviceEnumerator),
            byref(enumerator)
        )
        if hr != 0 or not enumerator.value:
            return None

        # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender=0, eMultimedia=1, &pDevice)
        # vtable[4]
        enum_vtable = ctypes.cast(
            ctypes.cast(enumerator, POINTER(c_void_p)).contents,
            POINTER(c_void_p)
        )
        get_default_endpoint_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, c_long, c_long, POINTER(c_void_p))
        get_default_endpoint = get_default_endpoint_proto(enum_vtable[4])

        device = c_void_p()
        hr = get_default_endpoint(enumerator, 0, 1, byref(device))
        if hr != 0 or not device.value:
            return None

        # IMMDevice::Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, NULL, &pEndpointVolume)
        # vtable[3]
        dev_vtable = ctypes.cast(
            ctypes.cast(device, POINTER(c_void_p)).contents,
            POINTER(c_void_p)
        )
        activate_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))
        activate = activate_proto(dev_vtable[3])

        endpoint_vol = c_void_p()
        hr = activate(device, byref(IID_IAudioEndpointVolume), CLSCTX_ALL, None, byref(endpoint_vol))
        if hr == 0 and endpoint_vol.value:
            _endpoint_volume_ptr = endpoint_vol
            return _endpoint_volume_ptr
    except Exception:
        pass
    return None


def get_master_volume() -> Tuple[int, bool]:
    """
    Retorna (volumen_porcentaje, silenciado).
    volumen_porcentaje: int entre 0 y 100
    silenciado: bool indicando si el mute está activo
    """
    global _simulated_volume, _simulated_muted
    if not is_windows():
        return _simulated_volume, _simulated_muted

    ep_vol = _init_windows_endpoint_volume()
    if ep_vol:
        try:
            from ctypes import c_void_p, POINTER, c_float, c_long, byref
            from ctypes import wintypes
            vol_vtable = ctypes.cast(
                ctypes.cast(ep_vol, POINTER(c_void_p)).contents,
                POINTER(c_void_p)
            )

            # IAudioEndpointVolume::GetMasterVolumeLevelScalar(float* pfLevel) -> vtable[9]
            get_scalar_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(c_float))
            get_scalar = get_scalar_proto(vol_vtable[9])
            cur_scalar = c_float(0.0)
            hr = get_scalar(ep_vol, byref(cur_scalar))

            # IAudioEndpointVolume::GetMute(BOOL* pbMute) -> vtable[14]
            get_mute_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(wintypes.BOOL))
            get_mute = get_mute_proto(vol_vtable[14])
            cur_mute = wintypes.BOOL(False)
            get_mute(ep_vol, byref(cur_mute))

            if hr == 0:
                pct = max(0, min(100, int(round(cur_scalar.value * 100.0))))
                _simulated_volume = pct
                _simulated_muted = bool(cur_mute.value)
                return pct, bool(cur_mute.value)
        except Exception:
            pass

    return _simulated_volume, _simulated_muted


def set_master_volume(level: int) -> int:
    """
    Establece el volumen maestro del sistema a un valor absoluto entre 0 y 100.
    Devuelve el nivel resultante alcanzado.
    """
    global _simulated_volume, _simulated_muted
    target_level = max(0, min(100, int(level)))
    _simulated_volume = target_level

    if not is_windows():
        return target_level

    ep_vol = _init_windows_endpoint_volume()
    if ep_vol:
        try:
            from ctypes import c_void_p, POINTER, c_float, c_long, byref
            vol_vtable = ctypes.cast(
                ctypes.cast(ep_vol, POINTER(c_void_p)).contents,
                POINTER(c_void_p)
            )

            # IAudioEndpointVolume::SetMasterVolumeLevelScalar(float fLevel, GUID* pEventContext) -> vtable[7]
            set_scalar_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, c_float, c_void_p)
            set_scalar = set_scalar_proto(vol_vtable[7])
            scalar_val = c_float(target_level / 100.0)
            hr = set_scalar(ep_vol, scalar_val, None)
            if hr == 0:
                return target_level
        except Exception:
            pass

    # Respaldo mediante keybd_event si IAudioEndpointVolume no responde
    windll = getattr(ctypes, "windll", None)
    if windll and hasattr(windll, "user32"):
        try:
            cur, _ = get_master_volume()
            steps = int(abs(target_level - cur) / 2)
            vk = VK_VOLUME_UP if target_level > cur else VK_VOLUME_DOWN
            for _ in range(steps):
                windll.user32.keybd_event(vk, 0, 0, 0)
                windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        except Exception:
            pass

    return target_level


def change_master_volume(delta: int) -> int:
    """Incrementa o decrementa el volumen maestro en un paso relativo (ej: +5 o -5)."""
    cur, _ = get_master_volume()
    return set_master_volume(cur + delta)


def toggle_mute() -> bool:
    """Alterna el estado de silencio (Mute) del sistema. Devuelve el nuevo estado."""
    global _simulated_muted
    if not is_windows():
        _simulated_muted = not _simulated_muted
        return _simulated_muted

    ep_vol = _init_windows_endpoint_volume()
    if ep_vol:
        try:
            from ctypes import c_void_p, POINTER, c_long, byref
            from ctypes import wintypes
            vol_vtable = ctypes.cast(
                ctypes.cast(ep_vol, POINTER(c_void_p)).contents,
                POINTER(c_void_p)
            )

            get_mute_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, POINTER(wintypes.BOOL))
            get_mute = get_mute_proto(vol_vtable[14])
            cur_mute = wintypes.BOOL(False)
            get_mute(ep_vol, byref(cur_mute))

            new_mute = not bool(cur_mute.value)
            set_mute_proto = ctypes.WINFUNCTYPE(c_long, c_void_p, wintypes.BOOL, c_void_p)
            set_mute = set_mute_proto(vol_vtable[13])
            hr = set_mute(ep_vol, wintypes.BOOL(new_mute), None)
            if hr == 0:
                _simulated_muted = new_mute
                return new_mute
        except Exception:
            pass

    # Respaldo con tecla multimedia Mute
    windll = getattr(ctypes, "windll", None)
    if windll and hasattr(windll, "user32"):
        try:
            windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
            windll.user32.keybd_event(VK_VOLUME_MUTE, 0, KEYEVENTF_KEYUP, 0)
            _simulated_muted = not _simulated_muted
            return _simulated_muted
        except Exception:
            pass

    _simulated_muted = not _simulated_muted
    return _simulated_muted
