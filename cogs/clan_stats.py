"""
Comandos para ver stats del clan y ayudar a repartir recompensas de forma
justa, usando la API oficial de Clash of Clans.

Ojo con las limitaciones reales de la API (confirmadas en el server de
Discord "Clash API Developers"):
  - Es de solo lectura: ningún comando de acá puede entregar recompensas
    dentro del juego, solo te dice quién se las merece. Repartirlas (in-game,
    con un rol de Discord, etc.) lo sigues haciendo tú.
  - No existe endpoint de puntos de Clan Games: para eso habría que guardar
    una "foto" de los achievements de cada jugador al inicio del evento y
    otra al final, y restar. No está implementado en esta primera versión.
  - Los datos de guerra requieren que el registro de guerra del clan esté
    en público (Ajustes del clan, in-game).
"""
import coc
import discord
from discord import app_commands
from discord.ext import commands

import config

ROLES_ES = {
    "member": "Miembro",
    "admin": "Anciano",
    "coLeader": "Colíder",
    "leader": "Líder",
}

# Pesos del "puntaje de mérito" combinado en /puntaje. Son relativos entre sí
# (no tienen que sumar 1) — ajústalos a lo que tu clan considere justo.
PESO_DONACIONES = 0.4
PESO_GUERRA = 0.3
PESO_CAPITAL = 0.3

LIMITE_CARACTERES = 1900  # margen bajo el límite de 2000 de Discord por mensaje


def rol_legible(rol) -> str:
    crudo = str(getattr(rol, "value", rol))
    return ROLES_ES.get(crudo, crudo)


def normalizar(valores: dict) -> dict:
    """Escala un diccionario tag->valor a 0-1 según el máximo del grupo."""
    maximo = max(valores.values(), default=0)
    if not maximo:
        return {tag: 0.0 for tag in valores}
    return {tag: v / maximo for tag, v in valores.items()}


class ClanStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def _enviar_en_paginas(self, interaction: discord.Interaction, lineas: list[str]):
        bloque = ""
        for linea in lineas:
            if len(bloque) + len(linea) + 1 > LIMITE_CARACTERES:
                await interaction.followup.send(bloque)
                bloque = ""
            bloque += linea + "\n"
        if bloque:
            await interaction.followup.send(bloque)

    @app_commands.command(name="miembros", description="Lista todos los miembros del clan con sus stats básicos")
    async def miembros(self, interaction: discord.Interaction):
        await interaction.response.defer()
        clan = await self.coc_client.get_clan(config.CLAN_TAG)

        lineas = [f"**{clan.name}** ({clan.tag}) — {len(clan.members)} miembros\n"]
        for m in sorted(clan.members, key=lambda m: -m.trophies):
            lineas.append(
                f"`{m.clan_rank:>2}` **{m.name}** ({rol_legible(m.role)}) — "
                f"TH{m.town_hall} · 🏆{m.trophies} · 🎁{m.donations} dadas / {m.received} recibidas"
            )

        await self._enviar_en_paginas(interaction, lineas)

    @app_commands.command(name="donaciones", description="Ranking de donaciones del clan (dadas y recibidas)")
    async def donaciones(self, interaction: discord.Interaction):
        await interaction.response.defer()
        clan = await self.coc_client.get_clan(config.CLAN_TAG)
        ordenados = sorted(clan.members, key=lambda m: -m.donations)

        lineas = [f"**Ranking de donaciones — {clan.name}**\n"]
        for i, m in enumerate(ordenados, start=1):
            ratio = f"{m.donations / m.received:.1f}x" if m.received else "—"
            lineas.append(f"`{i:>2}.` **{m.name}** — {m.donations} dadas / {m.received} recibidas ({ratio})")

        await self._enviar_en_paginas(interaction, lineas)

    @app_commands.command(name="capital", description="Ranking de saqueo de oro de capital del último Raid Weekend")
    async def capital(self, interaction: discord.Interaction):
        await interaction.response.defer()
        raid_log = await self.coc_client.get_raid_log(config.CLAN_TAG, limit=1)
        entradas = list(raid_log)
        if not entradas:
            await interaction.followup.send("Todavía no hay datos de Raid Weekends para este clan.")
            return

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

        await self._enviar_en_paginas(interaction, lineas)

    @app_commands.command(name="guerra", description="Estado de la guerra actual del clan")
    async def guerra(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            guerra_actual = await self.coc_client.get_current_war(config.CLAN_TAG)
        except coc.PrivateWarLog:
            await interaction.followup.send(
                "El registro de guerra de este clan está en privado. "
                "Actívalo in-game en Ajustes del clan para poder ver esto."
            )
            return

        if guerra_actual is None or guerra_actual.state == "notInWar":
            await interaction.followup.send("El clan no está en guerra ahora mismo.")
            return

        lineas = [
            f"**Guerra vs {guerra_actual.opponent.name}** — estado: {guerra_actual.state} · "
            f"{guerra_actual.team_size} vs {guerra_actual.team_size}\n"
        ]
        for m in sorted(guerra_actual.clan.members, key=lambda m: m.map_position):
            mejor_destruccion = max((a.destruction for a in m.attacks), default=0)
            lineas.append(
                f"`{m.map_position:>2}.` **{m.name}** — {len(m.attacks)}/{guerra_actual.attacks_per_member} "
                f"ataques · ⭐{m.star_count} · {mejor_destruccion:.0f}% mejor destrucción"
            )

        await self._enviar_en_paginas(interaction, lineas)

    @app_commands.command(
        name="puntaje",
        description="Ranking combinado (donaciones + guerra + capital) para repartir recompensas de forma justa",
    )
    async def puntaje(self, interaction: discord.Interaction):
        await interaction.response.defer()
        clan = await self.coc_client.get_clan(config.CLAN_TAG)

        nombres = {m.tag: m.name for m in clan.members}
        donaciones = {m.tag: m.donations for m in clan.members}
        estrellas_guerra = {tag: 0 for tag in nombres}
        oro_capital = {tag: 0 for tag in nombres}

        try:
            guerra_actual = await self.coc_client.get_current_war(config.CLAN_TAG)
            if guerra_actual and guerra_actual.state != "notInWar":
                for m in guerra_actual.clan.members:
                    if m.tag in estrellas_guerra:
                        estrellas_guerra[m.tag] = m.star_count
        except coc.PrivateWarLog:
            pass  # sin este componente, pero seguimos con el resto

        raid_log = await self.coc_client.get_raid_log(config.CLAN_TAG, limit=1)
        entradas = list(raid_log)
        if entradas:
            for m in entradas[0].members:
                if m.tag in oro_capital:
                    oro_capital[m.tag] = m.capital_resources_looted

        n_don = normalizar(donaciones)
        n_gue = normalizar(estrellas_guerra)
        n_cap = normalizar(oro_capital)

        puntajes = {
            tag: 100
            * (
                PESO_DONACIONES * n_don.get(tag, 0)
                + PESO_GUERRA * n_gue.get(tag, 0)
                + PESO_CAPITAL * n_cap.get(tag, 0)
            )
            for tag in nombres
        }
        ranking = sorted(puntajes.items(), key=lambda kv: -kv[1])

        lineas = [
            f"**Puntaje de mérito — {clan.name}** "
            f"(donaciones {PESO_DONACIONES:.0%} · guerra {PESO_GUERRA:.0%} · capital {PESO_CAPITAL:.0%})\n"
        ]
        for i, (tag, score) in enumerate(ranking, start=1):
            lineas.append(
                f"`{i:>2}.` **{nombres[tag]}** — {score:.1f} pts "
                f"(🎁{donaciones[tag]} · ⭐{estrellas_guerra[tag]} · 🏰{oro_capital[tag]})"
            )

        await self._enviar_en_paginas(interaction, lineas)


async def setup(bot: commands.Bot):
    await bot.add_cog(ClanStats(bot))
