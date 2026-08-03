# Bot de Discord: stats de PUBG

Bot en Python (discord.py) con estos comandos:

- `/pubgstats <jugador> [modo]`: estadísticas lifetime de PUBG de un jugador (shard Steam). Modo por defecto: `squad` (TPP).
- `/squadstats [modo]`: estadísticas de todo el squad registrado en `squad.json`, en una sola respuesta.
- `/jugadordelasemana`: calcula quién tuvo el mejor promedio de daño desde el último checkpoint (ventana móvil de ~7 días).
- `/ultimapartida <jugador>`: resultado de la partida más reciente (mapa, posición, kills, daño, tiempo de vida).
- `/vs <jugador1> <jugador2> [modo]`: compara las stats lifetime de dos jugadores lado a lado.
- `/racha <jugador>`: detecta si viene de una racha de victorias o de partidas sin kills.
- `/armafavorita <jugador> [partidas]`: arma con más kills en sus últimas partidas (analiza telemetry).
- `/reiniciarsemana`: reinicia manualmente el checkpoint semanal (requiere permiso "Gestionar servidor").
- `/ayuda`: lista estos comandos dentro de Discord.

## Roster del squad (`squad.json`)

Los nombres del squad se registran a mano en `squad.json`, en la carpeta del proyecto. Es una lista simple con los nombres **exactos** (como figuran en el juego) de cada jugador:

```json
[
  "NombreExactoEnPUBG1",
  "NombreExactoEnPUBG2",
  "NombreExactoEnPUBG3"
]
```

`squad.json` está en `.gitignore` (no se sube al repo, para no publicar los nombres reales del squad). El repo trae `squad.json.example` como plantilla — copialo y renombralo:

```
cp squad.json.example squad.json
```

Para agregar o sacar gente del squad, editá `squad.json` y guardá — no hace falta reiniciar el bot, se lee cada vez que se usa `/squadstats` o `/jugadordelasemana`. Máximo 10 jugadores (límite de una request a la API de PUBG).

## 1. Requisitos

- Python 3.10 o superior.
- Una cuenta de Discord donde tengas permisos para invitar bots (o pedirle a un admin del server que lo invite).

## 2. Crear el bot de Discord

1. Andá a https://discord.com/developers/applications y hacé clic en **New Application**. Ponele un nombre.
2. En el menú de la izquierda, andá a **Bot** → **Add Bot**.
3. En esa misma página, copiá el **Token** (botón "Reset Token" si no lo ves) — eso va en `DISCORD_TOKEN` del `.env`. **No lo compartas con nadie.**
4. Andá a **OAuth2** → **URL Generator**. Marcá los scopes `bot` y `applications.commands`. En permisos del bot marcá al menos: `Send Messages`, `Embed Links`, `Use Slash Commands`.
5. Copiá la URL generada al final de la página, abrila en el navegador y elegí el servidor donde querés invitar el bot.

## 3. Conseguir la API key de PUBG

1. Andá a https://developer.pubg.com/ y logueate con tu cuenta de PUBG (Steam/etc).
2. Creá una nueva app ("Create New App"), ponele un nombre y descripción cortos.
3. Te va a dar una API key (empieza con algo como `eyJhbGciOi...`). Copiala a `PUBG_API_KEY` en el `.env`.
4. Las keys gratuitas tienen un límite de rate (10 requests/minuto aprox.) — de sobra para un bot personal.

## 4. Configurar el `.env`

Copiá `.env.example` a `.env` y completá los valores:

```
cp .env.example .env
```

## 5. Instalar dependencias y correr el bot

```bash
python -m venv venv
source venv/bin/activate   # en Windows: venv\Scripts\activate
pip install -r requirements.txt
python bot.py
```

Si todo salió bien vas a ver en la consola `Conectado como <nombre-del-bot>`. Los comandos pueden tardar unos minutos en aparecer en Discord la primera vez (sync de slash commands).

## 6. Dejarlo corriendo 24/7

Mientras tengas la terminal abierta y `python bot.py` corriendo, el bot funciona. Para que siga andando todo el tiempo sin tener tu PC prendida, alguna opción:

- **VPS barato** (DigitalOcean, Hetzner, etc.): subís los archivos, instalás dependencias, y corrés el bot con `screen`, `tmux` o como servicio systemd.
- **Railway / Render**: conectás el repo de GitHub y lo configurás como "worker" (no como web service), seteando las variables de entorno del `.env` en su panel.
- **Replit**: funciona para pruebas, pero para uso serio 24/7 conviene un VPS o Railway.

## Notas

- Las stats que muestra el bot son **lifetime** (las mismas que "Overall" dentro del juego), no de la temporada actual — es el endpoint más simple y estable de la API de PUBG.
- `/jugadordelasemana` no depende de un cron: cada jugador tiene su propio checkpoint guardado en `weekly_snapshots.json` (se crea solo). La primera vez que corrés el comando para un jugador nuevo, ese jugador arranca su checkpoint y todavía no compite en el ranking — va a aparecer recién la próxima vez que corras el comando, comparando contra ese punto de partida. Si pasan más de 7 días entre corridas, el checkpoint de ese jugador se reinicia solo.
- Con squads grandes (varios jugadores), `/squadstats` y `/jugadordelasemana` hacen varias consultas seguidas a la API de PUBG. La key gratuita tiene un límite de ~10 requests/minuto — si lo usás muy seguido con un squad de 8-10 jugadores podés toparte con el límite (el bot te va a avisar si pasa).
- `/ultimapartida`, `/vs` (indirectamente, vía `/racha`) y `/armafavorita` usan datos de **partidas**, que la API de PUBG solo retiene los últimos **14 días**. Fuera de esa ventana no hay datos disponibles.
- `/armafavorita` descarga y analiza el archivo de telemetry de cada partida (puede pesar varios MB), así que tarda más que los otros comandos — usá pocas partidas (`partidas`, por defecto 3, máximo 5) si querés que sea más rápido.
