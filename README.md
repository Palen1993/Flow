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

---

## 🎮 Tabla de Controles de Mando

| Botón Xbox | Botón PlayStation | Acción en Pantalla Principal (Big Picture) | Acción en In-Game Overlay / Diálogos |
| :---: | :---: | :--- | :--- |
| **D-Pad ← / →** | **Cruceta ← / →** | Desplazar carátulas del Cover Flow | Ajustar Volumen / Navegar campos |
| **D-Pad ↑ / ↓** | **Cruceta ↑ / ↓** | Selector de monitores / Menú | Seleccionar opción (Reanudar / Lanzador / Salir) |
| **A** | **Cruz** | **Iniciar juego seleccionado** | Confirmar / Ejecutar acción seleccionada |
| **B** | **Círculo** | Volver al modo Mini transparente | Cancelar / Salir / Reanudar juego |
| **X** | **Cuadrado** | Abrir menú de opciones | Abrir teclado OSD / Marcar todo |
| **Y** | **Triángulo** | Confirmar salida del lanzador | **Silenciar / Activar sonido (Mute)** / Carpeta Juegos |
| **LB / RB** | **L1 / R1** | **Cambiar Colección / Filtro** | **Bajar / Subir Volumen Maestro** (-5% / +5%) |
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

```text
GameFlow/
├── assets/                 # Iconos vectoriales y efectos de sonido acústicos
├── core/
│   ├── active_game_tracker.py # Rastreo de juegos activos para In-Game Overlay
│   ├── audio_service.py    # Control de volumen maestro nativo COM / ctypes / keybd_event
│   ├── config.py           # Persistencia atómica de configuración
│   ├── cover_downloader.py # Búsqueda y filtrado estricto de carátulas/wallpapers HD
│   ├── cover_resolver.py   # Extracción de iconos de ejecutables Win32
│   ├── coverflow_engine.py # Motor matemático 3D, estuches de cristal y perspectiva
│   ├── execution_service.py# Lanzamiento y centinela de procesos desacoplado
│   ├── external_launchers.py# Parsers de Steam, Epic Games, GOG y ROMs
│   ├── library_service.py  # Gestión atómica y caché lazy-loading de games.json
│   └── platform_layer.py   # Capa de abstracción y mocks multiplataforma Windows/Linux/CI
├── ui/
│   ├── dialogs/            # Diálogos Glassmorphism (InGameOverlay, Options, Scraper, etc.)
│   ├── controller_hud.py   # Glifos dinámicos vectoriales Xbox / PlayStation
│   ├── coverflow_canvas.py # Lienzo interactivo Cover Flow con reflejos y sombras
│   ├── display_scale.py    # Escalado dinámico multi-pantalla y High-DPI
│   ├── gamepad_service.py  # Bucle de despacho y navegación a 40 Hz
│   ├── theme.py            # Paleta de colores iOS Liquid Glass y Win32 helper
│   └── window_manager.py   # Gestión de modo Big Picture y Mini Dock transparente
├── app.py                  # Ventana principal y despachador de eventos inter-hilo
├── gamepad_watcher.pyw     # Centinela de fondo para botón Guía y atajos de mando
├── lanzador.py             # Punto de entrada de la aplicación
├── overlay.py              # Lanzador standalone del In-Game Overlay
└── requirements.txt        # Dependencias de producción
```

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.

---

<div align="center">
  <sub>Desarrollado con ❤️ para jugadores de PC que disfrutan de su biblioteca tanto en escritorio como en la televisión del salón.</sub>
</div>
