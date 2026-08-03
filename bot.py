"""
Bot de Discord con:
  - /pubgstats <jugador> [modo]  -> estadísticas lifetime de PUBG (shard steam)
  - /squadstats [modo]           -> estadísticas de todo el squad (squad.json)
  - /jugadordelasemana           -> mejor promedio de daño desde el último checkpoint
  - /ultimapartida <jugador>     -> resultado de la última partida jugada
  - /vs <jugador1> <jugador2>    -> compara stats lifetime de dos jugadores
  - /racha <jugador>             -> racha de victorias o de partidas sin kills
  - /armafavorita <jugador>      -> arma con más kills en las últimas partidas
  - /mantenimiento               -> último aviso de mantenimiento (chequeo manual)
  - Aviso automático en un canal cuando aparece un anuncio nuevo de mantenimiento
  - Anuncio automático semanal del jugador de la semana (día/hora configurables)

Configuración: ver .env.example / README.md
"""

import os
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from pubg_client import (
    PubgClient,
    PubgApiError,
    format_stats_summary,
    format_squad_line,
    format_match_summary,
    format_favorite_weapon,
    compute_streaks,
    VALID_GAME_MODES,
)
from squad_roster import load_roster, RosterError
from squad_weekly import (
    get_weekly_deltas,
    reset_all as reset_weekly,
    was_announced_this_week,
    mark_announced_this_week,
)
from steam_news import (
    fetch_recent_news,
    is_maintenance_related,
    get_new_maintenance_announcements,
    format_announcement,
    SteamNewsError,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pubg-bot")

# --- Config desde variables de entorno ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PUBG_API_KEY = os.getenv("PUBG_API_KEY")
PUBG_SHARD = os.getenv("PUBG_SHARD", "steam")
NOTIFY_CHANNEL_ID = os.getenv("NOTIFY_CHANNEL_ID")  # canal donde avisar mantenimiento
MAINTENANCE_CHECK_SECONDS = int(os.getenv("MAINTENANCE_CHECK_SECONDS", "1800"))  # 30 min

# Anuncio semanal automático del jugador de la semana.
# Por defecto: domingo 20:00 hora Argentina (UTC-3) = domingo 23:00 UTC.
# weekday(): lunes=0 ... domingo=6
WEEKLY_ANNOUNCE_CHANNEL_ID = os.getenv("WEEKLY_ANNOUNCE_CHANNEL_ID") or NOTIFY_CHANNEL_ID
WEEKLY_ANNOUNCE_WEEKDAY = int(os.getenv("WEEKLY_ANNOUNCE_WEEKDAY", "6"))
WEEKLY_ANNOUNCE_HOUR_UTC = int(os.getenv("WEEKLY_ANNOUNCE_HOUR_UTC", "23"))

# --- Cliente de la API de PUBG ---
pubg_client = PubgClient(api_key=PUBG_API_KEY, shard=PUBG_SHARD) if PUBG_API_KEY else None

intents = discord.Intents.default()


class PubgBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        if NOTIFY_CHANNEL_ID:
            check_maintenance_loop.start()
        else:
            log.warning("Aviso de mantenimiento desactivado: falta NOTIFY_CHANNEL_ID en el .env")

        if WEEKLY_ANNOUNCE_CHANNEL_ID and pubg_client:
            check_weekly_announce_loop.start()
        else:
            log.warning(
                "Anuncio semanal automático desactivado: falta WEEKLY_ANNOUNCE_CHANNEL_ID "
                "(o NOTIFY_CHANNEL_ID) o PUBG_API_KEY en el .env"
            )


client = PubgBot()


@client.event
async def on_ready():
    log.info(f"Conectado como {client.user} (id: {client.user.id})")


# --- Slash command: /pubgstats ---
@client.tree.command(name="pubgstats", description="Estadísticas de PUBG (lifetime) de un jugador de Steam")
@app_commands.describe(
    jugador="Nombre exacto del jugador en PUBG",
    modo="Modo de juego (por defecto squad)",
)
@app_commands.choices(
    modo=[app_commands.Choice(name=m, value=m) for m in VALID_GAME_MODES]
)
async def pubgstats(interaction: discord.Interaction, jugador: str, modo: app_commands.Choice[str] = None):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    await interaction.response.defer()
    game_mode = modo.value if modo else "squad"

    try:
        stats = await pubg_client.get_player_stats(jugador, game_mode)
    except PubgApiError as e:
        await interaction.followup.send(f"No pude traer las stats: {e}")
        return
    except Exception:
        log.exception("Error inesperado consultando PUBG API")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    resumen = format_stats_summary(jugador, game_mode, stats)
    embed = discord.Embed(description=resumen, color=discord.Color.orange())
    embed.set_footer(text="Datos: PUBG API (lifetime stats)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /squadstats ---
@client.tree.command(name="squadstats", description="Estadísticas de todo el squad registrado en squad.json")
@app_commands.describe(modo="Modo de juego (por defecto squad)")
@app_commands.choices(
    modo=[app_commands.Choice(name=m, value=m) for m in VALID_GAME_MODES]
)
async def squadstats(interaction: discord.Interaction, modo: app_commands.Choice[str] = None):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    try:
        roster = load_roster()
    except RosterError as e:
        await interaction.response.send_message(f"{e}", ephemeral=True)
        return

    await interaction.response.defer()
    game_mode = modo.value if modo else "squad"

    try:
        results = await pubg_client.get_squad_stats(roster, game_mode)
    except Exception:
        log.exception("Error inesperado consultando PUBG API (squadstats)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    lines = [format_squad_line(r["name"], r["stats"], r["error"]) for r in results]
    embed = discord.Embed(
        title=f"Stats del squad ({game_mode})",
        description="\n".join(lines),
        color=discord.Color.orange(),
    )
    embed.set_footer(text="Datos: PUBG API (lifetime stats)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /jugadordelasemana ---
@client.tree.command(
    name="jugadordelasemana",
    description="Mejor promedio de daño del squad desde el último checkpoint (~7 días)",
)
async def jugadordelasemana(interaction: discord.Interaction):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    try:
        roster = load_roster()
    except RosterError as e:
        await interaction.response.send_message(f"{e}", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        results = await pubg_client.get_squad_stats(roster, "squad")
    except Exception:
        log.exception("Error inesperado consultando PUBG API (jugadordelasemana)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    current_stats = {r["name"]: r["stats"] for r in results if r["stats"]}
    failed = [r["name"] for r in results if not r["stats"]]

    deltas = get_weekly_deltas(current_stats)

    ranking = [
        (name, d["avg_damage"], d["rounds"])
        for name, d in deltas.items()
        if d is not None
    ]
    ranking.sort(key=lambda x: x[1], reverse=True)

    just_reset = [name for name, d in deltas.items() if d is None]

    lines = []
    if ranking:
        for i, (name, avg_damage, rounds) in enumerate(ranking, start=1):
            medal = {1: "🏆", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"{medal} **{name}** — {avg_damage} dmg prom. ({rounds} partidas)")
    else:
        lines.append("Todavía no hay suficientes partidas nuevas desde el último checkpoint.")

    if just_reset:
        lines.append("")
        lines.append(
            "🔄 Se reinició el checkpoint semanal para: " + ", ".join(just_reset) +
            " (van a aparecer en el próximo /jugadordelasemana)."
        )
    if failed:
        lines.append("")
        lines.append("❌ No se pudo consultar: " + ", ".join(failed))

    embed = discord.Embed(
        title="Jugador de la semana (mejor daño promedio)",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await interaction.followup.send(embed=embed)


# --- Slash command: /ultimapartida ---
@client.tree.command(name="ultimapartida", description="Resultado de la última partida jugada por un jugador")
@app_commands.describe(jugador="Nombre exacto del jugador en PUBG")
async def ultimapartida(interaction: discord.Interaction, jugador: str):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    await interaction.response.defer()

    try:
        matches = await pubg_client.get_recent_matches(jugador, limit=5)
    except PubgApiError as e:
        await interaction.followup.send(f"No pude traer la partida: {e}")
        return
    except Exception:
        log.exception("Error inesperado consultando PUBG API (ultimapartida)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    if not matches:
        await interaction.followup.send(f"No encontré partidas recientes de '{jugador}' (últimos 14 días).")
        return

    resumen = format_match_summary(jugador, matches[0])
    embed = discord.Embed(description=resumen, color=discord.Color.blurple())
    embed.set_footer(text="Datos: PUBG API (match data)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /vs ---
@client.tree.command(name="vs", description="Compara las stats lifetime de dos jugadores")
@app_commands.describe(
    jugador1="Primer jugador",
    jugador2="Segundo jugador",
    modo="Modo de juego (por defecto squad)",
)
@app_commands.choices(
    modo=[app_commands.Choice(name=m, value=m) for m in VALID_GAME_MODES]
)
async def vs(
    interaction: discord.Interaction,
    jugador1: str,
    jugador2: str,
    modo: app_commands.Choice[str] = None,
):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    await interaction.response.defer()
    game_mode = modo.value if modo else "squad"

    try:
        results = await pubg_client.get_squad_stats([jugador1, jugador2], game_mode)
    except Exception:
        log.exception("Error inesperado consultando PUBG API (vs)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    lines = [format_squad_line(r["name"], r["stats"], r["error"]) for r in results]
    embed = discord.Embed(
        title=f"{jugador1} vs {jugador2} ({game_mode})",
        description="\n".join(lines),
        color=discord.Color.red(),
    )
    embed.set_footer(text="Datos: PUBG API (lifetime stats)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /racha ---
@client.tree.command(name="racha", description="Racha de victorias o de partidas sin kills de un jugador")
@app_commands.describe(jugador="Nombre exacto del jugador en PUBG")
async def racha(interaction: discord.Interaction, jugador: str):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    await interaction.response.defer()

    try:
        matches = await pubg_client.get_recent_matches(jugador, limit=5)
    except PubgApiError as e:
        await interaction.followup.send(f"No pude traer las partidas: {e}")
        return
    except Exception:
        log.exception("Error inesperado consultando PUBG API (racha)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    if not matches:
        await interaction.followup.send(f"No encontré partidas recientes de '{jugador}' (últimos 14 días).")
        return

    streaks = compute_streaks(matches)
    win_streak = streaks["win_streak"]
    no_kill_streak = streaks["no_kill_streak"]

    if win_streak >= 2:
        texto = f"🔥 **{jugador}** viene de **{win_streak} victorias seguidas**!"
    elif no_kill_streak >= 2:
        texto = f"💀 **{jugador}** lleva **{no_kill_streak} partidas seguidas sin kills**."
    else:
        texto = f"Sin racha destacada para **{jugador}** en las últimas {len(matches)} partidas."

    embed = discord.Embed(description=texto, color=discord.Color.dark_gold())
    embed.set_footer(text=f"Basado en las últimas {len(matches)} partidas (máx. 14 días)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /armafavorita ---
@client.tree.command(name="armafavorita", description="Arma con más kills de un jugador en sus últimas partidas")
@app_commands.describe(
    jugador="Nombre exacto del jugador en PUBG",
    partidas="Cantidad de partidas recientes a analizar (1-5, por defecto 3)",
)
async def armafavorita(interaction: discord.Interaction, jugador: str, partidas: int = 3):
    if not pubg_client:
        await interaction.response.send_message(
            "El bot no tiene configurada la PUBG_API_KEY. Revisá el .env.", ephemeral=True
        )
        return

    partidas = max(1, min(partidas, 5))
    await interaction.response.defer()

    try:
        resultado = await pubg_client.get_favorite_weapon(jugador, num_matches=partidas)
    except PubgApiError as e:
        await interaction.followup.send(f"No pude analizar las partidas: {e}")
        return
    except Exception:
        log.exception("Error inesperado consultando PUBG API (armafavorita)")
        await interaction.followup.send("Ocurrió un error inesperado consultando la API de PUBG.")
        return

    texto = format_favorite_weapon(jugador, resultado)
    embed = discord.Embed(description=texto, color=discord.Color.dark_red())
    embed.set_footer(text="Datos: PUBG API telemetry (puede tardar unos segundos)")
    await interaction.followup.send(embed=embed)


# --- Slash command: /reiniciarsemana ---
@client.tree.command(name="reiniciarsemana", description="Reinicia manualmente el checkpoint de jugador de la semana")
@app_commands.checks.has_permissions(manage_guild=True)
async def reiniciarsemana(interaction: discord.Interaction):
    reset_weekly()
    await interaction.response.send_message("Checkpoint semanal reiniciado para todo el squad.", ephemeral=True)


# --- Slash command: /mantenimiento ---
@client.tree.command(name="mantenimiento", description="Último aviso de mantenimiento de PUBG (vía noticias de Steam)")
async def mantenimiento(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        items = await fetch_recent_news(count=15)
    except SteamNewsError as e:
        await interaction.followup.send(f"No pude consultar las noticias de Steam: {e}")
        return
    except Exception:
        log.exception("Error inesperado consultando Steam News")
        await interaction.followup.send("Ocurrió un error inesperado consultando las noticias de Steam.")
        return

    maintenance_items = [i for i in items if is_maintenance_related(i)]

    if not maintenance_items:
        await interaction.followup.send(
            "No encontré avisos de mantenimiento recientes en las noticias de Steam de PUBG."
        )
        return

    texto = format_announcement(maintenance_items[0])
    embed = discord.Embed(description=texto, color=discord.Color.orange())
    embed.set_footer(text="Fuente: noticias de Steam (no hay API oficial de PUBG para esto)")
    await interaction.followup.send(embed=embed)


# --- Loop en background: chequea avisos de mantenimiento nuevos en Steam ---
@tasks.loop(seconds=MAINTENANCE_CHECK_SECONDS)
async def check_maintenance_loop():
    try:
        new_items = await get_new_maintenance_announcements()
    except SteamNewsError:
        log.exception("Error consultando Steam News (loop)")
        return
    except Exception:
        log.exception("Error inesperado en el chequeo de mantenimiento")
        return

    if not new_items:
        return

    channel = client.get_channel(int(NOTIFY_CHANNEL_ID))
    if channel is None:
        log.warning(f"No encuentro el canal de Discord con id {NOTIFY_CHANNEL_ID}")
        return

    for item in new_items:
        texto = format_announcement(item)
        embed = discord.Embed(
            title="⚠️ Aviso de mantenimiento de PUBG",
            description=texto,
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Fuente: noticias de Steam")
        await channel.send(embed=embed)


@check_maintenance_loop.before_loop
async def before_check_maintenance_loop():
    await client.wait_until_ready()


# --- Loop en background: anuncio semanal automático del jugador de la semana ---
@tasks.loop(minutes=30)
async def check_weekly_announce_loop():
    now = datetime.now(timezone.utc)
    if now.weekday() != WEEKLY_ANNOUNCE_WEEKDAY or now.hour != WEEKLY_ANNOUNCE_HOUR_UTC:
        return
    if was_announced_this_week():
        return

    channel = client.get_channel(int(WEEKLY_ANNOUNCE_CHANNEL_ID))
    if channel is None:
        log.warning(f"No encuentro el canal de Discord con id {WEEKLY_ANNOUNCE_CHANNEL_ID}")
        return

    try:
        roster = load_roster()
    except RosterError:
        log.warning("Anuncio semanal: no hay roster configurado (squad.json o SQUAD_ROSTER)")
        return

    try:
        results = await pubg_client.get_squad_stats(roster, "squad")
    except Exception:
        log.exception("Error inesperado consultando PUBG API (anuncio semanal)")
        return

    current_stats = {r["name"]: r["stats"] for r in results if r["stats"]}
    deltas = get_weekly_deltas(current_stats)

    ranking = [
        (name, d["avg_damage"], d["rounds"])
        for name, d in deltas.items()
        if d is not None
    ]
    ranking.sort(key=lambda x: x[1], reverse=True)

    lines = []
    if ranking:
        for i, (name, avg_damage, rounds) in enumerate(ranking, start=1):
            medal = {1: "🏆", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
            lines.append(f"{medal} **{name}** — {avg_damage} dmg prom. ({rounds} partidas)")
    else:
        lines.append("Nadie del squad tuvo partidas nuevas suficientes esta semana.")

    embed = discord.Embed(
        title="📅 Jugador de la semana",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await channel.send(embed=embed)

    reset_weekly()
    mark_announced_this_week()


@check_weekly_announce_loop.before_loop
async def before_check_weekly_announce_loop():
    await client.wait_until_ready()


# --- Slash command: /ayuda ---
@client.tree.command(name="ayuda", description="Muestra los comandos disponibles del bot")
async def ayuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Comandos disponibles",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="/pubgstats <jugador> [modo]",
        value="Estadísticas lifetime de un jugador puntual. Modo por defecto: squad.",
        inline=False,
    )
    embed.add_field(
        name="/squadstats [modo]",
        value="Estadísticas de todo el squad (definido en squad.json) en una sola respuesta.",
        inline=False,
    )
    embed.add_field(
        name="/jugadordelasemana",
        value="Ranking por mejor daño promedio desde el último checkpoint (~7 días).",
        inline=False,
    )
    embed.add_field(
        name="/ultimapartida <jugador>",
        value="Resultado de la última partida jugada: mapa, posición, kills, daño, tiempo de vida.",
        inline=False,
    )
    embed.add_field(
        name="/vs <jugador1> <jugador2> [modo]",
        value="Compara las stats lifetime de dos jugadores lado a lado.",
        inline=False,
    )
    embed.add_field(
        name="/racha <jugador>",
        value="Detecta si viene de una racha de victorias o de partidas sin kills.",
        inline=False,
    )
    embed.add_field(
        name="/armafavorita <jugador> [partidas]",
        value="Arma con más kills en sus últimas partidas (analiza telemetry, puede tardar unos segundos).",
        inline=False,
    )
    embed.add_field(
        name="/mantenimiento",
        value="Último aviso de mantenimiento de PUBG encontrado en las noticias de Steam.",
        inline=False,
    )
    embed.add_field(
        name="/reiniciarsemana",
        value="Reinicia el checkpoint semanal para todo el squad (requiere permiso de Gestionar servidor).",
        inline=False,
    )
    embed.add_field(
        name="/ayuda",
        value="Muestra este mensaje.",
        inline=False,
    )
    embed.set_footer(
        text="Además: el bot anuncia solo el jugador de la semana cada domingo y avisa "
        "si hay mantenimiento nuevo de PUBG (según configuración)."
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("Falta DISCORD_TOKEN en el .env")
    client.run(DISCORD_TOKEN)
