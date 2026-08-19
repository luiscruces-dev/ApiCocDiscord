"""
Vista 360 de un jugador: junta en un solo lugar lo que hoy esta repartido
entre /reputacion, /kda, /donaciones y /capital.
"""
import coc
import discord
from discord import app_commands
from discord.ext import commands

import config
import reputacion
import storage
from utils import enviar_en_paginas


class Perfil(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["perfil"] = self._lineas_perfil

    def cog_unload(self):
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    def _buscar_miembro(self, clan, identificador: str):
        """Busca un miembro del clan por tag (con o sin #) o por nombre
        (case-insensitive, primera coincidencia)."""
        tag = coc.utils.correct_tag(identificador)
        miembro = clan.get_member(tag)
        if miembro:
            return miembro
        identificador_low = identificador.lower()
        return next((m for m in clan.members if m.name.lower() == identificador_low), None)

    async def _lineas_perfil(self, argumentos: str = "", remitente: str = "") -> list[str]:
        identificador = (argumentos or "").strip()
        if not identificador:
            return ["Uso: `/perfil <tag o nombre>` (ej. `/perfil #ABC123XY` o `/perfil jeho`)."]

        try:
            clan = await self.coc_client.get_clan(config.CLAN_TAG)
        except coc.HTTPException:
            return ["La API tuvo un error consultando el clan, intenta de nuevo en un rato."]

        miembro = self._buscar_miembro(clan, identificador)
        if not miembro:
            return [f"{identificador} no está en el clan ahora mismo (¿tag o nombre mal escrito?)."]

        lineas = [f"**Perfil — {miembro.name}** ({miembro.tag})\n"]

        # Reputacion de la temporada actual
        temporada = reputacion.temporada_actual()
        ranking = storage.ranking_reputacion(self.db, temporada)
        rep = ranking.get(miembro.tag)
        if rep:
            cat = rep["categorias"]
            guerra = cat.get("guerra_ataque", 0) + cat.get("guerra_defensa", 0) + cat.get("guerra_no_ataco", 0)
            lineas.append(
                f"**Reputación (temporada {temporada}):** {rep['total']:.0f} pts "
                f"(guerra {guerra:.0f} · donaciones {cat.get('donaciones', 0):.0f} · "
                f"capital {cat.get('capital', 0):.0f} · clan games {cat.get('clan_games', 0):.0f})"
            )
        else:
            lineas.append("**Reputación:** sin datos todavía esta temporada.")

        # KDA historico de guerra
        stats = storage.stats_por_jugador(self.db).get(miembro.tag)
        if stats:
            prom_destruccion = stats["destruccion_total"] / stats["ataques"] if stats["ataques"] else 0
            lineas.append(
                f"**KDA de guerra:** {stats['ataques']} ataques, {stats['estrellas_ataque']} estrellas "
                f"({prom_destruccion:.0f}% destr. prom · TH arriba/igual/abajo: "
                f"{stats['subio']}/{stats['igual']}/{stats['bajo']}) · defensa: "
                f"{stats['veces_atacado']}x atacado, {stats['estrellas_recibidas']} estrellas recibidas"
            )
        else:
            lineas.append("**KDA de guerra:** sin guerras guardadas todavía.")

        # Donaciones en vivo (temporada actual, directo del clan)
        ratio = f"{miembro.donations / miembro.received:.1f}x" if miembro.received else "—"
        lineas.append(f"**Donaciones:** {miembro.donations} dadas / {miembro.received} recibidas ({ratio})")

        # Capital del ultimo Raid Weekend
        try:
            raid_log = await self.coc_client.get_raid_log(config.CLAN_TAG, limit=1)
            entradas = list(raid_log)
        except coc.HTTPException:
            entradas = []

        if not entradas:
            lineas.append("**Capital:** sin datos todavía de Raid Weekends.")
        else:
            raid_miembro = next((m for m in entradas[0].members if m.tag == miembro.tag), None)
            if raid_miembro:
                limite = raid_miembro.attack_limit + raid_miembro.bonus_attack_limit
                lineas.append(
                    f"**Capital (último Raid Weekend):** {raid_miembro.capital_resources_looted} oro "
                    f"({raid_miembro.attack_count}/{limite} ataques)"
                )
            else:
                lineas.append("**Capital (último Raid Weekend):** no participó.")

        return lineas

    async def _autocomplete_jugador(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            clan = await self.coc_client.get_clan(config.CLAN_TAG)
        except coc.HTTPException:
            return []
        current_low = current.lower()
        return [
            app_commands.Choice(name=m.name, value=m.tag) for m in clan.members if current_low in m.name.lower()
        ][:25]

    @app_commands.command(
        name="perfil", description="Vista completa de un jugador: reputación, KDA, donaciones y capital"
    )
    @app_commands.describe(jugador="Nombre o tag del jugador")
    @app_commands.autocomplete(jugador=_autocomplete_jugador)
    async def perfil(self, interaction: discord.Interaction, jugador: str):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_perfil(argumentos=jugador))


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
