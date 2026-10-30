import os

system_path = "core/system.py"
with open(system_path, "r", encoding="utf-8") as f:
    content = f.read()

target = """# Caché de nombres de monitor WMI para evitar lag de PowerShell (reduce llamadas de 1500ms a 0.2ms)
_WMI_MONITOR_MAP: Dict[str, str] = {}
_WMI_MAP_TIMESTAMP: float = 0.0

def get_monitors(force_refresh: bool = False) -> List[Dict[str, Any]]:
    \"\"\"
    Detecta todos los monitores activos obteniendo su resolución, posición y
    nombre de modelo amigable mediante emparejamiento exacto de ID de Hardware (EDID/WMI).
    Usa caché en memoria con TTL de 60 segundos para evitar llamadas costosas a PowerShell.
    \"\"\"
    global _WMI_MONITOR_MAP, _WMI_MAP_TIMESTAMP
    monitors = []
    wmi_map = _WMI_MONITOR_MAP

    now = time.time()
    if force_refresh or not _WMI_MONITOR_MAP or (now - _WMI_MAP_TIMESTAMP > 60.0):
        new_map = {}
        try:
            ps_script = (
                'Get-WmiObject -Namespace root\\\\wmi -Class WmiMonitorID | '
                'Select-Object InstanceName, @{Name="FriendlyName";Expression={[System.Text.Encoding]::ASCII.GetString($_.UserFriendlyName)}} | '
                'ConvertTo-Json'
            )
            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                if isinstance(data, dict):
                    data = [data]
                for item in data:
                    fname = item.get("FriendlyName", "").replace("\\u0000", "").strip()
                    inst = item.get("InstanceName", "").upper()
                    if fname:
                        new_map[inst] = fname
            if new_map:
                _WMI_MONITOR_MAP = new_map
                _WMI_MAP_TIMESTAMP = now
                wmi_map = new_map
        except Exception:
            pass

    for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        device_name = monitor_info['Device']
        rect = monitor_info['Monitor']
        is_primary = bool(monitor_info.get('Flags', 0) & 1)
        
        friendly_name = f"Monitor {i}"
        try:
            device = win32api.EnumDisplayDevices(device_name, 0, 0)
            dev_id = getattr(device, "DeviceID", "").upper()
            dev_string = getattr(device, "DeviceString", "")
            
            # Extraer token de hardware (ej: ACR053C, SAM0F14, LEN61BC)
            parts = dev_id.split('\\\\')
            hw_id = parts[1] if len(parts) > 1 else ''
            
            matched = False
            for inst, name in wmi_map.items():
                if hw_id and hw_id in inst:
                    friendly_name = name
                    matched = True
                    break
            if not matched and dev_string and dev_string.lower() != "generic pnp monitor":
                friendly_name = dev_string
        except Exception:
            pass
            
        display_name = f"{friendly_name} (Principal)" if is_primary else friendly_name
            
        monitors.append({
            "id": i,
            "device": device_name,
            "name": display_name,
            "raw_name": friendly_name,
            "is_primary": is_primary,
            "rect": rect  # (left, top, right, bottom)
        })
    return monitors"""

replacement = """def _read_edid_friendly_names_from_registry() -> Dict[str, str]:
    \"\"\"Lee el nombre comercial del monitor directamente desde los descriptores EDID en el Registro de Windows (<0.5ms).\"\"\"
    names = {}
    try:
        import winreg
        key_path = r"SYSTEM\\CurrentControlSet\\Enum\\DISPLAY"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root_key:
            count = winreg.QueryInfoKey(root_key)[0]
            for i in range(count):
                dev_id = winreg.EnumKey(root_key, i)
                try:
                    with winreg.OpenKey(root_key, dev_id) as dev_key:
                        inst_count = winreg.QueryInfoKey(dev_key)[0]
                        for j in range(inst_count):
                            inst_name = winreg.EnumKey(dev_key, j)
                            try:
                                with winreg.OpenKey(dev_key, f"{inst_name}\\\\Device Parameters") as dp_key:
                                    edid_val, _ = winreg.QueryValueEx(dp_key, "EDID")
                                    if isinstance(edid_val, (bytes, bytearray)) and len(edid_val) >= 128:
                                        for offset in (54, 72, 90, 108):
                                            if edid_val[offset:offset+3] == b"\\x00\\x00\\x00" and edid_val[offset+3] == 0xFC:
                                                raw_text = edid_val[offset+5:offset+18]
                                                name = raw_text.decode("latin1", errors="ignore").split("\\n")[0].strip()
                                                if name:
                                                    names[dev_id.upper()] = name
                                                    names[f"{dev_id}\\\\{inst_name}".upper()] = name
                                                    break
                            except Exception:
                                pass
                except Exception:
                    pass
    except Exception:
        pass
    return names

def _read_wmi_friendly_names_com() -> Dict[str, str]:
    \"\"\"Consulta WmiMonitorID en proceso mediante WMI COM (~10ms) sin lanzar subprocesos.\"\"\"
    names = {}
    try:
        import win32com.client
        wmi = win32com.client.GetObject(r"winmgmts:\\\\.\\root\\wmi")
        items = wmi.ExecQuery("SELECT InstanceName, UserFriendlyName FROM WmiMonitorID")
        for item in items:
            raw_name = getattr(item, "UserFriendlyName", None)
            inst = getattr(item, "InstanceName", "")
            if raw_name:
                fname = "".join(chr(c) for c in raw_name if c > 0).strip()
                if fname:
                    names[inst.upper()] = fname
                    parts = inst.split("\\\\")
                    if len(parts) > 1:
                        names[parts[1].upper()] = fname
    except Exception:
        pass
    return names

def _read_wmi_friendly_names_powershell() -> Dict[str, str]:
    \"\"\"Respaldo de último recurso mediante subproceso de PowerShell si COM y Registro están restringidos.\"\"\"
    names = {}
    try:
        ps_script = (
            'Get-WmiObject -Namespace root\\\\wmi -Class WmiMonitorID | '
            'Select-Object InstanceName, @{Name="FriendlyName";Expression={[System.Text.Encoding]::ASCII.GetString($_.UserFriendlyName)}} | '
            'ConvertTo-Json'
        )
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                data = [data]
            for item in data:
                fname = item.get("FriendlyName", "").replace("\\u0000", "").strip()
                inst = item.get("InstanceName", "").upper()
                if fname:
                    names[inst] = fname
                    parts = inst.split("\\\\")
                    if len(parts) > 1:
                        names[parts[1].upper()] = fname
    except Exception:
        pass
    return names

def _get_wmi_monitor_map() -> Dict[str, str]:
    \"\"\"Obtiene el mapa de modelos amigables mediante 3 niveles de defensa progresivos: Registro EDID -> WMI COM -> PowerShell.\"\"\"
    # Nivel 1: Registro directo EDID (<0.5ms)
    names = _read_edid_friendly_names_from_registry()
    if names:
        return names
    # Nivel 2: WMI COM en proceso (~10ms)
    names = _read_wmi_friendly_names_com()
    if names:
        return names
    # Nivel 3: Subproceso PowerShell (Respaldo de emergencia)
    return _read_wmi_friendly_names_powershell()

# Caché de nombres de monitor para evitar reconsultas redundantes
_WMI_MONITOR_MAP: Dict[str, str] = {}
_WMI_MAP_TIMESTAMP: float = 0.0

def get_monitors(force_refresh: bool = False) -> List[Dict[str, Any]]:
    \"\"\"
    Detecta todos los monitores activos obteniendo su resolución, posición y
    nombre de modelo amigable mediante emparejamiento exacto de ID de Hardware (EDID/WMI).
    Utiliza lectura ultrarrápida nativa (<2ms) eliminando la sobrecarga de subprocesos externos.
    \"\"\"
    global _WMI_MONITOR_MAP, _WMI_MAP_TIMESTAMP
    monitors = []
    wmi_map = _WMI_MONITOR_MAP

    now = time.time()
    if force_refresh or not _WMI_MONITOR_MAP or (now - _WMI_MAP_TIMESTAMP > 60.0):
        new_map = _get_wmi_monitor_map()
        if new_map:
            _WMI_MONITOR_MAP = new_map
            _WMI_MAP_TIMESTAMP = now
            wmi_map = new_map

    for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
        monitor_info = win32api.GetMonitorInfo(monitor[0])
        device_name = monitor_info['Device']
        rect = monitor_info['Monitor']
        is_primary = bool(monitor_info.get('Flags', 0) & 1)
        
        friendly_name = f"Monitor {i}"
        try:
            device = win32api.EnumDisplayDevices(device_name, 0, 0)
            dev_id = getattr(device, "DeviceID", "").upper()
            dev_string = getattr(device, "DeviceString", "")
            
            # Extraer token de hardware (ej: ACR053C, SAM0F14, LEN61BC)
            parts = dev_id.split('\\\\')
            hw_id = parts[1] if len(parts) > 1 else ''
            
            if hw_id in wmi_map:
                friendly_name = wmi_map[hw_id]
            else:
                matched = False
                for inst, name in wmi_map.items():
                    if hw_id and hw_id in inst:
                        friendly_name = name
                        matched = True
                        break
                if not matched and dev_string and dev_string.lower() != "generic pnp monitor":
                    friendly_name = dev_string
        except Exception:
            pass
            
        display_name = f"{friendly_name} (Principal)" if is_primary else friendly_name
            
        monitors.append({
            "id": i,
            "device": device_name,
            "name": display_name,
            "raw_name": friendly_name,
            "is_primary": is_primary,
            "rect": rect  # (left, top, right, bottom)
        })
    return monitors"""

assert target in content, "target block in core/system.py not found"
content = content.replace(target, replacement, 1)

with open(system_path, "w", encoding="utf-8") as f:
    f.write(content)

print("core/system.py successfully updated with native EDID/WMI enumeration!")
