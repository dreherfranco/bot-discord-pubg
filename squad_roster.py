"""
Roster fijo del squad. Se puede definir de dos formas (en este orden de prioridad):

1. Archivo squad.json en la carpeta del proyecto (uso local, editable a mano):
   [
     "NombreExactoEnPUBG1",
     "NombreExactoEnPUBG2"
   ]

2. Variable de entorno SQUAD_ROSTER, con los nombres separados por coma
   (útil para hosting, ya que squad.json no se sube al repo de GitHub):
   SQUAD_ROSTER=NombreExactoEnPUBG1,NombreExactoEnPUBG2
"""

import json
import os

ROSTER_FILE = "squad.json"
ROSTER_ENV_VAR = "SQUAD_ROSTER"


class RosterError(Exception):
    pass


def _validate(data: list[str], source: str) -> list[str]:
    if not isinstance(data, list) or not all(isinstance(n, str) for n in data):
        raise RosterError(f"El roster ({source}) debe ser una lista de nombres de PUBG.")
    if not data:
        raise RosterError(f"El roster ({source}) está vacío. Agregá al menos un nombre de jugador.")
    if len(data) > 10:
        raise RosterError(
            "El bot soporta hasta 10 jugadores en el roster por límite de la API de PUBG (1 request)."
        )
    return data


def load_roster() -> list[str]:
    if os.path.exists(ROSTER_FILE):
        try:
            with open(ROSTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise RosterError(f"'{ROSTER_FILE}' tiene un JSON inválido: {e}")
        return _validate(data, ROSTER_FILE)

    env_value = os.getenv(ROSTER_ENV_VAR)
    if env_value:
        names = [n.strip() for n in env_value.split(",") if n.strip()]
        return _validate(names, f"variable de entorno {ROSTER_ENV_VAR}")

    raise RosterError(
        f"No hay roster configurado. Creá '{ROSTER_FILE}' con una lista JSON de nombres "
        f'(ej: ["Fulano", "Mengano"]) o definí la variable de entorno {ROSTER_ENV_VAR} '
        f"con los nombres separados por coma."
    )
