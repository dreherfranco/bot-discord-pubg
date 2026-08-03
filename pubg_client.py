"""
Cliente sencillo para la API oficial de PUBG (developer.pubg.com).

Documentación: https://documentation.pubg.com/
"""

import os
import aiohttp

PUBG_API_BASE = "https://api.pubg.com"

# Modos de juego válidos según la documentación de PUBG
VALID_GAME_MODES = ["solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"]


class PubgApiError(Exception):
    """Error genérico al hablar con la API de PUBG."""


class PubgClient:
    def __init__(self, api_key: str, shard: str = "steam"):
        if not api_key:
            raise ValueError("Falta PUBG_API_KEY")
        self.api_key = api_key
        self.shard = shard
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/vnd.api+json",
        }

    async def _get(self, url: str, params: dict | None = None) -> dict:
        async with aiohttp.ClientSession(headers=self._headers) as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 404:
                    raise PubgApiError("Jugador no encontrado.")
                if resp.status == 401:
                    raise PubgApiError("PUBG_API_KEY inválida o vencida.")
                if resp.status == 429:
                    raise PubgApiError("Límite de rate de la API de PUBG alcanzado. Probá de nuevo en un minuto.")
                if resp.status != 200:
                    text = await resp.text()
                    raise PubgApiError(f"Error PUBG API ({resp.status}): {text[:200]}")
                return await resp.json()

    async def get_account_id(self, player_name: str) -> str:
        """Busca el accountId de un jugador por su nombre en el juego."""
        ids = await self.get_account_ids([player_name])
        if player_name not in ids:
            raise PubgApiError(f"No se encontró el jugador '{player_name}' en el shard '{self.shard}'.")
        return ids[player_name]

    async def get_account_ids(self, player_names: list[str]) -> dict[str, str]:
        """
        Busca varios accountId en una sola request (la API de PUBG permite
        hasta 10 nombres por consulta separados por coma).
        Devuelve un dict {nombre_pedido: accountId} (case-insensitive match).
        """
        if not player_names:
            return {}
        if len(player_names) > 10:
            raise PubgApiError("La API de PUBG permite consultar como máximo 10 jugadores por vez.")

        url = f"{PUBG_API_BASE}/shards/{self.shard}/players"
        data = await self._get(url, params={"filter[playerNames]": ",".join(player_names)})
        players = data.get("data", [])

        # La API devuelve el nombre con su capitalización real; mapeamos en minúsculas
        # para poder machear contra lo que pidió el usuario sin importar mayúsculas.
        by_lower_name = {
            p["attributes"]["name"].lower(): p["id"] for p in players
        }

        result = {}
        for requested in player_names:
            found_id = by_lower_name.get(requested.lower())
            if found_id:
                result[requested] = found_id
        return result

    async def get_lifetime_stats(self, account_id: str) -> dict:
        """Devuelve las stats 'lifetime' (overall) del jugador."""
        url = f"{PUBG_API_BASE}/shards/{self.shard}/players/{account_id}/seasons/lifetime"
        data = await self._get(url)
        return data["data"]["attributes"]["gameModeStats"]

    async def get_player_stats(self, player_name: str, game_mode: str = "squad") -> dict:
        """Atajo: nombre -> stats lifetime de un modo puntual."""
        if game_mode not in VALID_GAME_MODES:
            raise PubgApiError(
                f"Modo inválido '{game_mode}'. Válidos: {', '.join(VALID_GAME_MODES)}"
            )
        account_id = await self.get_account_id(player_name)
        all_modes = await self.get_lifetime_stats(account_id)
        stats = all_modes.get(game_mode)
        if not stats or stats.get("roundsPlayed", 0) == 0:
            raise PubgApiError(f"'{player_name}' no tiene partidas registradas en modo '{game_mode}'.")
        return stats

    async def get_squad_stats(self, player_names: list[str], game_mode: str = "squad") -> list[dict]:
        """
        Trae stats lifetime de varios jugadores a la vez.
        Devuelve una lista de dicts: {"name": str, "stats": dict|None, "error": str|None}
        (no levanta excepción por un jugador individual que falle).
        """
        if game_mode not in VALID_GAME_MODES:
            raise PubgApiError(
                f"Modo inválido '{game_mode}'. Válidos: {', '.join(VALID_GAME_MODES)}"
            )

        results = []
        try:
            ids = await self.get_account_ids(player_names)
        except PubgApiError as e:
            return [{"name": n, "stats": None, "error": str(e)} for n in player_names]

        for name in player_names:
            account_id = ids.get(name)
            if not account_id:
                results.append({"name": name, "stats": None, "error": "no encontrado en PUBG"})
                continue
            try:
                all_modes = await self.get_lifetime_stats(account_id)
                stats = all_modes.get(game_mode)
                if not stats or stats.get("roundsPlayed", 0) == 0:
                    results.append({"name": name, "stats": None, "error": f"sin partidas en '{game_mode}'"})
                else:
                    results.append({"name": name, "stats": stats, "error": None})
            except PubgApiError as e:
                results.append({"name": name, "stats": None, "error": str(e)})

        return results


def format_stats_summary(player_name: str, game_mode: str, stats: dict) -> str:
    """Arma un resumen legible de las stats para mostrar en Discord."""
    rounds = stats.get("roundsPlayed", 0)
    wins = stats.get("wins", 0)
    top10s = stats.get("top10s", 0)
    kills = stats.get("kills", 0)
    deaths = stats.get("losses", 0)  # PUBG no da "deaths" directo; losses ~ partidas no ganadas
    assists = stats.get("assists", 0)
    damage = stats.get("damageDealt", 0.0)
    headshots = stats.get("headshotKills", 0)
    kd = round(kills / rounds, 2) if rounds else 0  # kills promedio por partida como referencia
    win_rate = round((wins / rounds) * 100, 1) if rounds else 0
    avg_damage = round(damage / rounds, 1) if rounds else 0

    return (
        f"**Estadísticas de {player_name}** ({game_mode})\n"
        f"Partidas jugadas: {rounds}\n"
        f"Victorias: {wins} ({win_rate}%)\n"
        f"Top 10: {top10s}\n"
        f"Kills totales: {kills}\n"
        f"Asistencias: {assists}\n"
        f"Headshot kills: {headshots}\n"
        f"Daño promedio por partida: {avg_damage}\n"
        f"Kills promedio por partida: {kd}"
    )


def format_squad_line(name: str, stats: dict | None, error: str | None) -> str:
    """Una línea compacta de stats para usar en /squadstats."""
    if error or not stats:
        return f"❌ **{name}** — {error or 'sin datos'}"

    rounds = stats.get("roundsPlayed", 0)
    wins = stats.get("wins", 0)
    kills = stats.get("kills", 0)
    damage = stats.get("damageDealt", 0.0)
    win_rate = round((wins / rounds) * 100, 1) if rounds else 0
    avg_damage = round(damage / rounds, 1) if rounds else 0
    kd = round(kills / rounds, 2) if rounds else 0

    return (
        f"**{name}** — {rounds} partidas | {wins} victorias ({win_rate}%) | "
        f"{kills} kills ({kd}/partida) | {avg_damage} dmg prom."
    )
