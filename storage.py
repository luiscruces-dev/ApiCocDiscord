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
"""


def conectar():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
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


def temporadas_registradas(con):
    filas = con.execute("SELECT DISTINCT temporada FROM reputacion_eventos ORDER BY temporada DESC").fetchall()
    return [f[0] for f in filas]
