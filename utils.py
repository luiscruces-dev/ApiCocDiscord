import discord

LIMITE_CARACTERES = 1900  # margen bajo el limite de 2000 de Discord por mensaje


async def enviar_en_paginas(interaction: discord.Interaction, lineas: list[str]):
    bloque = ""
    for linea in lineas:
        if len(bloque) + len(linea) + 1 > LIMITE_CARACTERES:
            await interaction.followup.send(bloque)
            bloque = ""
        bloque += linea + "\n"
    if bloque:
        await interaction.followup.send(bloque)
