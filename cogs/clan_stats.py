import coc
import discord
from discord import app_commands
from discord.ext import commands

import config
import storage
from utils import enviar_en_paginas, tiempo_legible

ROLES_ES = {
    "member": "Miembro",
    "admin": "Anciano",
    "coLeader": "Colíder",
    "leader": "Líder",
}


def rol_legible(rol) -> str:
    crudo = str(getattr(rol, "value", rol))
    return ROLES_ES.get(crudo, crudo)


class ClanStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["miembros"] = self._lineas_miembros
        bot.comandos_wa["donaciones"] = self._lineas_donaciones
        bot.comandos_wa["capital"] = self._lineas_capital
        bot.comandos_wa["guerra"] = self._lineas_guerra
        bot.comandos_wa["rival"] = self._lineas_rival
        bot.comandos_wa["tags"] = self._lineas_tags

    def cog_unload(self):
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def _lineas_miembros(self, argumentos: str = "", remitente: str = "") -> list[str]:
        clan = await self.coc_client.get_clan(config.CLAN_TAG)
        lineas = [f"**{clan.name}** ({clan.tag}) — {len(clan.members)} miembros\n"]
        for m in sorted(clan.members, key=lambda m: -m.trophies):
            lineas.append(
                f"`{m.clan_rank:>2}` **{m.name}** ({rol_legible(m.role)}) — "
                f"TH{m.town_hall} · Trofeos: {m.trophies} · Donaciones: {m.donations} dadas / {m.received} recibidas"
            )
        return lineas

    @app_commands.command(name="miembros", description="Lista todos los miembros del clan con sus stats básicos")
    async def miembros(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_miembros())

    async def _lineas_tags(self, argumentos: str = "", remitente: str = "") -> list[str]:
        clan = await self.coc_client.get_clan(config.CLAN_TAG)
        jids = storage.jids_por_tag(self.db)
        vinculados = sum(1 for m in clan.members if m.tag in jids)
        lineas = [f"**Tags — {clan.name}** ({vinculados}/{len(clan.members)} vinculados)\n"]
        for m in sorted(clan.members, key=lambda m: m.name.lower()):
            marca = "" if m.tag in jids else " — ⚠️ sin vincular"
            lineas.append(f"**{m.name}** — {m.tag}{marca}")
        return lineas

    @app_commands.command(name="tags", description="Lista el nombre y tag de cada miembro del clan")
    async def tags(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_tags())

    async def _lineas_donaciones(self, argumentos: str = "", remitente: str = "") -> list[str]:
        clan = await self.coc_client.get_clan(config.CLAN_TAG)
        ordenados = sorted(clan.members, key=lambda m: -m.donations)

        lineas = [f"**Ranking de donaciones — {clan.name}**\n"]
        for i, m in enumerate(ordenados, start=1):
            ratio = f"{m.donations / m.received:.1f}x" if m.received else "—"
            lineas.append(f"`{i:>2}.` **{m.name}** — {m.donations} dadas / {m.received} recibidas ({ratio})")
        return lineas

    @app_commands.command(name="donaciones", description="Ranking de donaciones del clan (dadas y recibidas)")
    async def donaciones(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_donaciones())

    async def _lineas_capital(self, argumentos: str = "", remitente: str = "") -> list[str]:
        raid_log = await self.coc_client.get_raid_log(config.CLAN_TAG, limit=1)
        entradas = list(raid_log)
        if not entradas:
            return ["Todavía no hay datos de Raid Weekends para este clan."]

        temporada = entradas[0]
        ordenados = sorted(temporada.members, key=lambda m: -m.capital_resources_looted)

        lineas = [
            f"**Capital Raid Weekend** — {temporada.total_loot} oro total del clan, "
            f"{temporada.attack_count} ataques usados\n"
        ]
        for i, m in enumerate(ordenados, start=1):
            limite_ataques = m.attack_limit + m.bonus_attack_limit
            lineas.append(
                f"`{i:>2}.` **{m.name}** — {m.capital_resources_looted} oro "
                f"({m.attack_count}/{limite_ataques} ataques)"
            )
        return lineas

    @app_commands.command(name="capital", description="Ranking de saqueo de oro de capital del último Raid Weekend")
    async def capital(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_capital())

    async def _obtener_guerra_o_mensaje(self, titulo: str):
        """(guerra, None) si hay guerra con detalle para mostrar (en curso o
        recien terminada), o (None, lineas) con el mensaje a devolver
        directo (error, sin guerra, o en dia de preparacion)."""
        try:
            guerra = await self.coc_client.get_current_war(config.CLAN_TAG)
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

    async def _lineas_guerra(self, argumentos: str = "", remitente: str = "") -> list[str]:
        guerra_actual, mensaje = await self._obtener_guerra_o_mensaje("Guerra vs")
        if mensaje:
            return mensaje

        lineas = [
            f"**Guerra vs {guerra_actual.opponent.name}** — estado: {guerra_actual.state} · "
            f"{guerra_actual.team_size} vs {guerra_actual.team_size}\n"
        ]
        for m in sorted(guerra_actual.clan.members, key=lambda m: m.map_position):
            mejor_destruccion = max((a.destruction for a in m.attacks), default=0)
            lineas.append(
                f"`{m.map_position:>2}.` **{m.name}** — {len(m.attacks)}/{guerra_actual.attacks_per_member} "
                f"ataques · Estrellas: {m.star_count} · {mejor_destruccion:.0f}% mejor destrucción"
            )
        return lineas

    @app_commands.command(name="guerra", description="Estado de la guerra actual del clan")
    async def guerra(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_guerra())

    async def _lineas_rival(self, argumentos: str = "", remitente: str = "") -> list[str]:
        guerra, mensaje = await self._obtener_guerra_o_mensaje("Rival:")
        if mensaje:
            return mensaje

        lineas = [f"**Rival — {guerra.opponent.name}** ({guerra.team_size} vs {guerra.team_size})\n"]

        conteo_nuestro: dict[int, int] = {}
        for m in guerra.clan.members:
            conteo_nuestro[m.town_hall] = conteo_nuestro.get(m.town_hall, 0) + 1
        conteo_rival: dict[int, int] = {}
        for m in guerra.opponent.members:
            conteo_rival[m.town_hall] = conteo_rival.get(m.town_hall, 0) + 1

        lineas.append("**Balance de TH:**")
        for th in sorted(set(conteo_nuestro) | set(conteo_rival), reverse=True):
            lineas.append(f"TH{th} — nosotros: {conteo_nuestro.get(th, 0)} · rival: {conteo_rival.get(th, 0)}")
        lineas.append("")

        nuestro_por_posicion = {m.map_position: m for m in guerra.clan.members}
        lineas.append("**Bases enemigas:**")
        for m in sorted(guerra.opponent.members, key=lambda m: m.map_position):
            mejor_destruccion = max((a.destruction for a in m.attacks), default=0)
            espejo = nuestro_por_posicion.get(m.map_position)
            espejo_texto = f" · espejo: **{espejo.name}** (TH{espejo.town_hall})" if espejo else ""
            lineas.append(
                f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) — {len(m.attacks)}/{guerra.attacks_per_member} "
                f"ataques · Estrellas: {m.star_count} · {mejor_destruccion:.0f}% mejor destrucción{espejo_texto}"
            )
        return lineas

    @app_commands.command(
        name="rival", description="Estado del clan rival en la guerra actual: bases, TH y espejo con el nuestro"
    )
    async def rival(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await enviar_en_paginas(interaction, await self._lineas_rival())


async def setup(bot: commands.Bot):
    await bot.add_cog(ClanStats(bot))
