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
#
# ACTUALIZACION: Supercell corre Clan Games con calendario fijo hace anios
# (22 al 28 de cada mes, UTC), asi que ademas de los comandos manuales de
# arriba, un loop de fondo revisa la fecha y abre/cierra la medicion solo.
# La API no confirma este calendario en ningun lado -- si Supercell lo llega
# a cambiar, el aviso automatico de abajo lo recuerda para que se ajusten
# DIA_INICIO_CLAN_GAMES / DIA_CIERRE_CLAN_GAMES.
import logging
from datetime import datetime, timezone

import coc
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import storage
from utils import enviar_en_paginas, enviar_en_paginas_canal

DIA_INICIO_CLAN_GAMES = 22
DIA_CIERRE_CLAN_GAMES = 28

RECORDATORIO_CALENDARIO = (
    "\n-# Esto asume que Clan Games sigue corriendo del 22 al 28 (la API no lo confirma en ningun lado). "
    "Si las fechas ya no cuadran con el juego, avisen para ajustar DIA_INICIO_CLAN_GAMES / DIA_CIERRE_CLAN_GAMES en cogs/clan_games.py."
)


class ClanGames(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        self.revisar_clan_games.start()

    def cog_unload(self):
        self.revisar_clan_games.cancel()
        self.db.close()

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

    async def _abrir_sesion(self) -> int:
        foto = await self.foto_de_todos()
        sesion_id = storage.abrir_sesion_clan_games(self.db)
        storage.guardar_snapshot_clan_games(self.db, sesion_id, "inicio", foto)
        return len(foto)

    async def _cerrar_sesion(self, sesion_id: int):
        foto = await self.foto_de_todos()
        storage.guardar_snapshot_clan_games(self.db, sesion_id, "cierre", foto)
        storage.cerrar_sesion_clan_games(self.db, sesion_id)

        resultados = storage.resultado_clan_games(self.db, sesion_id)
        resultados.sort(key=lambda r: (r[1] is None, -(r[1] or 0)))
        return resultados

    async def iniciar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if storage.sesion_clan_games_abierta(self.db):
            await interaction.followup.send(
                "Ya hay una medición de Clan Games abierta. Usa `/clangames cerrar` primero si quieres cerrarla."
            )
            return

        cantidad = await self._abrir_sesion()
        await interaction.followup.send(
            f"Listo, guardé el punto de partida de {cantidad} miembros. "
            f"Corre `/clangames cerrar` cuando termine el evento."
        )

    async def cerrar(self, interaction: discord.Interaction):
        await interaction.response.defer()
        sesion_id = storage.sesion_clan_games_abierta(self.db)
        if not sesion_id:
            await interaction.followup.send("No hay ninguna medición abierta. Usa `/clangames iniciar` primero.")
            return

        resultados = await self._cerrar_sesion(sesion_id)
        lineas = self._lineas_resultado(resultados)
        await enviar_en_paginas(interaction, lineas)

    def _lineas_resultado(self, resultados) -> list[str]:
        lineas = ["**Resultado de Clan Games**\n"]
        for nombre, puntos in resultados:
            if puntos is None:
                lineas.append(f"**{nombre}** — se unió a mitad del evento, no hay punto de partida para comparar")
            else:
                lineas.append(f"**{nombre}** — {puntos} pts")
        return lineas

    @tasks.loop(minutes=15)
    async def revisar_clan_games(self):
        # Igual que revisar_guerra en historial_guerras.py: este loop tiene que
        # sobrevivir meses corriendo solo, cualquier error se ignora y se
        # reintenta en el proximo ciclo, nunca se cae.
        try:
            hoy = datetime.now(timezone.utc).day
            sesion_abierta = storage.sesion_clan_games_abierta(self.db)

            if hoy == DIA_INICIO_CLAN_GAMES and not sesion_abierta:
                cantidad = await self._abrir_sesion()
                await self._avisar_canal(
                    [f"**Clan Games arrancó** — guardé el punto de partida de {cantidad} miembros automáticamente."
                     + RECORDATORIO_CALENDARIO]
                )
            elif hoy == DIA_CIERRE_CLAN_GAMES and sesion_abierta:
                resultados = await self._cerrar_sesion(sesion_abierta)
                lineas = self._lineas_resultado(resultados)
                lineas.append(RECORDATORIO_CALENDARIO)
                await self._avisar_canal(lineas)
        except coc.HTTPException as e:
            logging.getLogger("apicocdiscord").warning("revisar_clan_games: error de la API, reintento en 15 min (%s)", e)
        except Exception:
            logging.getLogger("apicocdiscord").exception("revisar_clan_games: error inesperado, reintento en 15 min")

    @revisar_clan_games.before_loop
    async def antes_de_revisar(self):
        await self.bot.wait_until_ready()

    async def _avisar_canal(self, lineas: list[str]):
        if not config.CLAN_GAMES_CHANNEL_ID:
            return
        canal = self.bot.get_channel(int(config.CLAN_GAMES_CHANNEL_ID))
        if canal:
            await enviar_en_paginas_canal(canal, lineas)


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
