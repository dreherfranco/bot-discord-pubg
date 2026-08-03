"""
Chequeo de avisos de mantenimiento de PUBG.

No existe una API oficial de PUBG/Krafton para esto. Lo que se usa acá es el
feed público de noticias de Steam para la app de PUBG (no requiere API key),
filtrando los anuncios que mencionen mantenimiento/downtime.
"""

import json
import os

import aiohttp

STEAM_APP_ID = 578080  # PUBG: BATTLEGROUNDS
STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"

MAINTENANCE_KEYWORDS = [
    "maintenance",
    "mantenimiento",
    "downtime",
    "manutenção",
    "wartung",
    "server maintenance",
    "scheduled maintenance",
]

STATE_FILE = "steam_news_state.json"


class SteamNewsError(Exception):
    pass


async def fetch_recent_news(count: int = 15) -> list[dict]:
    """Trae las últimas noticias de PUBG publicadas en Steam."""
    params = {
        "appid": STEAM_APP_ID,
        "count": count,
        "maxlength": 400,
        "format": "json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(STEAM_NEWS_URL, params=params) as resp:
            if resp.status != 200:
                raise SteamNewsError(f"Error consultando noticias de Steam ({resp.status}).")
            data = await resp.json(content_type=None)
    return data.get("appnews", {}).get("newsitems", [])


def is_maintenance_related(item: dict) -> bool:
    text = f"{item.get('title', '')} {item.get('contents', '')}".lower()
    return any(kw in text for kw in MAINTENANCE_KEYWORDS)


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


async def get_new_maintenance_announcements() -> list[dict]:
    """
    Devuelve los anuncios de mantenimiento nuevos desde el último chequeo
    (no repite avisos ya mandados). En la primera corrida no manda nada
    de historial viejo, solo guarda el punto de partida.
    """
    items = await fetch_recent_news(count=15)
    maintenance_items = [i for i in items if is_maintenance_related(i)]

    state = _load_state()
    last_seen_gid = state.get("last_seen_gid")

    if last_seen_gid is None:
        if maintenance_items:
            state["last_seen_gid"] = maintenance_items[0]["gid"]
            _save_state(state)
        return []

    new_items = []
    for item in maintenance_items:
        if item.get("gid") == last_seen_gid:
            break
        new_items.append(item)

    if maintenance_items:
        state["last_seen_gid"] = maintenance_items[0]["gid"]
        _save_state(state)

    return list(reversed(new_items))  # del más viejo al más nuevo


def format_announcement(item: dict) -> str:
    title = item.get("title", "Anuncio de PUBG")
    url = item.get("url", "")
    return f"**{title}**\n{url}"
