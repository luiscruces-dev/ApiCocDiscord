import coc

PESO_ESTRELLA = 10
PESO_DESTRUCCION = 0.1
PENALIZ_BASE = 10
PENALIZ_CERO = 5
FACTOR_DEFENSA = 0.3
PENALIZ_NO_ATACAR = -45
PENALIZ_CAPITAL_NO_USADO = -8
PESO_DONACION = 0.1
ORO_POR_PUNTO = 500
DIVISOR_CLAN_GAMES = 10

PESO_GUERRA = {"normal": 1.0, "liga": 1.4}

# Mientras mas arriba el TH rival respecto al propio, mas vale el ataque (M) y
# menos imperdonable es no sacar el pleno (P) - y al reves atacando hacia abajo.
MULTIPLICADOR_M = {-2: 0.5, -1: 0.75, 0: 1.0, 1: 1.5, 2: 2.0}
CASTIGO_P = {-2: 2.0, -1: 1.5, 0: 1.0, 1: 0.5, 2: 0.0}


def _delta(th_propio: int, th_rival: int) -> int:
    return max(-2, min(2, th_rival - th_propio))


def puntos_ataque(th_propio: int, th_rival: int, estrellas: int, destruccion: float, tipo_guerra: str) -> float:
    # base = valor por estrellas/destruccion segun dificultad; se resta un
    # castigo si no hubo pleno, mas fuerte cuanto mas facil era el ataque.
    m, p = MULTIPLICADOR_M[_delta(th_propio, th_rival)], CASTIGO_P[_delta(th_propio, th_rival)]
    base = m * (PESO_ESTRELLA * estrellas + PESO_DESTRUCCION * destruccion)
    castigo = p * PENALIZ_BASE * (3 - estrellas) if estrellas < 3 else 0
    castigo += PENALIZ_CERO if estrellas == 0 else 0
    return PESO_GUERRA[tipo_guerra] * (base - castigo)


def puntos_defensa(th_propio: int, th_rival: int, estrellas_recibidas: int, destruccion_recibida: float, tipo_guerra: str) -> float:
    # solo premia (nunca resta): aguantar a un TH mas alto sin dejarle sacar
    # el pleno vale mas, aguantar mal nunca castiga al defensor.
    m = MULTIPLICADOR_M[_delta(th_propio, th_rival)]
    valor = FACTOR_DEFENSA * PESO_GUERRA[tipo_guerra] * m * (
        (3 - estrellas_recibidas) * 10 + (100 - destruccion_recibida) * 0.1
    )
    return max(0.0, valor)


def puntos_no_atacar(tipo_guerra: str) -> float:
    return PESO_GUERRA[tipo_guerra] * PENALIZ_NO_ATACAR


def puntos_donacion(donaciones: int) -> float:
    return donaciones * PESO_DONACION


def puntos_capital(oro_saqueado: int, ataques_usados: int, limite_ataques: int) -> float:
    # ataques de capital sin usar restan aparte, no importa cuanto oro se saco
    puntos = oro_saqueado / ORO_POR_PUNTO
    if ataques_usados < limite_ataques:
        puntos += (limite_ataques - ataques_usados) * PENALIZ_CAPITAL_NO_USADO
    return puntos


def puntos_clan_games(delta_puntos_evento: int) -> float:
    return delta_puntos_evento / DIVISOR_CLAN_GAMES


def temporada_actual() -> str:
    # temporada de reputacion = temporada oficial de Clash (ultimo lunes del mes)
    return coc.utils.get_season_start().date().isoformat()
