"""
Historial de guerras y KDA por jugador. get_war_log no trae detalle por
jugador, asi que cada guerra se guarda apenas termina.
"""
import logging

import coc
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import storage
import whatsapp
from utils import enviar_en_paginas

ESTADO_GUERRA_LEGIBLE = {"won": "GANADA", "lost": "PERDIDA", "tie": "EMPATE"}


class HistorialGuerras(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        self.revisar_guerra.start()
        bot.comandos_wa["historial"] = self._lineas_historial
        bot.comandos_wa["kda"] = self._lineas_kda

    def cog_unload(self):
        self.revisar_guerra.cancel()
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    @tasks.loop(minutes=10)
    async def revisar_guerra(self):
        try:
            war = await self.coc_client.get_current_war(config.CLAN_TAG)

            if not war or war.state != "warEnded":
                return
            if storage.guerra_guardada(self.db, war.end_time.raw_time, war.opponent.tag):
                return

            storage.guardar_guerra(self.db, war)
            await self._avisar_resultado_guerra(war)
        except coc.HTTPException as e:
            logging.getLogger("apicocdiscord").warning("revisar_guerra: error de la API, reintento en 10 min (%s)", e)
        except Exception:
            logging.getLogger("apicocdiscord").exception("revisar_guerra: error inesperado, reintento en 10 min")

    @revisar_guerra.before_loop
    async def antes_de_revisar(self):
        await self.bot.wait_until_ready()

    async def _avisar_resultado_guerra(self, war):
        if not whatsapp.configurado():
            return

        estado = ESTADO_GUERRA_LEGIBLE.get(war.status, war.status)
        lineas = [f"Guerra vs **{war.opponent.name}** terminó: **{estado}**"]

        mvp = max(
            war.clan.members,
            key=lambda m: (
                m.star_count,
                sum(a.destruction for a in m.attacks) / len(m.attacks) if m.attacks else 0,
            ),
            default=None,
        )
        if mvp:
            prom_destruccion = sum(a.destruction for a in mvp.attacks) / len(mvp.attacks) if mvp.attacks else 0
            lineas.append(f"🏆 MVP: **{mvp.name}** — {mvp.star_count} estrellas, {prom_destruccion:.0f}% destrucción promedio")

        no_atacaron = [m.name for m in war.clan.members if len(m.attacks) < war.attacks_per_member]
        if no_atacaron:
            lineas.append(f"⚠️ No atacaron: {', '.join(no_atacaron)}")

        texto = whatsapp.formatear_para_whatsapp("\n".join(lineas))
        await whatsapp.esperar_jitter(60)
        ok, detalle = await whatsapp.enviar(texto)
        if not ok:
            logging.getLogger("apicocdiscord").warning("avisar_resultado_guerra: no se pudo enviar (%s)", detalle)

    async def _lineas_historial(self, argumentos: str = "", remitente: str = "") -> list[str]:
        filas = storage.ultimas_guerras(self.db, limite=10)
        if not filas:
            return [
                "Todavia no hay guerras guardadas. Reviso cada 10 min si la guerra actual termino "
                "y la guardo — dale tiempo mientras el bot este corriendo durante una guerra."
            ]

        lineas = ["**Ultimas guerras**\n"]
        for end_time, opp_name, status, team_size, tipo in filas:
            lineas.append(f"vs **{opp_name}** ({team_size}v{team_size}, {tipo}) — {status}")
        return lineas

    @app_commands.command(name="historial", description="Ultimas guerras guardadas del clan")
    async def historial(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_historial())

    async def _lineas_kda(self, argumentos: str = "", remitente: str = "") -> list[str]:
        stats = storage.stats_por_jugador(self.db)
        if not stats:
            return [
                "Todavia no hay datos — se van guardando solos cuando termina cada guerra "
                "mientras el bot este corriendo."
            ]

        ordenados = sorted(stats.items(), key=lambda kv: -kv[1]["estrellas_ataque"])
        lineas = ["**KDA de guerra (acumulado desde que esto quedo corriendo)**\n"]
        for tag, s in ordenados:
            prom_destruccion = s["destruccion_total"] / s["ataques"] if s["ataques"] else 0
            lineas.append(
                f"**{s['nombre']}** — {s['ataques']} ataques, {s['estrellas_ataque']} estrellas "
                f"({prom_destruccion:.0f}% destr. prom · TH arriba/igual/abajo: {s['subio']}/{s['igual']}/{s['bajo']}) · "
                f"defensa: {s['veces_atacado']}x atacado, {s['estrellas_recibidas']} estrellas recibidas"
            )
        return lineas

    @app_commands.command(
        name="kda",
        description="Estadisticas de ataque/defensa por jugador, de las guerras guardadas hasta ahora",
    )
    async def kda(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_kda())


async def setup(bot: commands.Bot):
    await bot.add_cog(HistorialGuerras(bot))
