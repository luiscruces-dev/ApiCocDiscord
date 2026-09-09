# CLAUDE.md

Bot de Discord para stats de un clan de Clash of Clans: historial de guerras,
Clan Games, reputación por temporada y un puente a WhatsApp. Python 3 con
`discord.py` + `coc.py` sobre SQLite.

## Antes de cambiar arquitectura: lee el plan

**[`PLAN-MULTICLAN.md`](PLAN-MULTICLAN.md)** es la fuente de verdad de hacia
dónde va el proyecto. El bot es hoy **mono-clan** (un proceso = un clan = un
servidor de Discord) y hay un plan en marcha para convertirlo en multi-clan
más una web con stats, porque más de 60 clanes pidieron adquirirlo.

Léelo completo antes de tocar `storage.py`, `config.py`, `bot.py` o cualquier
loop de fondo. Trae el orden de los pasos, qué se rompe y por qué. Si haces
avances, actualiza su tabla de estado (sección 11).

## Correr el proyecto

```bash
pip install -r requirements.txt
cp .env.example .env    # completar DISCORD_TOKEN, COC_API_TOKEN, CLAN_TAG
python bot.py
```

`probar_conexion.py` verifica que las credenciales de Clash funcionen sin
levantar el bot entero.

**No hay tests todavía** — es el paso 00 del plan.

## Convenciones

- **Todo en español**: funciones, variables, tablas, docstrings y comentarios
  (`guardar_guerra`, `cagadas_avisadas`, `puntos_no_atacar`).
- **Commits en español, imperativo, sin acentos (ASCII), sin prefijos** tipo
  `feat:`. Ejemplo real: `Topear puntos de Clan Games al maximo real por
  edicion (10000)`.
- **Los comentarios explican el PORQUÉ, no el qué.** El código existente
  documenta limitaciones de la API de Supercell y decisiones no obvias.
  Mantener ese estándar y no comentar lo evidente.
- **Texto de cara al usuario en español de Venezuela**, incluido el tono
  relajado de `/cagarse`.

## Trampas conocidas

- **Los loops de fondo tienen que sobrevivir meses corriendo solos.** Capturan
  excepciones amplias y reintentan en el siguiente ciclo; nunca se mueren. Ver
  `cogs/historial_guerras.py:44` como referencia.
- **`clan_stats.db` no tiene respaldo y no se puede reconstruir desde la API.**
  Todo el historial de guerras y la reputación acumulada viven ahí. Cualquier
  operación que lo toque necesita backup previo.
- **La API de Clash es 100% de solo lectura.** Ningún comando puede repartir
  recompensas dentro del juego.
- **No existe endpoint de puntos de Clan Games.** Solo se infiere restando
  snapshots de achievements (inicio vs cierre); por eso existe toda la
  maquinaria de `clan_games_sesiones`.
- **En CWL la numeración de mapa no se corresponde entre los dos clanes**, así
  que no se puede calcular "espejo". Ya se corrigió una vez — no reintroducir.
- Caché del lado de Supercell: clan 120s, guerra 120s, CWL 600s, jugador 60s.
  Consultar más seguido no devuelve datos más frescos.
- La API se consulta a través del **proxy de RoyaleAPI**, no directo: la API
  oficial exige lista blanca de IP y la IP de casa cambia.
