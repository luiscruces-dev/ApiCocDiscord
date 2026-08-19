# ApiCocDiscord

Bot de Discord para ver stats del clan de Clash of Clans y ayudar a repartir
recompensas de forma justa. Lleva historial de guerras, Clan Games y un
sistema de reputación por temporada (guerra + donaciones + capital + clan
games combinados), usando la API oficial de Supercell vía
[coc.py](https://github.com/mathsman5133/coc.py).

## Comandos

Los marcados con 📱 también funcionan escribiéndolos tal cual en el grupo de
WhatsApp configurado (ver "Puente a WhatsApp" más abajo).

- `/miembros` 📱 — lista de todo el clan: rol, TH, trofeos, donaciones dadas/recibidas.
- `/donaciones` 📱 — ranking de donaciones (dadas, recibidas y ratio).
- `/capital` 📱 — ranking de oro saqueado en el último Raid Weekend.
- `/guerra` 📱 — estado de la guerra actual, ataques usados, estrellas y % de destrucción por miembro.
- `/historial` 📱 — últimas guerras guardadas por el bot.
- `/kda` 📱 — estadísticas acumuladas de ataque/defensa por jugador, de las guerras guardadas hasta ahora.
- `/clangames iniciar` / `/clangames cerrar` — miden los puntos de Clan Games a mano (la API solo da el acumulado de toda la vida, no el del evento actual — ver "Limitaciones" más abajo). También se disparan solos: un loop de fondo revisa la fecha (calendario fijo 22-28 de cada mes, UTC) y abre/cierra la medición automáticamente, avisando en el canal que configures con `CLAN_GAMES_CHANNEL_ID` en `.env`. Exclusivo de Discord a propósito: cambia estado, no se expone por WhatsApp.
- `/reputacion` 📱 — ranking de reputación de la temporada actual. Con `temporada:` (autocomplete en Discord con las temporadas guardadas; en WhatsApp se escribe la fecha tal cual, ej. `/reputacion 2026-07-27`) muestra el ranking final de una temporada pasada. La fórmula (pesos, multiplicadores por diferencia de TH, penalizaciones) está en [reputacion.py](reputacion.py).
- `/ayudarep` 📱 — el bot explica en el propio Discord cómo funciona el sistema de reputación.
- `/enviarwsp mensaje:` — reenvía un texto al grupo de WhatsApp del clan (requiere el puente de `whatsapp-bridge/`, ver más abajo). Solo para quienes pueden gestionar el servidor.
- `/tags` 📱 — nombre y tag de cada miembro del clan, marcando quién todavía no vinculó su número (⚠️ sin vincular), para que cualquiera ubique el suyo y lo use en `/vincular`.
- `/comandos` 📱 — lista todos los comandos disponibles del bot (se genera solo, no hay que mantenerla a mano).

Estos tres son exclusivos de WhatsApp (no existen como slash command de Discord, no tendría sentido ahí):

- `/vincular <tag>` — asocia tu número de WhatsApp con un tag de jugador, para que `/recordar` te pueda etiquetar directo. Soporta multicuenta: mandalo de nuevo con otro tag y se suma, no reemplaza el anterior. Única excepción a "solo lectura": no afecta al clan, en el peor caso te vinculás con el tag equivocado y lo corregís mandando el comando de nuevo.
- `/desvincular` — sin argumento deshace todos tus vínculos; con `/desvincular <tag>` deshace solo esa cuenta.
- `/recordar` — durante una guerra activa, lista quién le falta atacar; a quien esté vinculado lo etiqueta con una mención real de WhatsApp (no solo texto). Además de a pedido, dos loops de fondo avisan solos: uno manda un aviso especial ("hemos iniciado guerra") una sola vez apenas arranca cada guerra, y otro repite el recordatorio normal cada 4h mientras siga activa y falte alguien por atacar. Los dos son silenciosos el resto del tiempo (no avisan "no hay guerra" seguido).

## Persistencia

Guerras, Clan Games y reputación se guardan en `clan_stats.db` (SQLite, se
crea sola en la carpeta del proyecto la primera vez que corre el bot). Si se
borra ese archivo se pierde todo el historial y la reputación acumulada de
las temporadas — no hay forma de reconstruirlo desde la API, así que
conviene incluirlo en el backup del servidor donde corra el bot.

## Setup

### 1. Crear el bot de Discord
1. Ve a la [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Pestaña **Bot** → **Reset Token** → copia el token (va en `DISCORD_TOKEN`). No lo compartas con nadie.
3. Pestaña **OAuth2 → URL Generator**: marca los scopes `bot` y `applications.commands`. En permisos basta con `Send Messages` y `Embed Links`.
4. Abre la URL generada e invita el bot a tu servidor.

### 2. Conseguir la API key de Clash of Clans
1. Entra a [developer.clashofclans.com](https://developer.clashofclans.com) con tu cuenta.
2. **Create New Key**.
3. En **Allowed IP Address** pon `45.79.218.79` — **no** la IP de tu casa. Esa IP es la del proxy de [RoyaleAPI](https://docs.royaleapi.com/proxy.html), que este bot usa por defecto para que no se rompa cuando tu IP de casa cambie (típico si corres el bot desde tu PC, no un VPS con IP fija).
4. Copia el token generado → `COC_API_TOKEN`.

### 3. Configurar
```bash
pip install -r requirements.txt
```
Copia `.env.example` a `.env` y completa:
- `DISCORD_TOKEN`, `COC_API_TOKEN` (de los pasos anteriores)
- `CLAN_TAG` (con el `#`, ej. `#2ABC123XY`)
- `GUILD_ID` (opcional, recomendado en desarrollo: activa el modo desarrollador en Discord y copia el ID de tu servidor, así los slash commands aparecen al instante en vez de tardar ~1h)
- `CLAN_GAMES_CHANNEL_ID` (opcional, ID del canal donde el bot avisa cuando abre/cierra la medición automática de Clan Games)

### 4. Correr
```bash
python bot.py
```

## Puente a WhatsApp

`/enviarwsp` reenvía mensajes a un grupo de WhatsApp a través de un servicio
aparte, [`whatsapp-bridge/`](whatsapp-bridge/) (Node.js), pensado para correr
en un servidor propio 24/7 (no en el mismo hosting compartido del bot de
Discord — ver el README de esa carpeta para el por qué). Sin
`WHATSAPP_BRIDGE_URL` / `WHATSAPP_BRIDGE_TOKEN` en `.env`, el comando sigue
existiendo pero avisa que no está configurado en vez de fallar.

También funciona al revés: si alguien escribe `/miembros`, `/guerra`, etc.
directo en el grupo de WhatsApp, el puente le pide la respuesta a este bot
(vía una API interna en `127.0.0.1`, protegida con `BOT_API_TOKEN`) y
contesta ahí mismo. Solo los comandos de solo lectura están disponibles por
WhatsApp — los que cambian estado (`/clangames iniciar`/`cerrar`) siguen
siendo exclusivos de Discord. Sin `BOT_API_TOKEN` en `.env`, esta API
interna ni arranca y el grupo simplemente no responde a comandos.

## Limitaciones reales de la API (confirmado en el Discord oficial de la comunidad, `discord.gg/clashapi`)

- **Es 100% de solo lectura.** Ningún comando puede repartir recompensas dentro del juego — solo te dice quién se las merece según los números. La entrega la sigues haciendo tú (in-game, con un rol de Discord, etc.).
- **No hay endpoint de puntos de Clan Games.** Solo se puede inferir tomando una "foto" de los achievements de cada jugador al inicio y al final del evento y restando — así lo resuelve `/clangames` (ver Comandos).
- `/guerra`, `/historial`, `/kda` y `/reputacion` necesitan que el registro de guerra del clan esté en **público** (Ajustes del clan, in-game); si no, avisan en vez de fallar.
- La API cachea las respuestas del lado de Supercell: clan 120s, guerra 120s, CWL 600s, jugador 60s — no tiene sentido consultar más seguido que eso.
- Rate limit no oficial pero probado por la comunidad: ~30-40 requests/segundo.

## Recursos útiles
- Comparador de librerías/wrappers de la API: [coc-libs.vercel.app](https://coc-libs.vercel.app/)
- Servidor de Discord de la comunidad (útil para dudas de la API): [discord.gg/clashapi](https://discord.gg/clashapi)
- Docs de coc.py: [cocpy.readthedocs.io](https://cocpy.readthedocs.io/)
