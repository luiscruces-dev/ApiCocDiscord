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

        if guerra.is_cwl:
            # Toda la proyeccion depende de emparejar por espejo (mismo
            # map_position de los dos lados), y en CWL cada clan numera su
            # propio roster de todo el grupo de liga -- no se resincroniza
            # 1-15 por ronda, asi que el numero no se corresponde entre los
            # dos lados. Mejor avisar que inventar una proyeccion con datos
            # que no significan lo que el comando cree que significan.
            return [
                f"**Estimación — guerra vs {guerra.opponent.name}**\n",
                "Esta guerra es de CWL: en liga cada clan numera su roster de todo el grupo (no se "
                "resincroniza 1-15 por ronda), así que el emparejamiento por espejo que usa este comando "
                "no es válido acá. Usá `/guerra` para ver el marcador real mientras tanto.",
            ]

        stats_clan = storage.stats_por_diferencia_th(self.db)
        rival_por_posicion = {m.map_position: m for m in guerra.opponent.members}

        # El maximo real de una guerra es team_size * 3 (3 estrellas por
        # base rival, sin importar cuantos ataques reciba) -- NO
        # attacks_per_member * 3. war.clan.stars/max_stars ya lo calculan
        # bien del lado oficial, mejor usar eso que sumarlo a mano.
        total_estimado = float(guerra.clan.stars)
        total_posible = guerra.clan.max_stars
        lineas_detalle = []

        for m in sorted(guerra.clan.members, key=lambda m: m.map_position):
            rival = rival_por_posicion.get(m.map_position)
            usados = len(m.attacks)
            pendientes = guerra.attacks_per_member - usados

            if not rival:
                lineas_detalle.append(f"`{m.map_position:>2}.` **{m.name}** — sin rival asignado en esa posición")
                continue

            # best_opponent_attack es el mejor resultado que YA le sacamos a
            # esa base puntual (no m.star_count, que es la suma de estrellas
            # del jugador en SUS ataques y puede superar 3 si reataco la
            # misma base o no coincide con lo que cuenta para el marcador
            # oficial de la guerra).
            estrellas_en_base = rival.best_opponent_attack.stars if rival.best_opponent_attack else 0
            diferencia = rival.town_hall - m.town_hall
            comparacion = f"{diferencia:+d}" if diferencia else "mismo TH"

            if pendientes <= 0 or estrellas_en_base >= 3:
                extra = f", ya usó los {usados} ataques" if usados else ""
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {estrellas_en_base}⭐ en esa base{extra}"
                )
                continue

            margen = 3 - estrellas_en_base  # techo real: no se puede pasar de 3 en una base
            stats, origen = self._estimar_para(m.tag, diferencia, stats_clan)
            if stats:
                estimado_pendientes = min(stats["estrellas_prom"] * pendientes, margen)
                total_estimado += estimado_pendientes
                fuente = "su propio historial" if origen == "personal" else "el historial del clan"
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {estrellas_en_base}⭐ en esa base + "
                    f"~{estimado_pendientes:.1f}⭐ estimadas ({pendientes} pendiente{'s' if pendientes != 1 else ''}, "
                    f"según {fuente}: {stats['estrellas_prom']:.1f}⭐ prom. en {stats['ataques']} ataques a esa diferencia)"
                )
            else:
                lineas_detalle.append(
                    f"`{m.map_position:>2}.` **{m.name}** (TH{m.town_hall}) vs **{rival.name}** "
                    f"(TH{rival.town_hall}, {comparacion}) — {estrellas_en_base}⭐ en esa base, "
                    f"{pendientes} pendiente(s) sin historial a esa diferencia todavía"
                )

        porcentaje = (total_estimado / total_posible * 100) if total_posible else 0
        lineas = [
            f"**Estimación — guerra vs {guerra.opponent.name}**",
            "Las estrellas ya logradas son las oficiales de cada base rival; los ataques pendientes se estiman "
            "contra el espejo (topeado en 3 por base), según el historial del clan por diferencia de TH (poca "
            "muestra todavía = estimación floja, mirá el detalle de cada uno).\n",
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
