"""
Cliente sencillo para la API oficial de PUBG (developer.pubg.com).

Documentación: https://documentation.pubg.com/
"""

from collections import Counter

import aiohttp

PUBG_API_BASE = "https://api.pubg.com"

# Modos de juego válidos según la documentación de PUBG
VALID_GAME_MODES = ["solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"]

# Códigos de mapa (attributes.mapName) -> nombre amigable
MAP_NAMES = {
    "Baltic_Main": "Erangel",
    "Chimera_Main": "Paramo",
    "Desert_Main": "Miramar",
    "DihorOtok_Main": "Vikendi",
    "Erangel_Main": "Erangel",
    "Heaven_Main": "Haven",
    "Kiki_Main": "Deston",
    "Range_Main": "Camp Jackal",
    "Savage_Main": "Sanhok",
    "Summerland_Main": "Karakin",
    "Tiger_Main": "Taego",
    "Neon_Main": "Rondo",
}

# Mapeo parcial de armas comunes (damageCauserName de la telemetry -> nombre amigable).
# Lo que no está mapeado se limpia genéricamente en friendly_weapon_name().
WEAPON_NAMES = {
    "WeapAK47_C": "AKM",
    "WeapM416_C": "M416",
    "WeapKar98k_C": "Kar98k",
    "WeapUMP_C": "UMP45",
    "WeapVector_C": "Vector",
    "WeapM16A4_C": "M16A4",
    "WeapSCAR-L_C": "SCAR-L",
    "WeapM249_C": "M249",
    "WeapDP28_C": "DP-28",
    "WeapWinchester_C": "Winchester",
    "WeapMini14_C": "Mini 14",
    "WeapSKS_C": "SKS",
    "WeapMk47Mutant_C": "Mk47 Mutant",
    "WeapBerreta686_C": "S686",
    "WeapSawnoff_C": "Sawed-off",
    "WeapS1897_C": "S1897",
    "WeapS12K_C": "S12K",
    "WeapUZI_C": "Micro UZI",
    "WeapThompson_C": "Tommy Gun",
    "WeapP92_C": "P92",
    "WeapG18_C": "P18C",
    "WeapDesertEagle_C": "Deagle",
    "WeapR1895_C": "R1895",
    "WeapCrowbar_C": "Sartén",
    "WeapPanzerFaust100M_C": "Panzerfaust",
    "WeapM24_C": "M24",
    "WeapAWM_C": "AWM",
    "WeapMosinNagant_C": "Mosin Nagant",
    "WeapVSS_C": "VSS",
    "WeapQBU88_C": "QBU",
    "WeapMk14_C": "Mk14 EBR",
    "WeapGroza_C": "Groza",
    "WeapAUG_C": "AUG A3",
    "WeapBizonPP19_C": "PP-19 Bizon",
    "WeapDBS_C": "DBS",
    "WeapMolotov_C": "Molotov",
    "WeapFragGrenade_C": "Granada de fragmentación",
    "None": "Zona azul / caída / otros",
}


def friendly_map_name(map_code: str) -> str:
    return MAP_NAMES.get(map_code, map_code or "Desconocido")


def friendly_weapon_name(causer: str) -> str:
    if not causer:
        return "Desconocido"
    if causer in WEAPON_NAMES:
        return WEAPON_NAMES[causer]
    name = causer
    if name.startswith("Weap"):
        name = name[4:]
    if name.endswith("_C"):
        name = name[:-2]
    return name or causer


def format_survival_time(seconds: float) -> str:
    seconds = int(seconds or 0)
    minutes, secs = divmod(seconds, 60)
    return f"{minutes}m {secs}s"


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

    # --- Partidas recientes / telemetry ---

    async def get_player_matches(self, player_name: str) -> dict:
        """Devuelve accountId y lista de matchIds recientes (últimos 14 días) de un jugador."""
        url = f"{PUBG_API_BASE}/shards/{self.shard}/players"
        data = await self._get(url, params={"filter[playerNames]": player_name})
        players = data.get("data", [])
        if not players:
            raise PubgApiError(f"No se encontró el jugador '{player_name}' en el shard '{self.shard}'.")
        player = players[0]
        account_id = player["id"]
        match_refs = player.get("relationships", {}).get("matches", {}).get("data", [])
        match_ids = [m["id"] for m in match_refs]
        return {"account_id": account_id, "match_ids": match_ids}

    async def get_match(self, match_id: str) -> dict:
        """Detalle completo (JSON API crudo) de una partida."""
        url = f"{PUBG_API_BASE}/shards/{self.shard}/matches/{match_id}"
        return await self._get(url)

    @staticmethod
    def _extract_match_summary(match_data: dict, account_id: str) -> dict | None:
        attrs = match_data["data"]["attributes"]
        included = match_data.get("included", [])

        participant_stats = None
        for item in included:
            if item.get("type") == "participant" and item["attributes"]["stats"].get("playerId") == account_id:
                participant_stats = item["attributes"]["stats"]
                break

        if participant_stats is None:
            return None

        telemetry_url = None
        for item in included:
            if item.get("type") == "asset":
                telemetry_url = item["attributes"].get("URL")
                break

        return {
            "match_id": match_data["data"]["id"],
            "map_code": attrs.get("mapName"),
            "map_name": friendly_map_name(attrs.get("mapName", "")),
            "game_mode": attrs.get("gameMode"),
            "created_at": attrs.get("createdAt"),
            "stats": participant_stats,
            "telemetry_url": telemetry_url,
        }

    async def get_recent_matches(self, player_name: str, limit: int = 5) -> list[dict]:
        """
        Trae hasta `limit` partidas recientes (más nueva primero) con stats
        del jugador en cada una. Usa 1 request para la lista + 1 por partida.
        """
        info = await self.get_player_matches(player_name)
        account_id = info["account_id"]
        match_ids = info["match_ids"][:limit]

        if not match_ids:
            raise PubgApiError(f"'{player_name}' no tiene partidas registradas en los últimos 14 días.")

        summaries = []
        for match_id in match_ids:
            try:
                match_data = await self.get_match(match_id)
            except PubgApiError:
                continue
            summary = self._extract_match_summary(match_data, account_id)
            if summary:
                summaries.append(summary)

        summaries.sort(key=lambda s: s["created_at"] or "", reverse=True)
        return summaries

    async def get_telemetry_events(self, telemetry_url: str) -> list[dict]:
        """Descarga y parsea el archivo de telemetry (lista de eventos) de una partida."""
        async with aiohttp.ClientSession() as session:
            async with session.get(telemetry_url, headers={"Accept-Encoding": "gzip"}) as resp:
                if resp.status != 200:
                    raise PubgApiError(f"No se pudo descargar la telemetry ({resp.status}).")
                return await resp.json(content_type=None)

    async def get_favorite_weapon(self, player_name: str, num_matches: int = 3) -> dict:
        """
        Analiza la telemetry de las últimas `num_matches` partidas y cuenta
        con qué arma consiguió más kills el jugador.
        """
        matches = await self.get_recent_matches(player_name, limit=num_matches)
        if not matches:
            raise PubgApiError(f"'{player_name}' no tiene partidas recientes para analizar.")

        total_counter = Counter()
        matches_analyzed = 0

        for m in matches:
            if not m.get("telemetry_url"):
                continue
            try:
                events = await self.get_telemetry_events(m["telemetry_url"])
            except PubgApiError:
                continue
            total_counter.update(_count_weapon_kills(events, player_name))
            matches_analyzed += 1

        return {
            "counter": total_counter,
            "matches_analyzed": matches_analyzed,
            "matches_total": len(matches),
        }


def _count_weapon_kills(events: list[dict], player_name: str) -> Counter:
    """Cuenta kills por arma (damageCauserName) del jugador en una lista de eventos de telemetry."""
    counter = Counter()
    name_lower = player_name.lower()
    for event in events:
        if event.get("_T") != "LogPlayerKillV2":
            continue
        if event.get("isSuicide"):
            continue
        killer = event.get("killer") or {}
        if killer.get("name", "").lower() != name_lower:
            continue
        damage_info = event.get("killerDamageInfo") or {}
        weapon = damage_info.get("damageCauserName") or "None"
        counter[weapon] += 1
    return counter


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


def format_match_summary(player_name: str, match: dict) -> str:
    """Resumen de una partida puntual (para /ultimapartida)."""
    stats = match["stats"]
    win_place = stats.get("winPlace", "?")
    kills = stats.get("kills", 0)
    assists = stats.get("assists", 0)
    damage = round(stats.get("damageDealt", 0.0), 1)
    headshots = stats.get("headshotKills", 0)
    dbnos = stats.get("DBNOs", 0)
    survived = format_survival_time(stats.get("timeSurvived", 0))
    longest_kill = round(stats.get("longestKill", 0.0), 1)

    resultado = "🏆 ¡Victoria!" if win_place == 1 else f"Posición: #{win_place}"

    return (
        f"**Última partida de {player_name}**\n"
        f"Mapa: {match['map_name']} | Modo: {match['game_mode']}\n"
        f"{resultado}\n"
        f"Kills: {kills} | Asistencias: {assists} | Derribos (DBNO): {dbnos}\n"
        f"Daño: {damage} | Headshots: {headshots} | Kill más lejano: {longest_kill}m\n"
        f"Tiempo con vida: {survived}"
    )


def compute_streaks(matches: list[dict]) -> dict:
    """
    matches: lista ordenada de más nueva a más vieja (cada item con ["stats"]).
    Devuelve la racha activa de victorias y de partidas sin kills, contando
    desde la más reciente hacia atrás hasta que se corta.
    """
    win_streak = 0
    for m in matches:
        if m["stats"].get("winPlace") == 1:
            win_streak += 1
        else:
            break

    no_kill_streak = 0
    for m in matches:
        if m["stats"].get("kills", 0) == 0:
            no_kill_streak += 1
        else:
            break

    return {"win_streak": win_streak, "no_kill_streak": no_kill_streak}


def format_favorite_weapon(player_name: str, result: dict) -> str:
    counter = result["counter"]
    analyzed = result["matches_analyzed"]
    total = result["matches_total"]

    if not counter:
        return (
            f"**{player_name}** no tiene kills registradas en las últimas {analyzed} partidas analizadas "
            f"(de {total} encontradas)."
        )

    lines = [f"**Armas favoritas de {player_name}** (últimas {analyzed} de {total} partidas analizadas)"]
    for weapon, count in counter.most_common(5):
        lines.append(f"{friendly_weapon_name(weapon)}: {count} kill{'s' if count != 1 else ''}")

    return "\n".join(lines)
