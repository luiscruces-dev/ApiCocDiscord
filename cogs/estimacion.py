"""
Proyeccion de estrellas para la guerra ACTUAL, basada en el historial real
del clan por diferencia de TH (no una formula inventada). Los ataques que
ya se hicieron cuentan las estrellas reales; los que faltan se estiman
contra el "espejo" (mismo map_position del lado rival, igual que /rival),
usando el promedio historico -- primero el del jugador si tiene suficientes
ataques guardados a esa diferencia (>= MINIMO_MUESTRA_PERSONAL), si no el
promedio de todo el clan a esa diferencia. Sin historial a esa diferencia
todavia, se marca como tal en vez de inventar un numero.
"""
import coc
import discord
from discord import app_commands
from discord.ext import commands

import storage
from utils import enviar_en_paginas, obtener_guerra_o_mensaje

MINIMO_MUESTRA_PERSONAL = 3


class Estimacion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["estimacion"] = self._lineas_estimacion

    def cog_unload(self):
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    def _estimar_para(self, jugador_tag: str, diferencia: int, stats_clan: dict):
        """(stats, origen) donde origen es 'personal' o 'clan', o (None, None)
        si no hay historial de nadie a esa diferencia."""
        personal = storage.stats_por_diferencia_th(self.db, jugador_tag).get(diferencia)
        if personal and personal["ataques"] >= MINIMO_MUESTRA_PERSONAL:
            return personal, "personal"
        general = stats_clan.get(diferencia)
        if general:
            return general, "clan"
        return None, None

    async def _lineas_estimacion(self, argumentos: str = "", remitente: str = "") -> list[str]:
        guerra, mensaje = await obtener_guerra_o_mensaje(self.coc_client, "Estimación —")
        if mensaje:
            return mensaje

        stats_clan = storage.stats_por_diferencia_th(self.db)
        rival_por_posicion = {m.map_position: m for m in guerra.opponent.members}

        total_estimado = 0.0
        total_posible = guerra.team_size * guerra.attacks_per_member * 3
        lineas_detalle = []

        for m in sorted(guerra.clan.members, key=lambda m: m.map_position):
            rival = rival_por_posicion.get(m.map_position)
            usados = len(m.attacks)
            pendientes = guerra.attacks_per_member - usados
            total_estimado += m.star_count

            if not rival:
                lineas_detalle.append(f"`{m.map_position:>2}.` **{m.name}** — sin rival asignado en esa posición")
                continue

            diferencia = rival.town_hall - m.town_hall
            comparacion = f"{diferencia:+d}" if diferencia else "mismo TH"

            if pendientes <= 0:
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {m.star_count}⭐ reales, ya usó los {usados} ataques"
                )
                continue

            stats, origen = self._estimar_para(m.tag, diferencia, stats_clan)
            if stats:
                estimado_pendientes = stats["estrellas_prom"] * pendientes
                total_estimado += estimado_pendientes
                fuente = "su propio historial" if origen == "personal" else "el historial del clan"
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {m.star_count}⭐ reales + ~{estimado_pendientes:.1f}⭐ "
                    f"estimadas ({pendientes} pendiente{'s' if pendientes != 1 else ''}, según {fuente}: "
                    f"{stats['estrellas_prom']:.1f}⭐ prom. en {stats['ataques']} ataques a esa diferencia)"
                )
            else:
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {m.star_count}⭐ reales, {pendientes} pendiente(s) "
                    f"sin historial a esa diferencia todavía"
                )

        porcentaje = (total_estimado / total_posible * 100) if total_posible else 0
        lineas = [
            f"**Estimación — guerra vs {guerra.opponent.name}**",
            "Los ataques ya hechos cuentan estrellas reales; los pendientes se estiman contra el espejo, "
            "según el historial del clan por diferencia de TH (poca muestra todavía = estimación floja, "
            "mirá el detalle de cada uno).\n",
            f"**Proyección total: ~{total_estimado:.0f}⭐ de {total_posible} posibles ({porcentaje:.0f}%)**\n",
        ]
        lineas.extend(lineas_detalle)
        return lineas

    @app_commands.command(
        name="estimacion",
        description="Proyección de estrellas de la guerra actual, según el historial del clan por diferencia de TH",
    )
    async def estimacion(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_estimacion())


async def setup(bot: commands.Bot):
    await bot.add_cog(Estimacion(bot))
