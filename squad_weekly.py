"""
Tracker de "jugador de la semana" por promedio de daño.

Como el comando es manual (no corre solo), la "semana" se define como una
ventana móvil: la primera vez que se corre el comando para un jugador se
guarda un checkpoint (partidas jugadas + daño acumulado a esa fecha). Las
siguientes veces se compara contra ese checkpoint. Si el checkpoint tiene
más de WEEK_DAYS días, se reinicia automáticamente (arranca una semana nueva
para ese jugador).
"""

import json
import os
import time
from datetime import datetime, timezone

SNAPSHOT_FILE = "weekly_snapshots.json"
WEEK_SECONDS = 7 * 24 * 60 * 60

ANNOUNCE_STATE_FILE = "weekly_announce_state.json"


def _load_snapshots() -> dict:
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    try:
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_snapshots(data: dict) -> None:
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_weekly_deltas(current_stats: dict) -> dict:
    """
    current_stats: {player_name: {"roundsPlayed": int, "damageDealt": float}}

    Devuelve {player_name: {"rounds": int, "damage": float, "avg_damage": float} | None}
    None significa "checkpoint recién reiniciado, todavía sin datos de esta semana".

    Efecto secundario: persiste checkpoints nuevos/reiniciados en SNAPSHOT_FILE.
    """
    snapshots = _load_snapshots()
    now = time.time()
    deltas = {}
    dirty = False

    for name, stats in current_stats.items():
        rounds_now = stats.get("roundsPlayed", 0)
        damage_now = stats.get("damageDealt", 0.0)

        checkpoint = snapshots.get(name)
        needs_reset = (
            checkpoint is None
            or (now - checkpoint.get("timestamp", 0)) > WEEK_SECONDS
            or rounds_now < checkpoint.get("rounds", 0)  # stats bajaron -> temporada/roster cambió
        )

        if needs_reset:
            snapshots[name] = {"timestamp": now, "rounds": rounds_now, "damage": damage_now}
            dirty = True
            deltas[name] = None
            continue

        delta_rounds = rounds_now - checkpoint["rounds"]
        delta_damage = damage_now - checkpoint["damage"]

        if delta_rounds <= 0:
            deltas[name] = None
            continue

        deltas[name] = {
            "rounds": delta_rounds,
            "damage": round(delta_damage, 1),
            "avg_damage": round(delta_damage / delta_rounds, 1),
        }

    if dirty:
        _save_snapshots(snapshots)

    return deltas


def reset_all() -> None:
    """Borra todos los checkpoints (arranca una semana nueva para todos)."""
    if os.path.exists(SNAPSHOT_FILE):
        os.remove(SNAPSHOT_FILE)


def _current_year_week() -> str:
    iso = datetime.now(timezone.utc).isocalendar()
    return f"{iso[0]}-W{iso[1]}"


def was_announced_this_week() -> bool:
    """Indica si ya se hizo el anuncio automático semanal en la semana calendario actual (UTC)."""
    if not os.path.exists(ANNOUNCE_STATE_FILE):
        return False
    try:
        with open(ANNOUNCE_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    return data.get("last_announced") == _current_year_week()


def mark_announced_this_week() -> None:
    with open(ANNOUNCE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"last_announced": _current_year_week()}, f)
