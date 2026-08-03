"""
Cliente sencillo para la API de Twitch (Helix) usando el flujo
client_credentials, pensado para chequear si un canal está en vivo.

Docs: https://dev.twitch.tv/docs/api/
"""

import time
import aiohttp

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_BASE = "https://api.twitch.tv/helix"


class TwitchApiError(Exception):
    pass


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise ValueError("Faltan TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None
        self._token_expires_at = 0

    async def _get_app_token(self) -> str:
        """Consigue (o reusa) un app access token vía client_credentials."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(TOKEN_URL, params=params) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise TwitchApiError(f"No se pudo obtener token de Twitch ({resp.status}): {text[:200]}")
                data = await resp.json()

        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)
        return self._token

    async def get_stream_info(self, user_login: str) -> dict | None:
        """
        Devuelve info del stream si el canal está en vivo, o None si está offline.
        user_login es el nombre de usuario de Twitch (en minúsculas), ej: 'lgltn'.
        """
        token = await self._get_app_token()
        headers = {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {token}",
        }
        params = {"user_login": user_login}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(f"{HELIX_BASE}/streams", params=params) as resp:
                if resp.status == 401:
                    # Token puede haber sido revocado; forzamos refresh en el próximo intento.
                    self._token = None
                    raise TwitchApiError("Token de Twitch inválido/expirado.")
                if resp.status != 200:
                    text = await resp.text()
                    raise TwitchApiError(f"Error Twitch API ({resp.status}): {text[:200]}")
                data = await resp.json()

        streams = data.get("data", [])
        return streams[0] if streams else None
