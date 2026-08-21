import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import reputacion

DB_PATH = str(Path(__file__).resolve().parent / "clan_stats.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS wars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    end_time TEXT NOT NULL,
    opponent_tag TEXT,
    opponent_name TEXT,
    status TEXT,
    team_size INTEGER,
    tipo TEXT,
    UNIQUE(end_time, opponent_tag)
);

CREATE TABLE IF NOT EXISTS ataques (
    war_id INTEGER NOT NULL REFERENCES wars(id),
    player_tag TEXT NOT NULL,
    player_name TEXT NOT NULL,
    player_th INTEGER,
    stars INTEGER,
    destruction REAL,
    enemy_th INTEGER,
    es_defensa INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_games_sesiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    inicio_fecha TEXT NOT NULL,
    cierre_fecha TEXT
);

CREATE TABLE IF NOT EXISTS clan_games_snapshots (
    sesion_id INTEGER NOT NULL REFERENCES clan_games_sesiones(id),
    momento TEXT NOT NULL,
    player_tag TEXT NOT NULL,
    player_name TEXT NOT NULL,
    puntos INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reputacion_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    temporada TEXT NOT NULL,
    fecha TEXT NOT NULL,
    player_tag TEXT NOT NULL,
    player_name TEXT NOT NULL,
    categoria TEXT NOT NULL,
    puntos REAL NOT NULL,
    detalle TEXT,
    clave TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS raid_weekends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS vinculos_wa (
    player_tag TEXT NOT NULL,
    wa_jid TEXT NOT NULL,
    player_name TEXT NOT NULL,
    fecha TEXT NOT NULL,
    PRIMARY KEY (player_tag, wa_jid)
);

CREATE TABLE IF NOT EXISTS avisos_inicio_guerra (
    start_time TEXT NOT NULL,
    opponent_tag TEXT,
    UNIQUE(start_time, opponent_tag)
);

CREATE TABLE IF NOT EXISTS avisos_temporada_cerrada (
    temporada TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS recordatorios_automaticos (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ultimo_envio TEXT NOT NULL
);

-- El nombre quedo de cuando /cagarse solo hacia roasts, pero tambien trackea
-- los ataques que dispararon un elogio (FRASES_ELOGIO en cagarse.py) -- en
-- los dos casos, el punto es no volver a avisar el mismo ataque.
CREATE TABLE IF NOT EXISTS cagadas_avisadas (
    start_time TEXT NOT NULL,
    opponent_tag TEXT,
    attack_order INTEGER NOT NULL,
    UNIQUE(start_time, opponent_tag, attack_order)
);
"""


def _migrar_vinculos_wa(con):
    """vinculos_wa empezo con wa_jid como PK (un numero, un solo tag). Para
    soportar multicuenta (un numero, varios tags) el PK paso a player_tag.
    Si la tabla ya existe con el esquema viejo, se migra sin perder datos."""
    columnas = con.execute("PRAGMA table_info(vinculos_wa)").fetchall()
    pk_actual = next((col[1] for col in columnas if col[5] == 1), None)
    if pk_actual != "wa_jid":
        return

    filas = con.execute("SELECT wa_jid, player_tag, player_name, fecha FROM vinculos_wa").fetchall()
    con.execute("ALTER TABLE vinculos_wa RENAME TO vinculos_wa_viejo")
    con.execute(
        "CREATE TABLE vinculos_wa ("
        "player_tag TEXT PRIMARY KEY, wa_jid TEXT NOT NULL, "
        "player_name TEXT NOT NULL, fecha TEXT NOT NULL)"
    )
    con.executemany(
        "INSERT INTO vinculos_wa (player_tag, wa_jid, player_name, fecha) VALUES (?, ?, ?, ?)",
        [(tag, jid, nombre, fecha) for jid, tag, nombre, fecha in filas],
    )
    con.execute("DROP TABLE vinculos_wa_viejo")
    con.commit()


def _migrar_vinculos_wa_multi_numero(con):
    """vinculos_wa tenia player_tag solo como PK (una cuenta, un solo
    numero). Para que una cuenta compartida (ej. una pareja jugando desde
    el mismo tag) pueda tener mas de un numero vinculado, el PK paso a ser
    (player_tag, wa_jid). Migra sin perder datos si la tabla todavia tiene
    el esquema viejo."""
    columnas = con.execute("PRAGMA table_info(vinculos_wa)").fetchall()
    columnas_pk = {col[1] for col in columnas if col[5] > 0}
    if columnas_pk == {"player_tag", "wa_jid"}:
        return

    filas = con.execute("SELECT player_tag, wa_jid, player_name, fecha FROM vinculos_wa").fetchall()
    con.execute("ALTER TABLE vinculos_wa RENAME TO vinculos_wa_viejo_pk_simple")
    con.execute(
        "CREATE TABLE vinculos_wa ("
        "player_tag TEXT NOT NULL, wa_jid TEXT NOT NULL, "
        "player_name TEXT NOT NULL, fecha TEXT NOT NULL, "
        "PRIMARY KEY (player_tag, wa_jid))"
    )
    con.executemany(
        "INSERT INTO vinculos_wa (player_tag, wa_jid, player_name, fecha) VALUES (?, ?, ?, ?)",
        filas,
    )
    con.execute("DROP TABLE vinculos_wa_viejo_pk_simple")
    con.commit()


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    _migrar_vinculos_wa(con)
    _migrar_vinculos_wa_multi_numero(con)
    return con


def guerra_guardada(con, end_time: str, opponent_tag: str) -> bool:
    fila = con.execute(
        "SELECT 1 FROM wars WHERE end_time = ? AND opponent_tag = ?", (end_time, opponent_tag)
    ).fetchone()
    return fila is not None


def guardar_guerra(con, war) -> int:
    tipo = "liga" if war.is_cwl else "normal"
    cur = con.execute(
        "INSERT INTO wars (end_time, opponent_tag, opponent_name, status, team_size, tipo) VALUES (?, ?, ?, ?, ?, ?)",
        (war.end_time.raw_time, war.opponent.tag, war.opponent.name, war.status, war.team_size, tipo),
    )
    war_id = cur.lastrowid

    temporada = reputacion.temporada_actual()
    fecha = datetime.now(timezone.utc).isoformat()
    filas = []
    eventos = []

    for miembro in war.clan.members:
        for ataque in miembro.attacks:
            enemigo = war.opponent.get_member(ataque.defender_tag)
            enemy_th = enemigo.town_hall if enemigo else None
            filas.append((
                war_id, miembro.tag, miembro.name, miembro.town_hall,
                ataque.stars, ataque.destruction, enemy_th, 0,
            ))
            if enemy_th is not None:
                puntos = reputacion.puntos_ataque(miembro.town_hall, enemy_th, ataque.stars, ataque.destruction, tipo)
                eventos.append((
                    temporada, fecha, miembro.tag, miembro.name, "guerra_ataque", puntos,
                    f"vs TH{enemy_th} ({tipo}): {ataque.stars}* {ataque.destruction:.0f}%",
                ))

        for _ in range(max(0, war.attacks_per_member - len(miembro.attacks))):
            eventos.append((
                temporada, fecha, miembro.tag, miembro.name, "guerra_no_ataco",
                reputacion.puntos_no_atacar(tipo), f"no atacó ({tipo})",
            ))

        for defensa in miembro.defenses:
            atacante = war.opponent.get_member(defensa.attacker_tag)
            enemy_th = atacante.town_hall if atacante else None
            filas.append((
                war_id, miembro.tag, miembro.name, miembro.town_hall,
                defensa.stars, defensa.destruction, enemy_th, 1,
            ))
            if enemy_th is not None:
                puntos = reputacion.puntos_defensa(miembro.town_hall, enemy_th, defensa.stars, defensa.destruction, tipo)
                eventos.append((
                    temporada, fecha, miembro.tag, miembro.name, "guerra_defensa", puntos,
                    f"defendió de TH{enemy_th} ({tipo}): {defensa.stars}*",
                ))

    con.executemany(
        "INSERT INTO ataques (war_id, player_tag, player_name, player_th, stars, destruction, enemy_th, es_defensa) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        filas,
    )
    registrar_eventos_reputacion(con, eventos)
    con.commit()
    return war_id


def ultimas_guerras(con, limite: int = 10):
    return con.execute(
        "SELECT end_time, opponent_name, status, team_size, tipo FROM wars ORDER BY end_time DESC LIMIT ?",
        (limite,),
    ).fetchall()


def stats_por_jugador(con) -> dict:
    """tag -> stats de ataque/defensa acumulados de todas las guerras guardadas hasta ahora."""
    filas = con.execute(
        "SELECT player_tag, player_name, player_th, stars, destruction, enemy_th, es_defensa FROM ataques"
    ).fetchall()

    stats = {}
    for tag, nombre, th, stars, destruction, enemy_th, es_defensa in filas:
        s = stats.setdefault(tag, {
            "nombre": nombre, "ataques": 0, "estrellas_ataque": 0, "destruccion_total": 0.0,
            "subio": 0, "bajo": 0, "igual": 0,
            "veces_atacado": 0, "estrellas_recibidas": 0,
        })
        s["nombre"] = nombre  # se queda con el nombre mas reciente que veamos
        if es_defensa:
            s["veces_atacado"] += 1
            s["estrellas_recibidas"] += stars
        else:
            s["ataques"] += 1
            s["estrellas_ataque"] += stars
            s["destruccion_total"] += destruction
            if enemy_th is not None and th is not None:
                if enemy_th > th:
                    s["subio"] += 1
                elif enemy_th < th:
                    s["bajo"] += 1
                else:
                    s["igual"] += 1
    return stats


def stats_por_diferencia_th(con, player_tag: str | None = None) -> dict:
    """diferencia (enemy_th - player_th, ej. +1 = atacando un TH mas alto)
    -> {ataques, estrellas_prom, destruccion_prom, triples_pct}. Sin
    player_tag, junta los ataques de TODO el clan (para /estimacion cuando
    no hay suficiente muestra personal); con player_tag, solo los de ese
    jugador."""
    query = (
        "SELECT enemy_th - player_th AS diferencia, COUNT(*), AVG(stars), AVG(destruction), "
        "SUM(CASE WHEN stars = 3 THEN 1 ELSE 0 END) "
        "FROM ataques WHERE es_defensa = 0 AND enemy_th IS NOT NULL AND player_th IS NOT NULL"
    )
    params: tuple = ()
    if player_tag:
        query += " AND player_tag = ?"
        params = (player_tag,)
    query += " GROUP BY diferencia"

    resultado = {}
    for diferencia, cantidad, estrellas_prom, destruccion_prom, triples in con.execute(query, params).fetchall():
        resultado[diferencia] = {
            "ataques": cantidad,
            "estrellas_prom": estrellas_prom,
            "destruccion_prom": destruccion_prom,
            "triples_pct": (triples / cantidad * 100) if cantidad else 0.0,
        }
    return resultado


def sesion_clan_games_abierta(con):
    """id de la sesion abierta (sin cerrar todavia), o None si no hay ninguna."""
    fila = con.execute(
        "SELECT id FROM clan_games_sesiones WHERE cierre_fecha IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return fila[0] if fila else None


def abrir_sesion_clan_games(con) -> int:
    cur = con.execute(
        "INSERT INTO clan_games_sesiones (inicio_fecha) VALUES (?)",
        (datetime.now(timezone.utc).isoformat(),),
    )
    con.commit()
    return cur.lastrowid


def cerrar_sesion_clan_games(con, sesion_id: int):
    con.execute(
        "UPDATE clan_games_sesiones SET cierre_fecha = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), sesion_id),
    )
    con.commit()


def guardar_snapshot_clan_games(con, sesion_id: int, momento: str, jugadores):
    """jugadores: lista de tuplas (tag, nombre, puntos)."""
    con.executemany(
        "INSERT INTO clan_games_snapshots (sesion_id, momento, player_tag, player_name, puntos) "
        "VALUES (?, ?, ?, ?, ?)",
        [(sesion_id, momento, tag, nombre, puntos) for tag, nombre, puntos in jugadores],
    )
    con.commit()


def resultado_clan_games(con, sesion_id: int):
    inicio = {
        tag: puntos
        for tag, puntos in con.execute(
            "SELECT player_tag, puntos FROM clan_games_snapshots WHERE sesion_id = ? AND momento = 'inicio'",
            (sesion_id,),
        )
    }
    cierre = con.execute(
        "SELECT player_tag, player_name, puntos FROM clan_games_snapshots WHERE sesion_id = ? AND momento = 'cierre'",
        (sesion_id,),
    ).fetchall()

    resultados = []
    for tag, nombre, puntos_cierre in cierre:
        if tag in inicio:
            resultados.append((tag, nombre, puntos_cierre - inicio[tag]))
        else:
            # se unio al clan a mitad del evento, no le alcanzamos a sacar la foto de inicio
            resultados.append((tag, nombre, None))
    return resultados


# ---- reputacion ------------------------------------------------------------

def registrar_eventos_reputacion(con, eventos):
    """eventos: lista de tuplas (temporada, fecha, tag, nombre, categoria, puntos, detalle)."""
    if not eventos:
        return
    con.executemany(
        "INSERT INTO reputacion_eventos (temporada, fecha, player_tag, player_name, categoria, puntos, detalle) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        eventos,
    )


def registrar_reputacion_clan_games(con, temporada, resultados):
    """resultados: tuplas (tag, nombre, puntos_del_evento_o_None), como devuelve resultado_clan_games."""
    fecha = datetime.now(timezone.utc).isoformat()
    eventos = [
        (temporada, fecha, tag, nombre, "clan_games", reputacion.puntos_clan_games(puntos), f"{puntos} pts del evento")
        for tag, nombre, puntos in resultados
        if puntos is not None
    ]
    registrar_eventos_reputacion(con, eventos)
    con.commit()


def sincronizar_donaciones(con, temporada, miembros):
    """miembros: tuplas (tag, nombre, donaciones). Se reemplaza el valor de la
    temporada en vez de sumarlo, porque la API ya da el acumulado de la
    temporada en curso (se resetea sola cuando resetea la temporada)."""
    fecha = datetime.now(timezone.utc).isoformat()
    filas = [
        (
            temporada, fecha, tag, nombre, "donaciones", reputacion.puntos_donacion(donaciones),
            f"{donaciones} donadas", f"{temporada}:{tag}:donaciones",
        )
        for tag, nombre, donaciones in miembros
    ]
    con.executemany(
        "INSERT INTO reputacion_eventos (temporada, fecha, player_tag, player_name, categoria, puntos, detalle, clave) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET fecha=excluded.fecha, player_name=excluded.player_name, "
        "puntos=excluded.puntos, detalle=excluded.detalle",
        filas,
    )
    con.commit()


def raid_weekend_guardado(con, start_time: str) -> bool:
    fila = con.execute("SELECT 1 FROM raid_weekends WHERE start_time = ?", (start_time,)).fetchone()
    return fila is not None


def guardar_raid_weekend(con, temporada, start_time, miembros):
    """miembros: tuplas (tag, nombre, oro, ataques_usados, limite_ataques)."""
    con.execute("INSERT INTO raid_weekends (start_time) VALUES (?)", (start_time,))
    fecha = datetime.now(timezone.utc).isoformat()
    eventos = [
        (
            temporada, fecha, tag, nombre, "capital",
            reputacion.puntos_capital(oro, usados, limite), f"{oro} oro, {usados}/{limite} ataques",
        )
        for tag, nombre, oro, usados, limite in miembros
    ]
    registrar_eventos_reputacion(con, eventos)
    con.commit()


def ranking_reputacion(con, temporada):
    """tag -> {nombre, total, categorias: {categoria: puntos}} de la temporada dada."""
    filas = con.execute(
        "SELECT player_tag, player_name, categoria, SUM(puntos) FROM reputacion_eventos "
        "WHERE temporada = ? GROUP BY player_tag, categoria",
        (temporada,),
    ).fetchall()

    resumen = {}
    for tag, nombre, categoria, puntos in filas:
        r = resumen.setdefault(tag, {"nombre": nombre, "total": 0.0, "categorias": {}})
        r["nombre"] = nombre
        r["categorias"][categoria] = puntos
        r["total"] += puntos
    return resumen


# ---- vinculos de WhatsApp ---------------------------------------------------

def vincular_wa(con, wa_jid: str, player_tag: str, player_name: str):
    # PK compuesta (player_tag, wa_jid): relacion muchos-a-muchos real.
    # Un numero puede tener varias cuentas (multicuenta), y una cuenta
    # puede tener varios numeros (ej. una pareja compartiendo una cuenta).
    con.execute(
        "INSERT INTO vinculos_wa (player_tag, wa_jid, player_name, fecha) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(player_tag, wa_jid) DO UPDATE SET "
        "player_name=excluded.player_name, fecha=excluded.fecha",
        (player_tag, wa_jid, player_name, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()


def desvincular_wa(con, wa_jid: str, player_tag: str | None = None) -> int:
    """Sin player_tag borra todas las cuentas vinculadas a ese numero.
    Con player_tag borra solo esa cuenta. Devuelve cuantas se borraron."""
    if player_tag:
        cur = con.execute(
            "DELETE FROM vinculos_wa WHERE wa_jid = ? AND player_tag = ?", (wa_jid, player_tag)
        )
    else:
        cur = con.execute("DELETE FROM vinculos_wa WHERE wa_jid = ?", (wa_jid,))
    con.commit()
    return cur.rowcount


def tags_de_jid(con, wa_jid: str) -> list[tuple[str, str]]:
    """(player_tag, player_name) de todas las cuentas vinculadas a ese numero."""
    return con.execute(
        "SELECT player_tag, player_name FROM vinculos_wa WHERE wa_jid = ? ORDER BY player_name", (wa_jid,)
    ).fetchall()


def cagada_avisada(con, start_time: str, opponent_tag: str, attack_order: int) -> bool:
    fila = con.execute(
        "SELECT 1 FROM cagadas_avisadas WHERE start_time = ? AND opponent_tag = ? AND attack_order = ?",
        (start_time, opponent_tag, attack_order),
    ).fetchone()
    return fila is not None


def marcar_cagada_avisada(con, start_time: str, opponent_tag: str, attack_order: int):
    con.execute(
        "INSERT OR IGNORE INTO cagadas_avisadas (start_time, opponent_tag, attack_order) VALUES (?, ?, ?)",
        (start_time, opponent_tag, attack_order),
    )
    con.commit()


def guerra_inicio_avisado(con, start_time: str, opponent_tag: str) -> bool:
    fila = con.execute(
        "SELECT 1 FROM avisos_inicio_guerra WHERE start_time = ? AND opponent_tag = ?",
        (start_time, opponent_tag),
    ).fetchone()
    return fila is not None


def marcar_guerra_inicio_avisado(con, start_time: str, opponent_tag: str):
    con.execute(
        "INSERT OR IGNORE INTO avisos_inicio_guerra (start_time, opponent_tag) VALUES (?, ?)",
        (start_time, opponent_tag),
    )
    con.commit()


def temporada_cierre_avisado(con, temporada: str) -> bool:
    fila = con.execute(
        "SELECT 1 FROM avisos_temporada_cerrada WHERE temporada = ?", (temporada,)
    ).fetchone()
    return fila is not None


def marcar_temporada_cierre_avisado(con, temporada: str):
    con.execute("INSERT OR IGNORE INTO avisos_temporada_cerrada (temporada) VALUES (?)", (temporada,))
    con.commit()


def ultimo_recordatorio_automatico(con) -> str | None:
    """ISO datetime del ultimo envio real de recordatorio_automatico, o None
    si nunca se mando ninguno. Sirve para no repetirlo si el bot reinicia
    (tasks.loop dispara una vez apenas arranca) antes de que pasen las 4h."""
    fila = con.execute("SELECT ultimo_envio FROM recordatorios_automaticos WHERE id = 1").fetchone()
    return fila[0] if fila else None


def marcar_recordatorio_automatico_enviado(con):
    ahora = datetime.now(timezone.utc).isoformat()
    con.execute(
        "INSERT INTO recordatorios_automaticos (id, ultimo_envio) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET ultimo_envio = excluded.ultimo_envio",
        (ahora,),
    )
    con.commit()


def jids_por_tag(con) -> dict:
    """player_tag -> lista de wa_jid vinculados a esa cuenta (puede ser mas
    de uno, ej. una pareja compartiendo una misma cuenta)."""
    filas = con.execute("SELECT player_tag, wa_jid FROM vinculos_wa").fetchall()
    resultado: dict[str, list[str]] = {}
    for tag, jid in filas:
        resultado.setdefault(tag, []).append(jid)
    return resultado


def jids_de_tag(con, player_tag: str) -> list[str]:
    """Todos los numeros vinculados a una cuenta puntual."""
    filas = con.execute("SELECT wa_jid FROM vinculos_wa WHERE player_tag = ?", (player_tag,)).fetchall()
    return [jid for (jid,) in filas]


def temporadas_registradas(con):
    filas = con.execute("SELECT DISTINCT temporada FROM reputacion_eventos ORDER BY temporada DESC").fetchall()
    return [f[0] for f in filas]
