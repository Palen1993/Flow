# GameFlow Launcher 🎮✨

<div align="center">

![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078d7.svg?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab.svg?style=for-the-badge&logo=python)
![UI Framework](https://img.shields.io/badge/UI-CustomTkinter%20%2B%20Pillow-1f2937.svg?style=for-the-badge)
![Gamepad](https://img.shields.io/badge/Gamepad-Console--Grade%2040Hz-10b981.svg?style=for-the-badge&logo=xbox)
![License](https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge)

<p align="center">
  <b>Un lanzador de videojuegos portable de diseño premium para Windows, con navegación 3D estilo Cover Flow, control 100% por mando desde el sofá, escalado dinámico High-DPI y fondos ambientales inmersivos.</b>
</p>

[⬇️ Descargar Última Versión Portable (.zip)](https://github.com/Palen1993/Flow/releases/latest) • [Ver Registro de Cambios](#-características-principales) • [Controles](#-tabla-de-controles-de-mando)

</div>

---

## 🌟 Características Principales

### 💿 1. Vista Cover Flow 3D Fluida
* Motor de proyección en perspectiva acelerado en CPU con **Pillow** y renderizado por **CustomTkinter/Canvas**.
* Estuches de cristal cuadradas de alta fidelidad (*Jewel Case*) con reflejos en tiempo real y física de inercia suave (`1 - exp(-k * dt)`).
* Fondos de pantalla dinámicos en formato 16:9 con opacidad y desenfoque gaussiano ambiental configurable juego a juego.

### 🎮 2. Navegación por Mando Console-Grade (40 Hz)
* Compatible de forma nativa con mandos de **Xbox (XInput)**, **PlayStation (DualSense PS5 y DualShock 4 por HID)** y genéricos (DirectInput/WinMM).
* **Operable al 100% sin ratón ni teclado:** toda la aplicación (menús, exploradores de carpetas, editores de metadatos, teclado en pantalla) está adaptada a mando.
* Glifos de mando contextuales que se adaptan automáticamente a la familia conectada (`A/B/X/Y` para Xbox o `Cruz/Círculo/Cuadrado/Triángulo` para PlayStation).
* Detección de nivel de batería en tiempo real en el HUD superior.

### 📺 3. Adaptabilidad Dinámica de Resolución (720p hasta 4K)
* Arquitectura matemática desacoplada (`ui/display_scale.py`) que detecta el área de trabajo y DPI de la pantalla en tiempo real.
* **Cero desbordamientos en consolas portátiles (Steam Deck / ROG Ally / 720p)** y tipografías y botones legibles a 3 metros de distancia en **televisores 4K a 200% DPI**.

### 🖼️ 4. Selector Inteligente de Carátulas y Wallpapers HD
* Motor de búsqueda multiproveedor concurrente en **Steam Store**, **GOG Catalog**, **SteamGridDB** y **Web**.
* Filtro de relevancia estricto que descarta juguetes físicos y juegos homónimos, trayendo únicamente arte oficial y wallpapers 1080p HD.
* Editor de encuadre en vivo para recortar o adaptar arte apaisado al estuche cuadrado con vista previa interactiva.

### 🚀 5. Importador Universal de Juegos
* Detección automática en un clic de juegos instalados en:
  * **Steam**
  * **Epic Games Store**
  * **GOG Galaxy**
  * **Carpetas locales de PC** (ej. `D:\Juegos`)
  * **ROMs de emuladores** (RetroArch, PCSX2, etc.)
* Modo de ejecución prioritario en Windows y centinela de procesos en segundo plano.

### 🏷️ 6. Sistema de Colecciones y Filtros Instantáneos (LB / RB)
* Navegación fluida entre colecciones pulsando los botones superiores **LB / RB** (o **L1 / R1** en PlayStation) o teclas **Q / E**:
  * **Todos**: Catálogo completo unificado.
  * **⭐ Favoritos**: Acceso directo a tus títulos predilectos (alternable con `F` o menú de opciones).
  * **Por Estado**: Clasificación en *Por jugar*, *Jugando*, *Completados* y *Abandonados*.
  * **Por Plataforma**: Detección de fuentes (*Steam*, *Epic Games*, *GOG*, *PC*, emuladores...).
  * **Por Género**: Filtro por categoría (*Acción*, *RPG*, *Aventura*, *Estrategia*, etc.).
* Píldora HUD superior izquierda en estilo Glassmorphism con indicador interactivo de colección, conteo de títulos y glifos adaptativos.
* Diálogo modal accesible desde el menú de opciones `(X)` para seleccionar directamente cualquier colección.

### 🪟 7. In-Game Gamepad Overlay (Botón Guía / Nexus / PS)
* Al pulsar el botón central **Xbox / Guía / PS** (o tecla `O` / `F1`) durante una partida en ejecución, se despliega instantáneamente un menú flotante Glassmorphism en primer plano absoluto:
  * **Reloj Digital y Fecha** en vivo en tiempo real.
  * **Nivel de Batería del Mando** con indicador dinámico de carga / cable USB y modelo de mando detectado.
  * **Control de Volumen Maestro del Sistema** ajustable directamente con la cruceta o gatillos superiores (`LB / RB`), y silencio rápido con `Y` / `Triángulo`.
  * **Acciones Rápidas con Mando**:
    * **▶️ Reanudar Partida** (devuelve el foco instantáneamente al juego activo).
    * **🏠 Volver a GameFlow** (restaura la ventana del lanzador).
    * **🛑 Cerrar Juego** (cierra el proceso del juego limpiamente registrando el tiempo de sesión).
* Totalmente autónomo: funciona tanto si GameFlow permanece minimizado como si se utiliza el modo de cierre tras lanzar juego (`overlay.py` + `gamepad_watcher.pyw`).

### ⏱️ 8. Estadísticas Avanzadas, Gráficas de Actividad y Metas Locales (S)
* Accesible con tecla **S** o desde el menú de opciones `(X)`:
  * **Métricas por Título**: Tiempo total acumulado, fecha de alta en la biblioteca, cantidad de veces iniciado, última sesión jugada (relativa y exacta) y promedio por partida.
  * **Gráfica de Actividad Semanal y Mensual**: Visualización estilo consola (Steam / Nintendo Switch) con barras proporcionales en Canvas High-DPI para los últimos 7 días o 30 días, alternable con la cruceta o botones `LB / RB`.
  * **Checklist de Metas y Logros Personales**: Lista interactiva para marcar tareas pendientes (ideal para RPGs y juegos de mundo abierto) con casillas `[✓]` / `[ ]`, barra de progreso porcentual, adición con teclado en pantalla OSD `(X)` y borrado `(Y)`.
  * **Guía y Notas del Juego**: Bloc de notas integrado para guardar códigos, combinaciones de puertas, builds de personajes o misiones secundarias.
* Persistencia atómica y fusión inteligente resistente a cierres o ejecuciones en segundo plano.

### 💾 9. Copias de Seguridad de Partidas Guardadas (Save Backup)
* Accesible con tecla **C**, atajo **Ctrl+B** o desde el menú de opciones `(X)`:
  * **Detección Automática de Carpetas de Guardado**: Escaneo inteligente de rutas estándar en Windows:
    * `%USERPROFILE%/Saved Games`
    * `%LOCALAPPDATA%` (incluyendo jerarquías Unreal Engine `Saved/SaveGames`)
    * `%APPDATA%` (Roaming) y `%USERPROFILE%/AppData/LocalLow` (motores Unity e indie)
    * `%USERPROFILE%/Documents/My Games` y `%USERPROFILE%/Documents`
    * Subcarpetas de guardado locales de la instalación (`saves/`, `SaveData/`, `userdata/`).
  * **Backups Automáticos y Manuales en .zip**:
    * Creación de copias comprimidas con fecha y hora (`<Juego>_Save_YYYYMMDD_HHMMSS.zip`) con `manifest.json` interno de metadatos.
    * Ejecución automática en segundo plano al terminar cada partida sin congelar la interfaz.
    * Política de retención automática (conserva las últimas 10 copias por juego).
  * **Restauración Segura con Protección Preventiva**:
    * Restaura cualquier punto anterior con un solo clic o pulsación de mando.
    * Genera automáticamente una copia de seguridad de protección (*pre-restore safety backup*) antes de sobrescribir archivos para garantizar que nunca pierdas datos.
  * **Selector de Carpeta Personalizada**: Posibilidad de indicar o cambiar la carpeta de guardado manualmente mediante el explorador OSD.

### 🎛️ 10. Perfiles de Rendimiento y Modos de Energía (Handheld Mode)
* Diseñado específicamente para consolas portátiles (**ASUS ROG Ally**, **Valve Steam Deck** con Windows, **Lenovo Legion Go**, **AYANEO**, **GPD Win**, **MSI Claw**, **OneXPlayer**) y portátiles gaming:
  * **3 Modos de Rendimiento y Energía**:
    * **🌱 Modo Batería (Eco)**: Plan Economizador (`~9W - 15W TDP`), maximiza la autonomía de batería para juegos 2D, emuladores retro y novelas visuales.
    * **⚖️ Modo Equilibrado**: Plan Equilibrado (`~15W - 20W TDP`), balance óptimo de temperatura, FPS y ventiladores.
    * **⚡ Modo Turbo (Rendimiento)**: Plan Alto Rendimiento (`~25W - 30W+ TDP`), libera toda la potencia de la APU CPU/GPU para títulos AAA exigentes.
  * **Cambio en Caliente sin Reinicios**: Modificación instantánea de planes de energía mediante `powercfg /setactive` sin necesidad de permisos de Administrador ni bloatware propietario de fondo.
  * **Perfiles Automáticos por Juego (Per-Game Profiles)**: Asigna un perfil preferido a cada título (`Por Defecto`, `Eco`, `Equilibrado`, `Turbo`). GameFlow lo aplica automáticamente al lanzar el juego y restaura tu perfil anterior al salir.
  * **In-Game Quick Toggle**: Alterna perfiles en plena partida pulsando **X** (o tecla **P**) dentro del In-Game Overlay tras pulsar el botón Guía/Nexus.
  * **Telemetría y Detección de Hardware**: Detección de la consola, nivel y estado de carga de la batería, tiempo restante estimado y telemetría de mando.

### ☁️ 11. Sincronización de Partidas en la Nube (Cloud Save Sync)
* Compatible con **Microsoft OneDrive**, **Google Drive**, **Dropbox**, **Carpetas Locales / NAS en red** y servidores **Nextcloud / WebDAV**:
  * **Sincronización Automática en Segundo Plano**: Al terminar una partida o crear un backup local, GameFlow sube de forma asíncrona la copia comprimida `.zip` sin congelar el juego ni la interfaz.
  * **Autodetección Inteligente de Proveedores**: Identifica automáticamente las rutas de instalación de OneDrive (`%USERPROFILE%\OneDrive`), Google Drive (`G:\My Drive`) y Dropbox en Windows.
  * **Soporte Nativo WebDAV (Nextcloud / ownCloud)**: Implementación 100% en biblioteca estándar de Python sin dependencias pesadas externas, con validación de tokens de aplicación y certificados.
  * **Sincronización Completa de la Biblioteca**: Botón "Sincronizar Toda la Biblioteca Ahora" para respaldar todos los títulos con un solo clic.
  * **Panel de Configuración y Diagnóstico**: Prueba de conexión en tiempo real con comprobación de permisos de escritura, indicadores visuales de copia sincronizada (`☁️ En la Nube`) y descarga directa de partidas remotas.

### 🏆 12. Logros y Trofeos (Steam API & RetroAchievements)
* Panel unificado de logros y trofeos accesible con tecla **Y** o desde el menú de opciones `(X)`:
  * **Integración Oficial con Steam**:
    * **Autodetección de Cuenta en Windows**: Localiza automáticamente el `SteamID64` y el perfil del usuario activo analizando `Steam/config/loginusers.vdf` y carpetas `userdata`.
    * **Extracción de Esquema y Progreso**: Muestra nombres, descripciones, estado de desbloqueo, fechas de obtención y rareza global (`💎 4.2% Muy Raro`) mediante Steam Web API o perfil público XML.
  * **Integración con RetroAchievements**:
    * Soporte para juegos retro y emuladores (NES, SNES, Genesis, PS1, PS2, N64, GBA, etc.).
    * Consulta en tiempo real de badges oficiales, puntuación RetroPoints / Hardcore y fechas de obtención.
  * **Fallback a Metas Locales**:
    * Para juegos independientes o sin conexión a APIs, las metas personales definidas en GameFlow actúan automáticamente como logros locales con medallas y puntuación.
  * **Caché Offline Inteligente**:
    * Almacena logros e iconos en disco (`achievements_cache.json`) para una navegación 100% instantánea y fluida sin latencia de red.
  * **Filtros Rápidos y Navegación por Mando**:
### 🗂️ 13. Navegación 2D por Estanterías Multi-Carrusel y Taxonomía Canónica
* **Navegación 2D Estilo Consola Moderna**:
  * **Eje Horizontal (`← / →`)**: Desplaza suavemente las carátulas 3D Cover Flow del canal o lista actual con efecto de reflejo e inercia.
  * **Eje Vertical (`↑ / ↓`)**: Cambia instantáneamente entre las diferentes estanterías y canales habilitados (Todos los Juegos, Favoritos, Recientes, Por Jugar, Plataformas, Géneros canónicos y Listas personalizadas).
  * **Memoria de Posición por Canal**: Al alternar de fila verticalmente, cada carrusel recuerda con precisión la carátula que estabas visualizando.
  * **Regla de Consistencia Dinámica**: Si solo hay una lista o estantería habilitada en la configuración, no baja ni sube a otro carrusel, manteniendo la interfaz limpia y minimalista.
* **Panel de Configuración de Estanterías y Filtros**:
  * Accesible haciendo clic en la cápsula superior izquierda o pulsando `LB / RB` / menú de filtros.
  * **Activación/Desactivación Selectiva**: Muestra u oculta canales con un solo toque (`[✓] Habilitada`).
  * **Reordenación Vertical**: Sube o baja la jerarquía de las filas con botones `▲ Subir` / `▼ Bajar` (o `LB / RB` en mando).
  * **Listas Personalizadas**: Crea colecciones a tu medida (ej: "Juegos Cooperativos", "GOTYs", "Indies Favoritos") con teclado en pantalla OSK.
* **Taxonomía Canónica de Géneros Normalizada**:
  * Clasificación inteligente y profesional que agrupa cualquier metadato o subgénero en 10 grandes categorías universales (Acción y Aventura, Rol (RPG), Plataformas y Metroidvania, Shooter y Disparos, Estrategia y Táctica, Simulación y Gestión, Carreras y Deportes, Lucha y Combate, Terror y Suspenso, Puzles y Casual).
  * Evita la proliferación caótica y redundante de etiquetas manteniendo una organización impecable.
* **Asignación de Juegos a Listas en Edición**:
  * En el diálogo de Añadir / Modificar juego (`AddEditGameDialog`), añade o quita fácilmente el título de cualquier colección personalizada.

### 📺 14. Modo Kiosco y Shell de Consola Dedicada en Windows
* Convierte cualquier PC, consola portátil (**ROG Ally, Steam Deck con Windows, Legion Go**) o bartop arcade en una **consola de videojuegos dedicada**:
  * **Shell de Consola en Windows (`HKCU\...\Winlogon\Shell`)**: Al encender o iniciar sesión, Windows arranca directamente GameFlow en pantalla completa sin cargar el escritorio, barra de tareas o procesos innecesarios de `explorer.exe`. No requiere permisos de Administrador.
  * **Inicio Automático con Windows (`Run`)**: Configuración con un solo toque para iniciar el lanzador automáticamente junto al sistema operativo.
  * **Failsafe y Respaldo de Seguridad**: Botón rápido para lanzar el explorador de Windows (`explorer.exe`) bajo demanda en cualquier momento, tanto desde el panel de Modo Kiosco como desde el diálogo de confirmación de salida (`ConfirmExitDialog`).

### 🕹️ 15. Soporte Universal de Emuladores y Lanzamiento de ROMs Retro
* **Catálogo Integral de 16 Plataformas Clásicas y Modernas**:
  * Super Nintendo (SNES), Nintendo (NES), Nintendo 64 (N64), GameCube, Wii, Game Boy / Color, Game Boy Advance (GBA), Nintendo DS (NDS), Nintendo 3DS, Nintendo Switch, PlayStation (PS1), PlayStation 2 (PS2), PlayStation Portable (PSP), PlayStation 3 (PS3), Sega Genesis / Mega Drive, Sega Dreamcast y Arcade (MAME / NeoGeo).
* **Detección Automática por Extensión y Desambiguación Heurística**:
  * Reconoce extensiones nativas (`.sfc`, `.nes`, `.gba`, `.n64`, `.rvz`, `.chd`, `.pbp`, `.cso`, etc.) y desambigua heurísticamente formatos compartidos (`.iso`, `.bin`, `.zip`) según la estructura de carpetas.
* **Limpieza Inteligente de Nombres de ROMs**:
  * Elimina automáticamente códigos de región, versiones y etiquetas de scene (ej: `'Super Mario World (USA) [!].sfc'` → `'Super Mario World'`).
* **Integración con Emuladores Populares y RetroArch**:
  * Detección automática y paso de argumentos optimizados para **RetroArch** (inyección de núcleos `.dll`), **Dolphin** (`-b -e`), **PCSX2** (`-nogui -fullscreen`), **DuckStation** (`-batch -fullscreen`), **PPSSPP**, **RPCS3**, **Snes9x**, **mGBA**, etc.
* **Escaneo Masivo de Carpetas de ROMs**:
  * En el importador de juegos, escanea carpetas enteras de ROMs asignando plataforma, género canónico y metadatos con un solo clic.

### ⚡ 16. Descarga y Scraper Automático de Fondos Panorámicos 16:9 (SteamGridDB Heroes)
* **Wallpapers de Alta Definición (1080p, 2K, 4K)**:
  * Integración con la API oficial y pública de **SteamGridDB** para obtener automáticamente los fondos panorámicos (*Heroes 16:9*) oficiales de cada título.
  * **Descarga Automática en 1 Clic**: Botón `⚡ Fondo 16:9 Auto` en el diálogo de edición para descargar y aplicar el arte ambiental panorámico al instante sin búsquedas manuales.
  * **Descarga Masiva en Lote (`BatchSteamGridDBDialog`)**: Actualiza todas las carátulas verticales 3D y fondos panorámicos de toda tu colección a la vez.

---

## 🎮 Tabla de Controles de Mando

| Botón Xbox | Botón PlayStation | Acción en Pantalla Principal (Big Picture) | Acción en In-Game Overlay / Diálogos |
| :---: | :---: | :--- | :--- |
| **D-Pad ← / →** | **Cruceta ← / →** | Desplazar carátulas del Cover Flow actual | Ajustar Volumen / Navegar tarjetas de perfil |
| **D-Pad ↑ / ↓** | **Cruceta ↑ / ↓** | **Navegar verticalmente entre carruseles / estanterías (↑ / ↓)** | Seleccionar opción / Reordenar estanterías |
| **A** | **Cruz** | **Iniciar juego seleccionado** | Confirmar / Activar / Alternar estantería |
| **B** | **Círculo** | Volver al modo Mini transparente | Cancelar / Salir / Reanudar juego |
| **X** | **Cuadrado** | Abrir menú de opciones | **Cambiar Perfil de Rendimiento / Nueva Lista** |
| **Y** | **Triángulo** | **Abrir Logros y Trofeos (Steam / Retro)** | **Silenciar / Activar sonido (Mute)** / Carpeta Juegos |
| **LB / RB** | **L1 / R1** | **Cambiar Carrusel / Estantería** | **Subir / Bajar Posición en Estanterías** / Volumen (-5%/+5%) |
| **LT / RT** | **L2 / R2** | Salto alfabético rápido con HUD (A-Z) | Ajustar borrosidad / desenfoque |
| **Start** | **Options** | Alternar Pantalla Completa / Mini Dock | Seleccionar carpeta o guardar |
| **Select / Back** | **Share / Touchpad** | Minimizar a la bandeja del sistema | Alternar Carátula 3D vs Wallpaper 16:9 |
| **Guía / Xbox** | **PS Button** | Restaurar ventana del lanzador | **Abrir / Cerrar In-Game Overlay (en partida)** |

---

## 📦 Descarga y Ejecución

### Opción 1: Versión Portable Precompilada (Recomendada para usuarios)
No requiere tener Python instalado:
1. Descarga el archivo comprimido **`GameFlow_Launcher_Portable.zip`** desde la sección de [**Releases**](https://github.com/Palen1993/Flow/releases/latest).
2. Descomprímelo en cualquier carpeta o disco (por ejemplo `C:\Juegos\GameFlow` o en un pendrive).
3. Ejecuta **`GameFlow Launcher.exe`**.

### Opción 2: Ejecución desde Código Fuente (Para desarrolladores)
**Requisitos:** Windows 10 o Windows 11 y Python 3.11+ (compatible con 3.11 hasta 3.14).

```powershell
# 1. Clonar el repositorio
git clone https://github.com/Palen1993/Flow.git
cd Flow

# 2. Crear y activar el entorno virtual
python -m venv venv
.\venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Lanzar la aplicación
python lanzador.py
```

### Compilar tu propio ejecutable portable
```powershell
.\venv\Scripts\activate
python build.py
```
El ejecutable listo para usar se generará en `dist/GameFlow Launcher/` y el archivo comprimido en `dist/GameFlow_Launcher_Portable.zip`.

---

## 🏗️ Arquitectura del Proyecto

> **Guía Técnica y Contexto Rápido (IA / Desarrolladores):** Consulta [**`WALKTHROUGH.md`**](WALKTHROUGH.md) para ver el mapa completo de módulos, flujos de datos, invariantes técnicas, comandos de build/test y el historial vivo de cambios y arreglos.

```text
GameFlow/
├── assets/                 # Iconos vectoriales y efectos de sonido acústicos
├── core/
│   ├── achievements_service.py # Logros y trofeos (Steam API & RetroAchievements)
│   ├── active_game_tracker.py # Rastreo de juegos activos para In-Game Overlay
│   ├── audio_service.py    # Control de volumen maestro nativo COM / ctypes / keybd_event
│   ├── cloud_sync_service.py # Sincronización en la nube (OneDrive, GDrive, Dropbox, WebDAV)
│   ├── config.py           # Persistencia atómica de configuración
│   ├── cover_downloader.py # Búsqueda y filtrado estricto de carátulas/wallpapers HD
│   ├── cover_resolver.py   # Extracción de iconos de ejecutables Win32
│   ├── coverflow_engine.py # Motor matemático 3D, estuches de cristal y perspectiva
│   ├── execution_service.py# Lanzamiento y centinela de procesos desacoplado
│   ├── external_launchers.py# Parsers de Steam, Epic Games, GOG y ROMs
│   ├── library_service.py  # Gestión atómica y caché lazy-loading de games.json
│   ├── platform_layer.py   # Capa de abstracción y mocks multiplataforma Windows/Linux/CI
│   ├── power_service.py    # Detección de consolas portátiles, telemetría de batería y perfiles de energía
│   ├── save_backup_service.py# Detección de carpetas de guardado, compresión zip y retención
│   └── stats_service.py    # Métricas de tiempo, agregaciones semanales/mensuales y metas
├── ui/
│   ├── dialogs/            # Diálogos Glassmorphism (Achievements, SaveBackup, CloudSync, GameStats, PerformanceProfile, etc.)
│   ├── controller_hud.py   # Glifos dinámicos vectoriales Xbox / PlayStation
│   ├── coverflow_canvas.py # Lienzo interactivo Cover Flow con reflejos y sombras
│   ├── display_scale.py    # Escalado dinámico multi-pantalla y High-DPI
│   ├── gamepad_service.py  # Bucle de despacho y navegación a 40 Hz
│   ├── theme.py            # Paleta de colores iOS Liquid Glass y Win32 helper
│   └── window_manager.py   # Gestión de modo Big Picture y Mini Dock transparente
├── tests/                  # Suite automatizada de pruebas unitarias, UI e integración
├── app.py                  # Ventana principal y despachador de eventos inter-hilo
├── gamepad_watcher.pyw     # Centinela de fondo para botón Guía y atajos de mando
├── lanzador.py             # Punto de entrada de la aplicación
├── overlay.py              # Lanzador standalone del In-Game Overlay
└── requirements.txt        # Dependencias de producción
```

### Ejecutar la Suite de Pruebas
```powershell
python tests/run_all_tests.py
```

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

<div align="center">
  <sub>Desarrollado con ❤️ para jugadores de PC que disfrutan de su biblioteca tanto en escritorio como en la televisión del salón.</sub>
</div>
