"""
Bot de Discord con:
  - /pubgstats <jugador> [modo]  -> estadísticas lifetime de PUBG (shard steam)
  - /squadstats [modo]           -> estadísticas de todo el squad (squad.json)
  - /jugadordelasemana           -> mejor promedio de daño desde el último checkpoint
  - /ultimapartida <jugador>     -> resultado de la última partida jugada
  - /vs <jugador1> <jugador2>    -> compara stats lifetime de dos jugadores
  - /racha <jugador>             -> racha de victorias o de partidas sin kills
  - /armafavorita <jugador>      -> arma con más kills en las últimas partidas

Configuración: ver .env.example / README.md
"""

import os
import logging

import discord
from discord import app_commands
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
from squad_weekly import get_weekly_deltas, reset_all as reset_weekly

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pubg-bot")

# --- Config desde variables de entorno ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
PUBG_API_KEY = os.getenv("PUBG_API_KEY")
PUBG_SHARD = os.getenv("PUBG_SHARD", "steam")

# --- Cliente de la API de PUBG ---
pubg_client = PubgClient(api_key=PUBG_API_KEY, shard=PUBG_SHARD) if PUBG_API_KEY else None

intents = discord.Intents.default()


class PubgBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


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
        name="/reiniciarsemana",
        value="Reinicia el checkpoint semanal para todo el squad (requiere permiso de Gestionar servidor).",
        inline=False,
    )
    embed.add_field(
        name="/ayuda",
        value="Muestra este mensaje.",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise SystemExit("Falta DISCORD_TOKEN en el .env")
    client.run(DISCORD_TOKEN)
