import coc
import discord

import config

LIMITE_CARACTERES = 1900  # margen bajo el limite de 2000 de Discord por mensaje por si acasito


def tiempo_legible(segundos: int) -> str:
    segundos = max(0, segundos)
    horas, resto = divmod(segundos, 3600)
    minutos = resto // 60
    if horas and minutos:
        return f"{horas}h {minutos}m"
    if horas:
        return f"{horas}h"
    return f"{minutos}m"


async def obtener_guerra_o_mensaje(coc_client: coc.Client, titulo: str):
    """(guerra, None) si hay guerra con detalle para mostrar (en curso o
    recien terminada), o (None, lineas) con el mensaje a devolver directo
    (error, sin guerra, o en dia de preparacion). Compartido entre /guerra,
    /rival y /estimacion — los tres arrancan revisando lo mismo."""
    try:
        guerra = await coc_client.get_current_war(config.CLAN_TAG)
    except coc.PrivateWarLog:
        return None, [
            "El registro de guerra de este clan está en privado. "
            "Actívalo in-game en Ajustes del clan para poder ver esto."
        ]
    except coc.HTTPException:
        return None, [
            "La API tuvo un error consultando la guerra (pasa seguido justo en transiciones de ronda de CWL). "
            "Intenta de nuevo en un rato."
        ]

    if guerra is None or guerra.state == "notInWar":
        return None, ["El clan no está en guerra ahora mismo."]

    if guerra.state == "preparation":
        faltan_para_iniciar = tiempo_legible(guerra.start_time.seconds_until)
        return None, [
            f"**{titulo} {guerra.opponent.name}** — día de preparación, "
            f"arranca en aproximadamente {faltan_para_iniciar} · "
            f"{guerra.team_size} vs {guerra.team_size}"
        ]

    return guerra, None


def dividir_en_bloques(lineas: list[str]) -> list[str]:
    bloques = []
    bloque = ""
    for linea in lineas:
        if len(bloque) + len(linea) + 1 > LIMITE_CARACTERES:
            bloques.append(bloque)
            bloque = ""
        bloque += linea + "\n"
    if bloque:
        bloques.append(bloque)
    return bloques


async def enviar_en_paginas(interaction: discord.Interaction, lineas: list[str]):
    for bloque in dividir_en_bloques(lineas):
        await interaction.followup.send(bloque)


async def enviar_en_paginas_canal(canal: discord.abc.Messageable, lineas: list[str]):
    for bloque in dividir_en_bloques(lineas):
        await canal.send(bloque)
