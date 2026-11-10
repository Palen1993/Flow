"""
GameFlow - Servicio de Estadísticas de Juego Avanzadas y Metas Locales
======================================================================
Módulo encargado de:
- Calcular métricas de tiempo jugado, promedios, frecuencia de sesiones y fechas.
- Generar agregaciones de actividad diaria para gráficas semanales (7 días) y mensuales (30 días).
- Gestionar metas personales / checklist por juego (ej. misiones pendientes en RPGs).
- Gestionar notas y guías personalizadas asociadas a cada título.
- Persistencia atómica y fusión segura con games.json.
"""

import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

try:
    from core.logger import get_logger
    logger = get_logger("StatsService")
except Exception:
    import logging
    logger = logging.getLogger("GameFlow.StatsService")


# Nombres de días en español abreviados
DAYS_ES = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def format_playtime_minutes(minutes: int) -> str:
    """Formatea minutos en una cadena legible estilo consola (ej: '14h 25m', '45m' o '0m')."""
    mins = max(0, int(minutes or 0))
    if mins == 0:
        return "0 min"
    if mins < 60:
        return f"{mins} min"
    hours = mins // 60
    rem_mins = mins % 60
    if rem_mins == 0:
        return f"{hours}h"
    return f"{hours}h {rem_mins}m"


def format_relative_timestamp(date_str: Optional[str]) -> str:
    """
    Formatea una fecha 'YYYY-MM-DD HH:MM' o 'YYYY-MM-DD' en formato relativo amigable:
    'Hoy, 15:30', 'Ayer, 21:00', 'Hace 3 días', '12 de Octubre, 2026' o 'Nunca'.
    """
    if not date_str:
        return "Nunca"

    raw = str(date_str).strip()
    try:
        # Intentar parsear con hora
        if len(raw) >= 16 and " " in raw:
            dt = datetime.strptime(raw[:16], "%Y-%m-%d %H:%M")
            has_time = True
        else:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
            has_time = False
    except Exception:
        return raw

    now = datetime.now()
    diff = now.date() - dt.date()
    days = diff.days

    time_suffix = f", {dt.strftime('%H:%M')}" if has_time else ""

    if days == 0:
        return f"Hoy{time_suffix}"
    elif days == 1:
        return f"Ayer{time_suffix}"
    elif 2 <= days <= 6:
        return f"Hace {days} días{time_suffix}"
    elif 7 <= days <= 30:
        weeks = days // 7
        return f"Hace {weeks} sem.{time_suffix}"
    else:
        m_name = MONTHS_ES[dt.month - 1]
        return f"{dt.day} de {m_name}, {dt.year}"


def format_date_simple(date_str: Optional[str]) -> str:
    """Formatea una fecha en formato 'DD/MM/YYYY'."""
    if not date_str:
        return "Desconocida"
    try:
        dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return dt.strftime("%d/%m/%Y")
    except Exception:
        return str(date_str)[:10]


def get_game_stats(game: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula el conjunto completo de estadísticas y métricas para un juego dado.
    Devuelve un diccionario estructurado listo para ser consumido por la interfaz gráfica.
    """
    if not isinstance(game, dict):
        game = {}

    total_mins = int(game.get("playtime_minutes", 0) or 0)
    raw_play_count = int(game.get("play_count", 0) or 0)
    # Si tiene tiempo acumulado pero play_count era 0 (versión previa), inferir al menos 1
    play_count = raw_play_count if raw_play_count > 0 else (1 if total_mins > 0 else 0)

    last_played = game.get("last_played")
    date_added = game.get("date_added")
    if not date_added:
        # Intentar obtener fecha de creación del ejecutable si existe
        gpath = game.get("path", "")
        if gpath and os.path.exists(gpath):
            try:
                mtime = os.path.getmtime(gpath)
                date_added = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            except Exception:
                date_added = datetime.now().strftime("%Y-%m-%d")
        else:
            date_added = datetime.now().strftime("%Y-%m-%d")

    avg_mins = int(round(total_mins / play_count)) if play_count > 0 else 0

    daily_map = game.get("daily_playtime") or {}
    if not isinstance(daily_map, dict):
        daily_map = {}

    # Generar serie de los últimos 7 días (Semanal)
    weekly_activity: List[Dict[str, Any]] = []
    now = datetime.now()
    weekly_total = 0
    max_day_mins = 0
    max_day_info = {"day_label": "Ninguno", "minutes": 0, "date": ""}

    for i in range(6, -1, -1):
        d = now - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        mins = int(daily_map.get(d_str, 0) or 0)
        weekly_total += mins
        day_name = DAYS_ES[d.weekday()]
        label = f"{day_name} {d.day}"
        if mins > max_day_mins:
            max_day_mins = mins
            max_day_info = {"day_label": label, "minutes": mins, "date": d_str}

        weekly_activity.append({
            "date": d_str,
            "day_label": label,
            "weekday_num": d.weekday(),
            "minutes": mins,
            "hours_str": format_playtime_minutes(mins) if mins > 0 else "0m",
            "is_today": (i == 0)
        })

    # Generar serie de los últimos 30 días (Mensual)
    monthly_activity: List[Dict[str, Any]] = []
    monthly_total = 0
    for i in range(29, -1, -1):
        d = now - timedelta(days=i)
        d_str = d.strftime("%Y-%m-%d")
        mins = int(daily_map.get(d_str, 0) or 0)
        monthly_total += mins
        monthly_activity.append({
            "date": d_str,
            "day_label": f"{d.day:02d}/{d.month:02d}",
            "minutes": mins,
            "hours_str": format_playtime_minutes(mins) if mins > 0 else "0m",
            "is_today": (i == 0)
        })

    # Metas y checklist
    raw_goals = game.get("goals") or []
    if not isinstance(raw_goals, list):
        raw_goals = []
    
    clean_goals = []
    completed_count = 0
    for g in raw_goals:
        if isinstance(g, dict) and g.get("text"):
            comp = bool(g.get("completed", False))
            if comp:
                completed_count += 1
            clean_goals.append({
                "id": str(g.get("id") or uuid.uuid4().hex[:8]),
                "text": str(g.get("text", "")).strip(),
                "completed": comp,
                "created_at": str(g.get("created_at") or datetime.now().strftime("%Y-%m-%d"))
            })

    total_goals = len(clean_goals)
    completion_pct = int(round((completed_count / total_goals) * 100)) if total_goals > 0 else 0

    notes = str(game.get("notes") or "").strip()

    return {
        "name": game.get("name", "Juego"),
        "path": game.get("path", ""),
        "platform": game.get("platform", "PC"),
        "genre": game.get("genre", ""),
        "status": game.get("status", "Por jugar"),
        "favorite": bool(game.get("favorite", False)),
        "cover": game.get("cover"),
        "wallpaper": game.get("wallpaper"),
        "total_playtime_minutes": total_mins,
        "total_playtime_formatted": format_playtime_minutes(total_mins),
        "play_count": play_count,
        "last_played": last_played,
        "last_played_formatted": format_relative_timestamp(last_played),
        "date_added": date_added,
        "date_added_formatted": format_date_simple(date_added),
        "avg_session_minutes": avg_mins,
        "avg_session_formatted": f"{avg_mins} min / partida" if avg_mins > 0 else "0 min",
        "weekly_activity": weekly_activity,
        "weekly_total_minutes": weekly_total,
        "weekly_total_formatted": format_playtime_minutes(weekly_total),
        "monthly_activity": monthly_activity,
        "monthly_total_minutes": monthly_total,
        "monthly_total_formatted": format_playtime_minutes(monthly_total),
        "most_active_day": max_day_info,
        "goals": clean_goals,
        "goals_completed_count": completed_count,
        "goals_total_count": total_goals,
        "completion_percentage": completion_pct,
        "notes": notes
    }


def add_goal_to_game(game: Dict[str, Any], text: str) -> Optional[Dict[str, Any]]:
    """Añade una nueva meta al juego en memoria y devuelve el objeto creado."""
    text = (text or "").strip()
    if not text:
        return None

    if "goals" not in game or not isinstance(game["goals"], list):
        game["goals"] = []

    new_goal = {
        "id": uuid.uuid4().hex[:8],
        "text": text,
        "completed": False,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    game["goals"].append(new_goal)
    return new_goal


def toggle_game_goal(game: Dict[str, Any], goal_id: str) -> bool:
    """Alterna el estado completado de una meta por su ID. Devuelve True si se encontró."""
    goals = game.get("goals") or []
    for g in goals:
        if isinstance(g, dict) and g.get("id") == goal_id:
            g["completed"] = not bool(g.get("completed", False))
            return True
    return False


def delete_game_goal(game: Dict[str, Any], goal_id: str) -> bool:
    """Elimina una meta por su ID. Devuelve True si se eliminó."""
    goals = game.get("goals") or []
    initial_len = len(goals)
    game["goals"] = [g for g in goals if isinstance(g, dict) and g.get("id") != goal_id]
    return len(game["goals"]) < initial_len


def set_game_notes(game: Dict[str, Any], notes: str) -> None:
    """Establece las notas personales del juego."""
    game["notes"] = str(notes or "").strip()


def record_daily_playtime(game: Dict[str, Any], minutes: int, date_str: Optional[str] = None) -> None:
    """Acumula minutos en el mapa diario del juego para la fecha indicada (por defecto hoy)."""
    if minutes <= 0:
        return
    d_str = date_str or datetime.now().strftime("%Y-%m-%d")
    daily = game.setdefault("daily_playtime", {})
    if not isinstance(daily, dict):
        daily = {}
        game["daily_playtime"] = daily
    daily[d_str] = int(daily.get(d_str, 0) or 0) + int(minutes)


def increment_game_play_count(game: Dict[str, Any]) -> int:
    """Incrementa la cantidad de veces que el juego ha sido iniciado."""
    curr = int(game.get("play_count", 0) or 0)
    game["play_count"] = curr + 1
    if not game.get("date_added"):
        game["date_added"] = datetime.now().strftime("%Y-%m-%d")
    return game["play_count"]
