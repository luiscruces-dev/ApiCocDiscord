import logging

import coc
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import reputacion
import storage
import whatsapp
from utils import enviar_en_paginas


class Reputacion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        self.sincronizar_donaciones.start()
        self.revisar_capital.start()
        self.revisar_cierre_temporada.start()
        bot.comandos_wa["reputacion"] = self._lineas_reputacion
        bot.comandos_wa["ayudarep"] = self._lineas_ayudarep

    def cog_unload(self):
        self.sincronizar_donaciones.cancel()
        self.revisar_capital.cancel()
        self.revisar_cierre_temporada.cancel()
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def _lineas_reputacion(self, argumentos: str = "", remitente: str = "") -> list[str]:
        temporada_actual = reputacion.temporada_actual()
        temporada = (argumentos or "").strip() or temporada_actual
        resumen = storage.ranking_reputacion(self.db, temporada)
        if not resumen:
            return [
                "Todavia no hay puntos de reputacion registrados esta temporada. Se van sumando solos "
                "con cada guerra guardada, cada hora con donaciones, y en cada cierre de capital o clan games."
            ]

        ranking = sorted(resumen.items(), key=lambda kv: -kv[1]["total"])

        if temporada == temporada_actual:
            # get_season_end() da la fecha de cierre de LA TEMPORADA EN CURSO
            # nomas -- para una temporada pasada no aplica, ya cerro hace rato.
            fin = coc.utils.get_season_end().date().isoformat()
            encabezado = f"**Reputacion — temporada {temporada} a {fin}**\n"
        else:
            encabezado = f"**Reputacion — temporada {temporada}**\n"

        lineas = [encabezado]
        for i, (_tag, r) in enumerate(ranking, start=1):
            cat = r["categorias"]
            guerra = cat.get("guerra_ataque", 0) + cat.get("guerra_defensa", 0) + cat.get("guerra_no_ataco", 0)
            lineas.append(
                f"`{i:>2}.` **{r['nombre']}** — {r['total']:.0f} pts "
                f"(guerra {guerra:.0f} · donaciones {cat.get('donaciones', 0):.0f} · "
                f"capital {cat.get('capital', 0):.0f} · clan games {cat.get('clan_games', 0):.0f})"
            )
        return lineas

    async def _autocomplete_temporada(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        temporadas = storage.temporadas_registradas(self.db)
        return [
            app_commands.Choice(name=t, value=t) for t in temporadas if current.lower() in t.lower()
        ][:25]

    @app_commands.command(
        name="reputacion",
        description="Ranking de reputacion de la temporada actual (guerra, donaciones, capital, clan games)",
    )
    @app_commands.describe(temporada="Temporada pasada a consultar (dejar vacío para la actual)")
    @app_commands.autocomplete(temporada=_autocomplete_temporada)
    async def reputacion_cmd(self, interaction: discord.Interaction, temporada: str | None = None):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_reputacion(argumentos=temporada or ""))

    async def _lineas_ayudarep(self, argumentos: str = "", remitente: str = "") -> list[str]:
        return [
            "**Como funciona la reputacion**\n",
            "Cada miembro acumula puntos, que pueden sumar o restar, por guerra, donaciones, "
            "capital y clan games. Se mide por temporada (se reinicia con la temporada oficial "
            "del juego), pero el historico de temporadas pasadas queda guardado.",
            "",
            "Guerra es, por lejos, la categoria que mas pesa. Las demas suman, pero no compiten con guerra.",
            "",
            "**Reglas de guerra**",
            "- Atacar hacia arriba vale mas que atacar igual, y atacar igual vale mas que atacar hacia abajo.",
            "- No sacar 3 estrellas en un ataque facil (mismo TH o uno mas bajo) resta puntos, y castiga "
            "mas fuerte mientras mas facil deberia haber sido.",
            "- Atacar hacia arriba y no lograr 3 estrellas casi no castiga: el intento en si ya vale.",
            "- No usar el ataque de guerra es peor que atacar y fallar: es la falta mas grave del sistema.",
            "- Defender bien tambien suma, aunque poco: aguantar a alguien de un TH mas alto sin dejarle "
            "sacar el pleno da un plus chico. Defender mal nunca resta.",
            f"- La guerra de liga (CWL) pesa {round((reputacion.PESO_GUERRA['liga'] - 1) * 100)}% mas que una guerra normal.",
            "",
            "**Otras categorias**",
            "- Donaciones: puntos segun lo donado en la temporada.",
            "- Capital: puntos por oro saqueado en los Raid Weekends, con penalizacion si se dejan "
            "ataques de capital sin usar.",
            "- Clan Games: puntos segun lo aportado en el evento del mes.",
            "",
            "Usa `/reputacion` para ver el ranking de la temporada actual.",
        ]

    @app_commands.command(name="ayudarep", description="Explica como funciona el sistema de reputacion")
    async def ayudarep(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_ayudarep())

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

    @tasks.loop(hours=1)
    async def revisar_cierre_temporada(self):
        # No hay que adivinar fechas: temporadas_registradas() ya trae todas
        # las temporadas con eventos guardados. Cualquiera que no sea la
        # actual y todavia no este marcada como avisada, cerro y falta
        # avisarla -- normalmente va a ser como mucho una por tick, salvo que
        # el bot haya estado caido durante mas de un cierre de temporada.
        try:
            temporada_actual = reputacion.temporada_actual()
            for temporada in storage.temporadas_registradas(self.db):
                if temporada == temporada_actual:
                    continue
                if storage.temporada_cierre_avisado(self.db, temporada):
                    continue

                await self._avisar_cierre_temporada(temporada)
                storage.marcar_temporada_cierre_avisado(self.db, temporada)
        except Exception:
            logging.getLogger("apicocdiscord").exception("revisar_cierre_temporada: error inesperado, reintento en 1h")

    async def _avisar_cierre_temporada(self, temporada: str):
        if not whatsapp.configurado():
            return

        resumen = storage.ranking_reputacion(self.db, temporada)
        if not resumen:
            return

        ranking = sorted(resumen.items(), key=lambda kv: -kv[1]["total"])
        medallas = ["🥇", "🥈", "🥉"]

        lineas = [f"🏁 Cerró la temporada **{temporada}** — podio final de reputación:"]
        for medalla, (_tag, r) in zip(medallas, ranking):
            lineas.append(f"{medalla} **{r['nombre']}** — {r['total']:.0f} pts")

        texto = whatsapp.formatear_para_whatsapp("\n".join(lineas))
        await whatsapp.esperar_jitter(120)
        ok, detalle = await whatsapp.enviar(texto)
        if not ok:
            logging.getLogger("apicocdiscord").warning("avisar_cierre_temporada: no se pudo enviar (%s)", detalle)

    @sincronizar_donaciones.before_loop
    @revisar_capital.before_loop
    @revisar_cierre_temporada.before_loop
    async def antes_de_revisar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Reputacion(bot))
