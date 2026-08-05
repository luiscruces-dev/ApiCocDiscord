# ApiCocDiscord

Bot de Discord para ver stats del clan de Clash of Clans y ayudar a repartir
recompensas de forma justa (donaciones, guerra, Capital Raids), usando la
API oficial de Supercell vía [coc.py](https://github.com/mathsman5133/coc.py).

## Comandos

- `/miembros` — lista de todo el clan: rol, TH, trofeos, donaciones dadas/recibidas.
- `/donaciones` — ranking de donaciones (dadas, recibidas y ratio).
- `/capital` — ranking de oro saqueado en el último Raid Weekend.
- `/guerra` — estado de la guerra actual, ataques usados, estrellas y % de destrucción por miembro.
- `/puntaje` — ranking combinado (donaciones + guerra + capital) pensado para decidir reparto de recompensas. Los pesos de cada categoría están al inicio de [cogs/clan_stats.py](cogs/clan_stats.py) (`PESO_DONACIONES`, `PESO_GUERRA`, `PESO_CAPITAL`) — cámbialos a lo que tu clan considere justo.

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

### 4. Correr
```bash
python bot.py
```

## Limitaciones reales de la API (confirmado en el Discord oficial de la comunidad, `discord.gg/clashapi`)

- **Es 100% de solo lectura.** Ningún comando puede repartir recompensas dentro del juego — solo te dice quién se las merece según los números. La entrega la sigues haciendo tú (in-game, con un rol de Discord, etc.).
- **No hay endpoint de puntos de Clan Games.** Solo se puede inferir tomando una "foto" de los achievements de cada jugador al inicio y al final del evento y restando. No está implementado en esta primera versión — si lo quieres, es el siguiente paso natural.
- `/guerra` y `/puntaje` necesitan que el registro de guerra del clan esté en **público** (Ajustes del clan, in-game); si no, avisan en vez de fallar.
- La API cachea las respuestas del lado de Supercell: clan 120s, guerra 120s, CWL 600s, jugador 60s — no tiene sentido consultar más seguido que eso.
- Rate limit no oficial pero probado por la comunidad: ~30-40 requests/segundo.

## Recursos útiles
- Comparador de librerías/wrappers de la API: [coc-libs.vercel.app](https://coc-libs.vercel.app/)
- Servidor de Discord de la comunidad (útil para dudas de la API): [discord.gg/clashapi](https://discord.gg/clashapi)
- Docs de coc.py: [cocpy.readthedocs.io](https://cocpy.readthedocs.io/)
