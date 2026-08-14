import sqlite3
from datetime import datetime, timezone
from pathlib import Path

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
    cur = con.execute(
        "INSERT INTO wars (end_time, opponent_tag, opponent_name, status, team_size, tipo) VALUES (?, ?, ?, ?, ?, ?)",
        (
            war.end_time.raw_time,
            war.opponent.tag,
            war.opponent.name,
            war.status,
            war.team_size,
            "liga" if war.is_cwl else "normal",
        ),
    )
    war_id = cur.lastrowid

    filas = []
    for miembro in war.clan.members:
        for ataque in miembro.attacks:
            enemigo = war.opponent.get_member(ataque.defender_tag)
            filas.append((
                war_id, miembro.tag, miembro.name, miembro.town_hall,
                ataque.stars, ataque.destruction,
                enemigo.town_hall if enemigo else None, 0,
            ))
        for defensa in miembro.defenses:
            atacante = war.opponent.get_member(defensa.attacker_tag)
            filas.append((
                war_id, miembro.tag, miembro.name, miembro.town_hall,
                defensa.stars, defensa.destruction,
                atacante.town_hall if atacante else None, 1,
            ))

    con.executemany(
        "INSERT INTO ataques (war_id, player_tag, player_name, player_th, stars, destruction, enemy_th, es_defensa) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        filas,
    )
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
            resultados.append((nombre, puntos_cierre - inicio[tag]))
        else:
            # se unio al clan a mitad del evento, no le alcanzamos a sacar la foto de inicio
            resultados.append((nombre, None))
    return resultados
