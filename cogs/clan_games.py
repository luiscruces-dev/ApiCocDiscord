#aca el rollo es este, le podes preguntar a la API cuantos puntos
# del juego del clan lleva este jugador te va a responder un numero gigante
# tipo 280,000 porque ese numero es TODO LO QUE HA GANADO EN SU VIDA,
# sumando cada edicion del evento desde que existe la cuenta. La API no
# tiene forma de decirnos cuanto llevas EN ESTE evento que esta corriendo
# ahora mismo ese dato simplemente no existe como tal en ningun lado.
#
# La buena noticia es que ese numero nunca baja, solo sube. Entonces el
# truco es medio tonto pero funciona, le sacamos una foto a ese
# numero de cada jugador justo cuando arranca el evento (/clangames iniciar),
# y le sacamos otra foto cuando termina (/clangames cerrar). Lo que gano
# cada quien en el medio es ni mas ni menos que: foto_final - foto_inicial.
# Restas y ya, te cuadra perfecto.
#
# El unico costo de esto es que alguien (cualquier colider) le tiene que avisar
# al bot cuando arranca y cuando termina el evento, porque la API tampoco
# nos dice eso no hay forma de que el bot lo adivine solo, o bueno a mi no se me ocurrio
import coc
import discord
from discord import app_commands
from discord.ext import commands

import config
import storage
from utils import enviar_en_paginas


class ClanGames(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def foto_de_todos(self):
        """(tag, nombre, puntos_de_clan_games_de_toda_la_vida) de cada miembro, ahora mismo."""
        clan = await self.coc_client.get_clan(config.CLAN_TAG)
        foto = []
        for miembro in clan.members:
            jugador = await self.coc_client.get_player(miembro.tag)
            achievement = jugador.get_achievement("Games Champion")
            foto.append((miembro.tag, miembro.name, achievement.value if achievement else 0))
        return foto

    async def iniciar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if storage.sesion_clan_games_abierta(self.db):
            await interaction.followup.send(
                "Ya hay una medición de Clan Games abierta. Usa `/clangames cerrar` primero si quieres cerrarla."
            )
            return

        foto = await self.foto_de_todos()
        sesion_id = storage.abrir_sesion_clan_games(self.db)
        storage.guardar_snapshot_clan_games(self.db, sesion_id, "inicio", foto)
        await interaction.followup.send(
            f"Listo, guardé el punto de partida de {len(foto)} miembros. "
            f"Corre `/clangames cerrar` cuando termine el evento."
        )

    async def cerrar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        sesion_id = storage.sesion_clan_games_abierta(self.db)
        if not sesion_id:
            await interaction.followup.send("No hay ninguna medición abierta. Usa `/clangames iniciar` primero.")
            return

        foto = await self.foto_de_todos()
        storage.guardar_snapshot_clan_games(self.db, sesion_id, "cierre", foto)
        storage.cerrar_sesion_clan_games(self.db, sesion_id)

        resultados = storage.resultado_clan_games(self.db, sesion_id)
        resultados.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))

        lineas = ["**Resultado de Clan Games**\n"]
        for nombre, puntos in resultados:
            if puntos is None:
                lineas.append(f"**{nombre}** — se unió a mitad del evento, no hay punto de partida para comparar")
            else:
                lineas.append(f"**{nombre}** — {puntos} pts")

        await enviar_en_paginas(interaction, lineas)


class ClanGamesGroup(app_commands.Group):
    def __init__(self, cog: ClanGames):
        super().__init__(name="clangames", description="Medir puntos de Clan Games (inicio/cierre del evento)")
        self.cog = cog

    @app_commands.command(name="iniciar", description="Guarda el punto de partida de todos para esta edición")
    async def iniciar(self, interaction: discord.Interaction):
        await self.cog.iniciar(interaction)

    @app_commands.command(name="cerrar", description="Cierra la medición y muestra cuánto aportó cada quien")
    async def cerrar(self, interaction: discord.Interaction):
        await self.cog.cerrar(interaction)


async def setup(bot: commands.Bot):
    cog = ClanGames(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(ClanGamesGroup(cog))
