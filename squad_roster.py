"""
Roster fijo del squad, guardado en squad.json (editable a mano).

Formato del archivo:
[
  "NombreExactoEnPUBG1",
  "NombreExactoEnPUBG2"
]
"""

import json
import os

ROSTER_FILE = "squad.json"


class RosterError(Exception):
    pass


def load_roster() -> list[str]:
    if not os.path.exists(ROSTER_FILE):
        raise RosterError(
            f"No existe '{ROSTER_FILE}'. Creá el archivo con una lista JSON de nombres de PUBG, "
            f'ej: ["Fulano", "Mengano"]'
        )
    try:
        with open(ROSTER_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise RosterError(f"'{ROSTER_FILE}' tiene un JSON inválido: {e}")

    if not isinstance(data, list) or not all(isinstance(n, str) for n in data):
        raise RosterError(f"'{ROSTER_FILE}' debe ser una lista de strings con nombres de PUBG.")

    if not data:
        raise RosterError(f"'{ROSTER_FILE}' está vacío. Agregá al menos un nombre de jugador.")

    if len(data) > 10:
        raise RosterError(
            "El bot soporta hasta 10 jugadores en el roster por límite de la API de PUBG (1 request)."
        )

    return data
