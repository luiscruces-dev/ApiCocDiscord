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
- `/capital` 📱 — ranking de oro saqueado en el último Raid Weekend. Si el Raid Weekend sigue abierto, agrega un recordatorio al final con quién todavía le faltan ataques de Capital (incluye a quien no ha atacado nada, que la API ni siquiera lista); en WhatsApp etiqueta de verdad a quien esté vinculado con `/vincular`, igual que `/recordar`.
- `/guerra` 📱 — estado de la guerra actual, ataques usados, estrellas y % de destrucción por miembro.
- `/rival` 📱 — lo mismo pero del lado del rival: bases enemigas (TH, ataques recibidos, estrellas, % destrucción) con su "espejo" del propio clan (mismo `map_position`), más un balance de cuántos TH tiene cada bando.
- `/estimacion` 📱 — proyección de estrellas de la guerra actual: los ataques ya hechos cuentan real, los pendientes se estiman contra el espejo según el historial del clan por diferencia de TH (primero el del propio jugador si tiene suficiente muestra, si no el del clan entero). Sin historial a esa diferencia, lo dice en vez de inventar un número — con pocas guerras guardadas todavía, la estimación va a ser floja.
- `/historial` 📱 — últimas guerras guardadas por el bot. Apenas termina cada guerra, un loop de fondo la guarda y de paso anuncia resultado + MVP (más estrellas, empate por destrucción promedio) + quién no atacó, en el grupo de WhatsApp (requiere el puente configurado, ver "Puente a WhatsApp" más abajo).
- `/kda` 📱 — estadísticas acumuladas de ataque/defensa por jugador, de las guerras guardadas hasta ahora.
- `/clangames iniciar` / `/clangames cerrar` — miden los puntos de Clan Games a mano (la API solo da el acumulado de toda la vida, no el del evento actual — ver "Limitaciones" más abajo). También se disparan solos: un loop de fondo revisa la fecha (calendario fijo 22-28 de cada mes, UTC) y abre/cierra la medición automáticamente, avisando en el canal que configures con `CLAN_GAMES_CHANNEL_ID` en `.env`. Exclusivo de Discord a propósito: cambian estado, no se exponen por WhatsApp.
- `/clangames progreso` 📱 — cuánto lleva cada quien desde que arrancó la medición actual, sin cerrarla (compara la foto de ahora contra el punto de partida de `/clangames iniciar`). Si no hay ninguna medición abierta, avisa en vez de fallar. En WhatsApp se escribe `/clangames`.
- `/reputacion` 📱 — ranking de reputación de la temporada actual. Con `temporada:` (autocomplete en Discord con las temporadas guardadas; en WhatsApp se escribe la fecha tal cual, ej. `/reputacion 2026-07-27`) muestra el ranking final de una temporada pasada. La fórmula (pesos, multiplicadores por diferencia de TH, penalizaciones) está en [reputacion.py](reputacion.py). Apenas Clash resetea la temporada oficial (último lunes del mes), un loop de fondo se da cuenta solo y anuncia el podio final (top 3) de la que acaba de cerrar, en el grupo de WhatsApp.
- `/ayudarep` 📱 — el bot explica en el propio Discord cómo funciona el sistema de reputación.
- `/enviarwsp mensaje:` — reenvía un texto al grupo de WhatsApp del clan (requiere el puente de `whatsapp-bridge/`, ver más abajo). Solo para quienes pueden gestionar el servidor.
- `/tags` 📱 — nombre y tag de cada miembro del clan, marcando quién todavía no vinculó su número (⚠️ sin vincular), para que cualquiera ubique el suyo y lo use en `/vincular`.
- `/perfil <jugador>` 📱 — vista completa de una persona en un solo bloque: reputación de la temporada (por categoría), KDA histórico de guerra, donaciones en vivo y capital del último Raid Weekend. En Discord `jugador` tiene autocomplete por nombre; en WhatsApp se escribe el tag o el nombre tal cual (ej. `/perfil jeho`). Si no hay datos en alguna sección (recién vinculado, sin guerras guardadas, etc.) avisa "sin datos todavía" en vez de omitirla.
- `/comandos` 📱 — lista todos los comandos disponibles del bot (se genera solo, no hay que mantenerla a mano).
- `/cagarse <victima>` 📱 — comando de relajo: le tira un roast al azar (tono venezolano) a quien se mandó una cagada atacando. En Discord `victima` es una mención real (`@alguien`) y hay un `motivo` opcional; en WhatsApp se escribe el nombre tal cual, se menciona con "@" en el propio texto, o se cita/responde su mensaje (el motivo va después de un `|`, ej. `/cagarse Fulano | dejó el rey en la casa`). Puro chiste entre panas, no toca nada del clan. Además, un loop de fondo revisa la guerra activa cada 10 min y manda un mensaje automático al grupo de WhatsApp en tres casos, cada uno con su tono: ataca hacia arriba (TH rival más alto) y saca 2+ estrellas → elogio ("bien ataque, compai"), ahí sí hay mérito; ataca hacia abajo (TH rival más bajo) y no saca pleno → tono de "trátame en serio" (no hay excusa de dificultad); ataca parejo o hacia abajo y saca 0 o 1 estrella → la cagada normal de siempre. Atacar hacia arriba con 0-1 estrella no dispara nada (es lo esperable). Cada ataque se avisa una sola vez. Si alguien cita o menciona al propio bot como "víctima" (para que se autoinsulte), el chiste se le devuelve a quien lo intentó o, la mitad de las veces, a otro miembro vinculado al azar. Aparte, y solo durante CWL, otro loop (cada 5 min) manda un reporte neutral de cada ataque nuestro (quién atacó, a quién y el resultado, con la numeración de los dos lados) — sin roast ni elogio, porque en liga la numeración no se corresponde entre clanes y cuesta más seguir quién atacó a quién a simple vista (ver nota de "espejo" en `/rival`).

Estos tres son exclusivos de WhatsApp (no existen como slash command de Discord, no tendría sentido ahí):

- `/vincular <tag>` — asocia tu número de WhatsApp con un tag de jugador, para que `/recordar` te pueda etiquetar directo. Relación muchos-a-muchos: soporta multicuenta (mandalo de nuevo con otro tag y se suma, no reemplaza el anterior) y también cuenta compartida (ej. una pareja jugando desde el mismo tag — si los dos se vinculan a esa cuenta, a los dos les llega la mención). Única excepción a "solo lectura": no afecta al clan, en el peor caso te vinculás con el tag equivocado y lo corregís mandando el comando de nuevo.
- `/desvincular` — sin argumento deshace todos tus vínculos; con `/desvincular <tag>` deshace solo esa cuenta.
- `/recordar` — durante una guerra activa, lista quién le falta atacar; a quien esté vinculado lo etiqueta con una mención real de WhatsApp (no solo texto). Además de a pedido, tres loops de fondo avisan solos: uno manda un chiste ("preparen esas nalgas...") cuando faltan 30 min o menos para que arranque la guerra (mientras siga en día de preparación); otro manda un aviso especial ("hemos iniciado guerra") una sola vez apenas arranca; y el último repite el recordatorio normal cada 4h mientras siga activa y falte alguien por atacar. Los tres son silenciosos el resto del tiempo (no avisan "no hay guerra" seguido).

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
