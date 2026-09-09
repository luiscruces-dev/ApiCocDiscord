# Plan multi-clan — de un clan a sesenta

> **Para quien lea esto en frío (humano o sesión nueva de Claude):** este
> documento es la fuente de verdad de hacia dónde va el proyecto. Explica qué
> hay hoy, qué se rompe al meter más clanes, y en qué orden hay que tocarlo.
> Léelo completo antes de escribir código. Al final están las convenciones del
> repo y el estado real de avance.

**Estado a la fecha de este documento: nada de este plan está implementado.**
El código en `master` sigue siendo el bot mono-clan de siempre. Este archivo
es planificación, no descripción de lo que existe.

---

## 1. El contexto de negocio

El bot nació como herramienta interna del clan **Élite 21** (Clash of Clans).
Funciona bien y se corrió la voz: **más de 60 clanes escribieron pidiendo
adquirirlo**. El problema es que nunca fue diseñado para servir a más de un
clan.

La idea de producto acordada con el equipo (propuesta original de AJ) es
**freemium en dos fases**:

- **Fase 1 — gratis.** Una página web con stats y charts, más el bot de
  Discord, sirviendo a muchos clanes desde una sola instalación. Sin WhatsApp.
- **Fase 2 — de pago.** El puente de WhatsApp como suscripción mensual.

El razonamiento de por qué WhatsApp es el escalón de pago y no parte del
combo base está en la sección 4.4: no es una decisión comercial arbitraria,
es que es la pieza con más riesgo operativo real.

---

## 2. Inventario del código actual

Repositorio: `luiscruces-dev/apicocdiscord`. Python 3, `discord.py` + `coc.py`,
SQLite. ~3.458 líneas contando el puente de WhatsApp.

| Archivo | Líneas | Qué hace |
|---|---:|---|
| `storage.py` | 618 | Todo el acceso a SQLite: schema, migraciones a mano, consultas |
| `cogs/cagarse.py` | 349 | Roasts automáticos + 2 loops (ataques normales y CWL) |
| `cogs/vinculos.py` | 319 | Vínculos WhatsApp↔tag, `/recordar` + 3 loops de aviso |
| `cogs/clan_stats.py` | 226 | `/miembros`, `/donaciones`, `/capital`, `/guerra`, `/rival`, `/tags` |
| `cogs/clan_games.py` | 218 | Medición de Clan Games + loop de apertura/cierre automático |
| `cogs/reputacion.py` | 203 | `/reputacion`, `/ayudarep` + 3 loops |
| `cogs/historial_guerras.py` | 147 | `/historial`, `/kda` + loop que guarda guerras terminadas |
| `cogs/estimacion.py` | 142 | `/estimacion` — proyección de estrellas |
| `cogs/perfil.py` | 132 | `/perfil` — vista consolidada de un jugador |
| `api_interna.py` | 86 | HTTP en `127.0.0.1` que el puente de WhatsApp consulta |
| `bot.py` | 73 | Arranque, carga de cogs, login a la API de Clash |
| `utils.py` | 72 | Paginación de mensajes de Discord, helper de guerra |
| `reputacion.py` | 68 | Fórmula de reputación — **cálculo puro, sin I/O** |
| `whatsapp.py` | 61 | Cliente HTTP del puente + traducción de markdown |
| `passenger_wsgi.py` | 42 | Hack para correr el bot en hosting compartido |
| `config.py` | 39 | Variables de entorno |
| `whatsapp-bridge/index.js` | 375 | Puente Node.js (WhatsApp no oficial), servicio aparte |

### Dependencias y servicios externos

- **API oficial de Clash of Clans** vía `coc.py`, a través del **proxy de
  RoyaleAPI** (`https://cocproxy.royaleapi.dev/v1`). El proxy existe porque
  la API de Supercell exige lista blanca de IP y la IP de casa cambia.
- **Discord** vía `discord.py`, con `Intents.default()` — **sin intents
  privilegiados**, dato importante para la verificación (sección 7.1).
- **WhatsApp** vía librería no oficial en el puente Node.

---

## 3. Lo que NO es el problema: la API de Clash

Conviene dejarlo zanjado porque es el miedo que aparece primero en cada
conversación.

La API de Clash **no va a ser el cuello de botella**, y el argumento es
aritmético, no una impresión:

**Carga actual, por clan y por hora** (sumando los 10 loops de fondo):

| Loop | Archivo | Intervalo | Requests/hora |
|---|---|---|---:|
| `revisar_ataques_cwl` | `cogs/cagarse.py:291` | 5 min | 12 |
| `revisar_ataques` | `cogs/cagarse.py:215` | 10 min | 6 |
| `revisar_guerra` | `cogs/historial_guerras.py:44` | 10 min | 6 |
| `aviso_pre_guerra` | `cogs/vinculos.py:201` | 10 min | 6 |
| `aviso_inicio_guerra` | `cogs/vinculos.py:238` | 10 min | 6 |
| `revisar_clan_games` | `cogs/clan_games.py:160` | 15 min | 4 |
| `revisar_capital` | `cogs/reputacion.py:131` | 30 min | 2 |
| `sincronizar_donaciones` | `cogs/reputacion.py:117` | 1 h | 1 |
| `revisar_cierre_temporada` | `cogs/reputacion.py:154` | 1 h | ~1 |
| `recordatorio_automatico` | `cogs/vinculos.py:276` | 4 h | 0,25 |
| **Total** | | | **~44 req/hora/clan** |

- 60 clanes × 44 req/h = 2.640 req/h = **0,74 requests por segundo**.
- Techo medido por la comunidad (`discord.gg/clashapi`): **30–40 req/s**.
- **Utilización: ~2%.** Sigue sobrando margen a 500 clanes (~6 req/s).

Además, Supercell **cachea del lado suyo**: clan 120s, guerra 120s, CWL 600s,
jugador 60s. Pedir más seguido que eso no devuelve datos más frescos. El
techo real de frescura lo pone ese caché, no nuestra capacidad de pedir.

**Conclusión:** cualquier propuesta que empiece por "hay que repartir la
carga de la API entre varias llaves" está resolviendo un problema que no
tenemos. Un solo token por el proxy alcanza y sobra.

> Nota sobre desperdicio: hoy **cinco loops distintos** llaman
> `get_current_war()` del mismo clan sin compartir nada entre ellos. No es un
> problema de límites, pero sí de eficiencia — se arregla con el caché del
> paso 02.

---

## 4. Lo que SÍ es el problema

### 4.1 El schema asume que existe un solo clan en el mundo

**Ninguna de las 13 tablas tiene columna de clan.** Seis restricciones
colisionan entre clanes. Tres de ellas rompen de forma **garantizada** apenas
entre el segundo clan — no "a veces", no "bajo carga": siempre.

| Tabla | Restricción actual | Por qué colisiona | Tipo |
|---|---|---|---|
| `raid_weekends` | `start_time TEXT NOT NULL UNIQUE` | Los Raid Weekends arrancan **a la misma hora para todos los clanes del juego**. El primero que guarde bloquea a los otros 59: nadie más registra capital ni suma esos puntos de reputación. | **Dura** |
| `avisos_temporada_cerrada` | `temporada TEXT PRIMARY KEY` | Las temporadas son globales del juego. El primer clan marca `2026-09` como avisada y los demás **nunca reciben su podio**. | **Dura** |
| `recordatorios_automaticos` | `id INTEGER PRIMARY KEY CHECK (id = 1)` | Literalmente **una fila para toda la plataforma**. Un clan manda su recordatorio y silencia a los otros 59 por 4 horas. | **Dura** |
| `clan_games_sesiones` | `sesion_clan_games_abierta()` hace `ORDER BY id DESC LIMIT 1` sin filtro | Devuelve la sesión abierta de *cualquier* clan. Un clan cierra la medición de otro y le escribe encima los snapshots. | Silenciosa |
| `reputacion_eventos` | `clave TEXT UNIQUE`, formada como `{temporada}:{tag}:donaciones` | Un jugador en dos clanes de la plataforma (multicuenta, o que se cambió de clan) **sobrescribe sus donaciones de un clan con las del otro**. | Silenciosa |
| `wars` / `ataques` | `UNIQUE(end_time, opponent_tag)`; `stats_por_jugador()` hace `SELECT ... FROM ataques` sin filtro | Dos clanes nuestros contra el mismo rival a la misma hora (normal dentro de un grupo de CWL). Y el KDA sale **sumando los ataques de todos los clanes**. | Silenciosa |

Las **duras** tiran error y no guardan. Las **silenciosas** son peores:
guardan datos mezclados sin avisar a nadie.

Las tablas restantes (`avisos_inicio_guerra`, `avisos_pre_guerra`,
`cagadas_avisadas`, `ataques_cwl_avisados`, `vinculos_wa`) colisionan por la
misma razón de fondo y se arreglan con el mismo cambio: `clan_id` como parte
de cada clave.

### 4.2 La lógica está fusionada con la presentación

Este es el obstáculo real para la web, y ya duele hoy.

- `cogs/clan_stats.py:41` — `_lineas_miembros()` consulta la API **y arma
  markdown de Discord** (`**negrita**`, backticks) en el mismo método.
- `whatsapp.py:26` — `formatear_para_whatsapp()` existe únicamente para
  **traducir con expresiones regulares** ese markdown de Discord al formato de
  WhatsApp. Es un parche sobre el acoplamiento.
- `cogs/clan_stats.py:86` — `_lineas_capital()` arma las menciones de WhatsApp
  dentro del mismo método que sirve al `/capital` de Discord, que después
  **las descarta** (`cogs/clan_stats.py:153`).
- `utils.py:20` — `obtener_guerra_o_mensaje()` recibe el cliente de Clash por
  parámetro pero lee `config.CLAN_TAG` por dentro.

Una web necesita **datos**, no cadenas con `**asteriscos**`. Sin separar esto,
la web obliga a duplicar la lógica de negocio.

### 4.3 Un proceso = un clan = un servidor de Discord

`config.py` exige `CLAN_TAG`, `DISCORD_TOKEN` y `GUILD_ID` como variables de
entorno fijas al arranque. Dar de alta un clan hoy significa: clonar el
proyecto, crear una aplicación de Discord nueva, y levantar otro proceso.
Sesenta clanes = sesenta procesos, sesenta tokens, sesenta archivos `.db`
sueltos.

Además, cada cog abre **su propia conexión SQLite** (`storage.conectar()` en
cada `__init__`), o sea 6+ conexiones al mismo archivo por proceso.

### 4.4 El hosting es un parche, y el WhatsApp es el riesgo grande

`passenger_wsgi.py` arranca el bot **en un hilo dentro de un worker WSGI** de
hosting compartido tipo cPanel. Es un truco ingenioso para sostener un proceso
asyncio donde no se supone que corra, pero el hosting puede reciclar ese worker
sin avisar. No hay forma sana de correr 60 así.

El **puente de WhatsApp** usa una librería **no oficial** (no la API de
WhatsApp Business): se conecta como si fuera un celular. Replicarlo 60 veces
no es un problema de capacidad, es **riesgo de baneo de los números**. Eso no
se arregla con más servidores. Por eso WhatsApp queda como opción de pago que
cada clan activa con su propio número, no como parte del combo por defecto.

### 4.5 Cero tests

No hay ni un test en el repositorio. `reputacion.py` es cálculo puro (fórmula
de puntos por ataque, defensa, donaciones, capital, clan games) y **nadie lo
verifica**. Si se corrompe durante la migración, se descubre al cierre de
temporada, cuando el podio salga mal.

---

## 5. Arquitectura objetivo

```
┌──────────────────┬──────────────────┬──────────────────┐
│  Bot de Discord  │     API web      │ Worker de loops  │
│                  │                  │                  │
│ 1 proceso,       │ FastAPI.         │ Los 10 loops     │
│ N servidores.    │ Discord OAuth.   │ salen de los     │
│ guild_id →       │ Gating de plan   │ cogs. Itera      │
│ clan_id en cada  │ free/pro en un   │ clanes activos   │
│ comando.         │ solo middleware. │ con jitter.      │
└────────┬─────────┴────────┬─────────┴────────┬─────────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────┐
│  core/  — servicios, cliente de Clash, presentadores    │
│                                                          │
│  Los servicios devuelven dataclasses, NUNCA strings.    │
│  presentadores/discord.py · texto.py · json.py           │
│  Cliente de Clash con caché por clan_tag.                │
└────────────────────────────┬────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────┐
│  Postgres — clan_id en todas las tablas                 │
│                                                          │
│  Capa de repositorio donde clan_id es el PRIMER          │
│  argumento obligatorio de cada función. Nada de SQL      │
│  crudo en los cogs.                                      │
└─────────────────────────────────────────────────────────┘
```

La pieza clave no es Postgres ni la web: es **extraer `core/`**. Es lo que
permite que Discord, la web y (en fase 2) WhatsApp consuman la misma lógica
sin duplicarla.

---

## 6. Fase 1 — siete pasos en orden de dependencia

Cada paso habilita el siguiente; el orden no es negociable sin volver a
pensarlo. Los tamaños son **estimaciones gruesas de trabajo enfocado**, no
compromisos de calendario. Total realista: **6 a 9 semanas**.

### Paso 00 — Red de seguridad · 1–2 días

Tests de caracterización antes de tocar nada.

- `reputacion.py` primero: es cálculo puro, tests triviales de escribir y de
  valor altísimo. Congelar la fórmula actual con casos concretos.
- Tests sobre las consultas de `storage.py` **con dos clanes cargados** — esos
  mismos tests son los que después prueban que el aislamiento funciona.

**Toca:** `tests/` (nuevo), `reputacion.py`, `storage.py`

**Por qué primero:** sin esto, todo lo demás es cirugía a ciegas sobre datos
que no se pueden reconstruir desde la API.

### Paso 01 — Postgres y `clan_id` en todo el schema · 1–1,5 semanas

Tabla nueva `clanes` como registro de inquilinos:

```
clanes(
  id, clan_tag, nombre, guild_id, plan,
  canal_avisos_id, activo, creado_en
)
```

Después, `clan_id` en las 13 tablas de datos, **dentro de cada UNIQUE y cada
PRIMARY KEY** — no como columna suelta al final. Aquí se arreglan las seis
colisiones de la sección 4.1.

Cambio de forma más importante: **cada función de `storage.py` recibe
`clan_id` como primer argumento obligatorio.** Un `WHERE` olvidado es una fuga
de datos entre clientes, y la firma de la función es lo que lo previene.

Script de migración del `clan_stats.db` actual asignando todo el historial a
Élite 21. **Ese historial es la prueba de valor del producto:** backup antes,
migración en paralelo, verificar, y recién entonces cortar.

**Toca:** `storage.py` (618 líneas, reescritura casi completa),
`migraciones/` (nuevo), los 6 cogs que abren conexión propia

### Paso 02 — Extraer `core/` · 1,5–2 semanas

El paso más grande, y el que habilita la web sin duplicar lógica.

- `core/servicios/` — `guerra`, `reputacion`, `clan_games`, `capital`,
  `perfil`. Devuelven estructuras de datos.
- `presentadores/` — `discord.py`, `texto.py`, `json.py`. Visten los datos
  según el destino.
- `core/coc.py` — cliente con **caché por `clan_tag`**, que resuelve el
  desperdicio de los cinco loops pidiendo la misma guerra.
- Los cogs quedan finos: piden al servicio, entregan al presentador.

**Toca:** `core/` (nuevo), `presentadores/` (nuevo), los 10 cogs, `utils.py`

### Paso 03 — Bot multi-servidor · 3–5 días

- Cada comando resuelve su clan desde `interaction.guild_id`.
- `/configurar` restringido a administradores del servidor, para dar de alta.
- Mensaje claro (no un error) cuando el servidor no está configurado todavía.
- Se acaba `GUILD_ID`: **sync global** de slash commands, una vez para todos.

**Toca:** `bot.py`, `config.py`, todos los cogs

### Paso 04 — Worker de loops por clan · 4–6 días

Los 10 `@tasks.loop` salen de los cogs a un planificador que recorre clanes
activos. Tres cosas que hoy no existen y a 60 clanes son obligatorias:

1. **Escalonado con jitter** — si no, los 60 disparan en el segundo cero de
   cada intervalo. (Ya existe `whatsapp.esperar_jitter()`, pero con otro
   propósito: parecer humano. Es distinto.)
2. **Aislamiento de error por clan** — que el registro de guerra privado de
   uno no mate el loop de los otros 59.
3. **Canal de avisos por clan** — hoy es la variable de entorno
   `CLAN_GAMES_CHANNEL_ID`; pasa a la tabla `clanes`.

**Toca:** `worker/` (nuevo), `historial_guerras.py`, `clan_games.py`,
`reputacion.py`, `vinculos.py`, `cagarse.py`

### Paso 05 — API web y autenticación · ~1 semana

FastAPI encima de los servicios del paso 02.

**Login con Discord OAuth**, no usuarios y contraseñas propios: ya son
usuarios de Discord, evita custodiar credenciales, y de paso prueba que quien
entra realmente administra ese servidor.

El gating del plan free vive en **un solo middleware**, no repartido por
endpoint — es lo que permite vender el plan pro después sin tocar lógica.

**Toca:** `api/` (nuevo), reemplaza `api_interna.py`

### Paso 06 — Front con charts e infraestructura · 1,5–2 semanas

Los charts que pidió AJ: reputación por temporada, KDA histórico, donaciones,
historial de guerras.

Las limitaciones del plan gratis son **decisión de producto, no técnica** —
se deciden aquí. Propuesta de partida: últimas 3 guerras, temporada actual
solamente, sin exportar.

Cierre de infraestructura: VPS con Docker Compose (bot, api, worker, postgres,
proxy inverso), fuera Passenger. **Backups de Postgres desde el día uno** —
hoy el historial entero vive en un `.db` suelto sin respaldo, y el propio
README advierte que no se puede reconstruir desde la API.

**Toca:** `web/` (nuevo), `docker-compose.yml` (nuevo), elimina
`passenger_wsgi.py`

---

## 7. Decisiones

### 7.1 Verificación de Discord — PENDIENTE, con plazo externo

Un bot **sin verificar tiene techo de 100 servidores**. Con 60 clanes arrancan
al 60% del límite, y el trámite tarda semanas.

**Recomendación: arrancar la verificación ya, en paralelo al desarrollo.** A
favor: el bot usa `Intents.default()`, sin intents privilegiados, que es el
caso simple de aprobar.

### 7.2 Prueba de propiedad del clan — PENDIENTE

Hoy cualquiera podría configurar el tag de cualquier clan y ver sus stats.
Para un producto que se cobra, eso no va.

**Recomendación:** usar `/players/{tag}/verifytoken` de la API oficial — el
líder pega el token que le da el juego y queda probado. Es el estándar de la
comunidad para esto.

### 7.3 Un solo token de Clash — DECIDIDO

No hace falta repartir la carga. A 0,74 req/s contra un techo de 30–40, un
token por el proxy de RoyaleAPI sobra. Revisar recién pasando los 500 clanes.

### 7.4 Aislamiento entre clientes — DECIDIDO

El riesgo más caro del proyecto no es caerse: es **mostrarle a un clan los
datos de otro**. Se pierde la confianza de los 60 de una sola vez.

Mitigación en dos capas: repositorio que exige `clan_id` por firma de función,
y la batería de tests del paso 00 corriendo siempre con dos clanes cargados.

---

## 8. Fase 2 — los ganchos que se dejan puestos en fase 1

El objetivo es que la fase 2 sea **aprovisionar y cobrar**, no volver a abrir
el código. Estas cuatro cosas se hacen *durante* la fase 1 aunque nadie las
use todavía, porque hacerlas después significa tocar lo mismo dos veces:

1. **Config de WhatsApp por clan en base de datos**, no en `.env`.
   `whatsapp.py` ya recibe URL y token — solo cambia de dónde los lee. Una
   tarde en fase 1; una refactorización incómoda en fase 2.
2. **Columna `plan` en `clanes`** desde el paso 01, con el middleware de
   gating ya leyéndola en el paso 05. Cuando exista el cobro, solo hay que
   escribir en esa columna.
3. **El presentador de texto plano** del paso 02 *es* el formateo de WhatsApp.
   Nace resuelto, y de paso muere el hack de traducir markdown con regex.
4. **La API interna resuelve el clan por token del puente**, en vez de asumir
   que solo hay uno. Es la misma pieza que permite un puente por cliente.

**Queda entero para fase 2:** aprovisionar número y contenedor por cliente que
pague, el cobro recurrente, y el corte por impago. Nada de eso toca la lógica
del bot — que es justamente el punto de dejarlo preparado así.

---

## 9. Fuera de alcance de la fase 1

Un plan sin recortes explícitos se convierte en un plan de doce semanas a la
tercera reunión. Hasta que la fase 1 esté en producción, la respuesta a esto
es no:

- WhatsApp para clanes nuevos
- Cobros y suscripciones
- App móvil
- Comandos nuevos
- Rediseño del sistema de reputación
- Panel de administración propio

**Élite 21 conserva su puente de WhatsApp actual durante toda la fase 1.** Es
el único clan que ya lo tiene funcionando y no hay razón para quitárselo;
simplemente no se le ofrece a nadie más todavía.

---

## 10. Convenciones del repositorio

Para que una sesión nueva no rompa el estilo existente:

- **Todo en español**: nombres de funciones, variables, tablas, docstrings y
  comentarios (`guardar_guerra`, `cagadas_avisadas`, `puntos_no_atacar`).
- **Mensajes de commit en español, en imperativo, sin acentos** (ASCII), sin
  prefijos tipo `feat:`. Ejemplos reales del historial:
  - `Agregar /clangames progreso: ver como van los Clan Games sin cerrar la medicion`
  - `Corregir "espejo" incorrecto en CWL: la numeracion no se corresponde entre clanes`
  - `Topear puntos de Clan Games al maximo real por edicion (10000)`
- **Los comentarios explican el PORQUÉ, no el qué.** El código existente es
  buen ejemplo: los comentarios documentan limitaciones de la API de Supercell,
  decisiones no obvias y trampas conocidas. Mantener ese estándar.
- **Los loops de fondo tienen que sobrevivir meses corriendo solos**: capturan
  excepciones amplias y reintentan en el siguiente ciclo, nunca se mueren.
  Verlo en `cogs/historial_guerras.py:44`.
- **Texto de cara al usuario en español de Venezuela**, incluido el tono
  relajado de `/cagarse`.

### Limitaciones de la API que hay que respetar (ya confirmadas)

- Es **100% de solo lectura**. Ningún comando puede repartir recompensas
  dentro del juego.
- **No hay endpoint de puntos de Clan Games.** Solo se infiere restando
  snapshots de achievements (inicio vs cierre). Por eso existe toda la
  maquinaria de `clan_games_sesiones`.
- `/guerra`, `/historial`, `/kda` y `/reputacion` necesitan el registro de
  guerra del clan **en público**; si no, avisan en vez de fallar.
- Caché de Supercell: clan 120s, guerra 120s, CWL 600s, jugador 60s.
- En CWL la numeración de mapa **no se corresponde entre los dos clanes** — no
  se puede calcular "espejo". Ya se corrigió una vez; no reintroducirlo.

---

## 11. Estado de avance

| Paso | Estado |
|---|---|
| 00 · Red de seguridad (tests) | No iniciado |
| 01 · Postgres + `clan_id` | No iniciado |
| 02 · Extraer `core/` | No iniciado |
| 03 · Bot multi-servidor | No iniciado |
| 04 · Worker de loops | No iniciado |
| 05 · API web + auth | No iniciado |
| 06 · Front + infraestructura | No iniciado |

**Decisiones pendientes que bloquean:** verificación de Discord (7.1) y
método de prueba de propiedad del clan (7.2).

**Rama de trabajo:** `claude/bot-scalability-clans-abado1`

**Versión visual de este plan** (misma información, formato presentable para
compartir con el equipo):
https://claude.ai/code/artifact/01b7e759-c2be-478c-82ec-b76e01686387
