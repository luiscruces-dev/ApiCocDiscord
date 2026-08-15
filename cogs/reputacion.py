import logging

import coc
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import reputacion
import storage
from utils import enviar_en_paginas


class Reputacion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        self.sincronizar_donaciones.start()
        self.revisar_capital.start()

    def cog_unload(self):
        self.sincronizar_donaciones.cancel()
        self.revisar_capital.cancel()
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    @app_commands.command(
        name="reputacion",
        description="Ranking de reputacion de la temporada actual (guerra, donaciones, capital, clan games)",
    )
    async def reputacion_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer()
        temporada = reputacion.temporada_actual()
        resumen = storage.ranking_reputacion(self.db, temporada)
        if not resumen:
            await interaction.followup.send(
                "Todavia no hay puntos de reputacion registrados esta temporada. Se van sumando solos "
                "con cada guerra guardada, cada hora con donaciones, y en cada cierre de capital o clan games."
            )
            return

        fin = coc.utils.get_season_end().date().isoformat()
        ranking = sorted(resumen.items(), key=lambda kv: -kv[1]["total"])

        lineas = [f"**Reputacion — temporada {temporada} a {fin}**\n"]
        for i, (_tag, r) in enumerate(ranking, start=1):
            cat = r["categorias"]
            guerra = cat.get("guerra_ataque", 0) + cat.get("guerra_defensa", 0) + cat.get("guerra_no_ataco", 0)
            lineas.append(
                f"`{i:>2}.` **{r['nombre']}** — {r['total']:.0f} pts "
                f"(guerra {guerra:.0f} · donaciones {cat.get('donaciones', 0):.0f} · "
                f"capital {cat.get('capital', 0):.0f} · clan games {cat.get('clan_games', 0):.0f})"
            )

        await enviar_en_paginas(interaction, lineas)

    @tasks.loop(hours=1)
    async def sincronizar_donaciones(self):
        # las donaciones de la API ya son el acumulado de la temporada en
        # curso, asi que no hay que ir sumando delta a delta como clan games
        try:
            clan = await self.coc_client.get_clan(config.CLAN_TAG)
            temporada = reputacion.temporada_actual()
            miembros = [(m.tag, m.name, m.donations) for m in clan.members]
            storage.sincronizar_donaciones(self.db, temporada, miembros)
        except coc.HTTPException as e:
            logging.getLogger("apicocdiscord").warning("sincronizar_donaciones: error de la API, reintento en 1h (%s)", e)
        except Exception:
            logging.getLogger("apicocdiscord").exception("sincronizar_donaciones: error inesperado, reintento en 1h")

    @tasks.loop(minutes=30)
    async def revisar_capital(self):
        try:
            raid_log = await self.coc_client.get_raid_log(config.CLAN_TAG, limit=1)
            entradas = list(raid_log)
            if not entradas or entradas[0].state != "ended":
                return

            temporada_raid = entradas[0]
            start_time = temporada_raid.start_time.raw_time
            if storage.raid_weekend_guardado(self.db, start_time):
                return

            miembros = [
                (m.tag, m.name, m.capital_resources_looted, m.attack_count, m.attack_limit + m.bonus_attack_limit)
                for m in temporada_raid.members
            ]
            storage.guardar_raid_weekend(self.db, reputacion.temporada_actual(), start_time, miembros)
        except coc.HTTPException as e:
            logging.getLogger("apicocdiscord").warning("revisar_capital: error de la API, reintento en 30 min (%s)", e)
        except Exception:
            logging.getLogger("apicocdiscord").exception("revisar_capital: error inesperado, reintento en 30 min")

    @sincronizar_donaciones.before_loop
    @revisar_capital.before_loop
    async def antes_de_revisar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Reputacion(bot))
