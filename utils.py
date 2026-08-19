import discord

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
