# Bot de Discord: stats de PUBG

Bot en Python (discord.py) con estos comandos:

- `/pubgstats <jugador> [modo]`: estadísticas lifetime de PUBG de un jugador (shard Steam). Modo por defecto: `squad` (TPP).
- `/squadstats [modo]`: estadísticas de todo el squad registrado en `squad.json`, en una sola respuesta.
- `/jugadordelasemana`: calcula quién tuvo el mejor promedio de daño desde el último checkpoint (ventana móvil de ~7 días).
- `/ultimapartida <jugador>`: resultado de la partida más reciente (mapa, posición, kills, daño, tiempo de vida).
- `/vs <jugador1> <jugador2> [modo]`: compara las stats lifetime de dos jugadores lado a lado.
- `/racha <jugador>`: detecta si viene de una racha de victorias o de partidas sin kills.
- `/armafavorita <jugador> [partidas]`: arma con más kills en sus últimas partidas (analiza telemetry).
- `/mantenimiento`: último aviso de mantenimiento de PUBG encontrado en las noticias de Steam (chequeo manual).
- `/reiniciarsemana`: reinicia manualmente el checkpoint semanal (requiere permiso "Gestionar servidor").
- `/ayuda`: lista estos comandos dentro de Discord.

Además, si configurás `NOTIFY_CHANNEL_ID`, el bot chequea solo cada 30 minutos si hay un aviso de mantenimiento nuevo y lo postea en ese canal (sin que nadie tenga que pedirlo).

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

## Aviso de mantenimiento (`NOTIFY_CHANNEL_ID`)

PUBG/Krafton no tiene una API oficial para avisos de mantenimiento — los anuncian en Twitter/X, Steam y su web. El bot chequea las **noticias de Steam** (endpoint público, sin API key) y filtra las que mencionen mantenimiento/downtime. Es la fuente más confiable a la que se puede acceder por API, pero no es 100% infalible: puede tardar en aparecer si Krafton lo publica primero en otro lado, o (raramente) no detectar un aviso si no usa ninguna de las palabras clave que busca el bot.

Para activar el chequeo automático, en Discord activá el modo desarrollador (Configuración → Avanzado) y copiá el ID del canal donde querés el aviso (clic derecho sobre el canal → Copiar ID), y ponelo en `NOTIFY_CHANNEL_ID` del `.env`. Si no lo configurás, el chequeo automático queda desactivado, pero `/mantenimiento` sigue funcionando igual como comando manual.

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
- **Railway / Render**: conectás el repo de GitHub (ver pasos abajo).
- **Replit**: funciona para pruebas, pero para uso serio 24/7 conviene un VPS o Railway.

### Desplegar en Railway desde GitHub (recomendado)

1. Subí el proyecto a GitHub (ver sección de git más abajo si no lo hiciste).
2. Andá a https://railway.app y logueate con tu cuenta de GitHub.
3. **New Project** → **Deploy from GitHub repo** → elegí tu repo `pubg-discord-bot`.
4. Railway detecta que es Python y arranca el proceso con el `Procfile` que trae el proyecto (`worker: python bot.py`) — no hace falta configurar nada más ahí.
5. Andá a la pestaña **Variables** del servicio y cargá las mismas variables que tenés en tu `.env` local:
   - `DISCORD_TOKEN`
   - `PUBG_API_KEY`
   - `PUBG_SHARD` (`steam`)
   - `SQUAD_ROSTER` — **importante**: como `squad.json` no se sube al repo (está en `.gitignore` a propósito), acá tenés que definir el roster como variable de entorno, con los nombres separados por coma. Ejemplo: `SQUAD_ROSTER=dreher,DubenDoldan,aregol333,Matias533,KuxuroElDios,LaBolcholsa`
   - `NOTIFY_CHANNEL_ID` — opcional, si querés el aviso automático de mantenimiento.
6. Guardá — Railway redeploya solo y el bot debería aparecer conectado en los logs.

Railway tiene un plan gratuito con créditos limitados por mes; para que el bot ande sin cortes las 24hs de forma indefinida, en algún momento vas a necesitar pasar a un plan pago (charges por uso, generalmente unos pocos dólares al mes para un bot chico).

Cada vez que hagas `git push` a tu repo, Railway redespliega automáticamente la versión nueva.

## Notas

- Las stats que muestra el bot son **lifetime** (las mismas que "Overall" dentro del juego), no de la temporada actual — es el endpoint más simple y estable de la API de PUBG.
- `/jugadordelasemana` no depende de un cron: cada jugador tiene su propio checkpoint guardado en `weekly_snapshots.json` (se crea solo). La primera vez que corrés el comando para un jugador nuevo, ese jugador arranca su checkpoint y todavía no compite en el ranking — va a aparecer recién la próxima vez que corras el comando, comparando contra ese punto de partida. Si pasan más de 7 días entre corridas, el checkpoint de ese jugador se reinicia solo.
- Con squads grandes (varios jugadores), `/squadstats` y `/jugadordelasemana` hacen varias consultas seguidas a la API de PUBG. La key gratuita tiene un límite de ~10 requests/minuto — si lo usás muy seguido con un squad de 8-10 jugadores podés toparte con el límite (el bot te va a avisar si pasa).
- `/ultimapartida`, `/vs` (indirectamente, vía `/racha`) y `/armafavorita` usan datos de **partidas**, que la API de PUBG solo retiene los últimos **14 días**. Fuera de esa ventana no hay datos disponibles.
- `/armafavorita` descarga y analiza el archivo de telemetry de cada partida (puede pesar varios MB), así que tarda más que los otros comandos — usá pocas partidas (`partidas`, por defecto 3, máximo 5) si querés que sea más rápido.
