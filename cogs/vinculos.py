"""
Vincula un numero de WhatsApp con un tag de jugador del clan, para poder
etiquetarlo directo cuando /recordar detecta que le faltan ataques en la
guerra activa. Soporta multicuenta: un mismo numero puede tener varias
cuentas vinculadas (cada /vincular con un tag nuevo suma, no reemplaza).

A diferencia del resto de comandos_wa, estos SI escriben en la base de
datos (ver README de whatsapp-bridge, que documenta por que los comandos
que cambian estado del clan quedan exclusivos de Discord). Se hace una
excepcion acá porque vincularse no afecta al clan en nada — en el peor caso
alguien se vincula con el tag equivocado, y se corrige mandando /vincular
de nuevo o /desvincular.
"""
import coc
from discord.ext import commands

import config
import storage


def _tiempo_legible(segundos: int) -> str:
    segundos = max(0, segundos)
    horas, resto = divmod(segundos, 3600)
    minutos = resto // 60
    if horas and minutos:
        return f"{horas}h {minutos}m"
    if horas:
        return f"{horas}h"
    return f"{minutos}m"


class Vinculos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["vincular"] = self._vincular
        bot.comandos_wa["desvincular"] = self._desvincular
        bot.comandos_wa["recordar"] = self._recordar

    def cog_unload(self):
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def _vincular(self, argumentos: str = "", remitente: str = "") -> list[str]:
        if not remitente:
            return ["No pude identificar quién escribió esto, no te pude vincular."]

        tag = coc.utils.correct_tag((argumentos or "").strip())
        if not tag or tag == "#":
            return ["Uso: `/vincular <tag>` (ej. `/vincular #ABC123XY`)."]

        try:
            clan = await self.coc_client.get_clan(config.CLAN_TAG)
        except coc.HTTPException:
            return ["La API tuvo un error consultando el clan, intenta de nuevo en un rato."]

        miembro = clan.get_member(tag)
        if not miembro:
            return [f"{tag} no está en el clan ahora mismo (¿tag mal escrito?)."]

        storage.vincular_wa(self.db, remitente, miembro.tag, miembro.name)
        lineas = [
            f"Listo, quedaste vinculado a **{miembro.name}** ({miembro.tag}). "
            f"Te voy a etiquetar en `/recordar` si te faltan ataques de guerra."
        ]
        cuentas = storage.tags_de_jid(self.db, remitente)
        if len(cuentas) > 1:
            nombres = ", ".join(nombre for _tag, nombre in cuentas)
            lineas.append(f"Tenés {len(cuentas)} cuentas vinculadas a este número: {nombres}.")
        return lineas

    async def _desvincular(self, argumentos: str = "", remitente: str = "") -> list[str]:
        if not remitente:
            return ["No pude identificar quién escribió esto."]

        argumentos = (argumentos or "").strip()
        tag = coc.utils.correct_tag(argumentos) if argumentos else None
        borrados = storage.desvincular_wa(self.db, remitente, tag)

        if borrados == 0:
            return ["No tenías esa cuenta vinculada." if tag else "No tenías ningún tag vinculado."]
        if tag:
            return [f"Listo, desvinculé {tag}."]
        return [f"Listo, te desvinculé {borrados} cuenta{'s' if borrados != 1 else ''}."]

    async def _recordar(self, argumentos: str = "", remitente: str = "") -> tuple[list[str], list[str]]:
        try:
            guerra = await self.coc_client.get_current_war(config.CLAN_TAG)
        except coc.PrivateWarLog:
            return ["El registro de guerra de este clan está en privado, no puedo ver quién atacó."], []
        except coc.HTTPException:
            return ["La API tuvo un error consultando la guerra, intenta de nuevo en un rato."], []

        if guerra is None or guerra.state == "notInWar":
            return ["El clan no está en guerra ahora mismo."], []
        if guerra.state == "preparation":
            return ["La guerra está en día de preparación todavía, no se puede atacar hasta que empiece."], []
        if guerra.state == "warEnded":
            return ["La guerra ya terminó."], []

        faltan = [m for m in guerra.clan.members if len(m.attacks) < guerra.attacks_per_member]
        if not faltan:
            return [f"Ya atacaron todos contra **{guerra.opponent.name}**, no falta nadie."], []

        jids = storage.jids_por_tag(self.db)
        tiempo = _tiempo_legible(guerra.end_time.seconds_until)
        lineas = [
            f"Muchachos, recuerden atacar en guerra contra **{guerra.opponent.name}**, tienen {tiempo}:\n"
        ]
        menciones = []
        for m in sorted(faltan, key=lambda m: m.map_position):
            usados = len(m.attacks)
            jid = jids.get(m.tag)
            if jid:
                # El JID real (con su dominio real: @s.whatsapp.net o @lid segun
                # como direccione WhatsApp a esta persona en el grupo) va tal
                # cual en "menciones" — el puente NO debe reconstruirlo a mano,
                # porque adivinar mal el dominio hace que WhatsApp no lo
                # reconozca como mencion real.
                quien = f"@{jid.split('@')[0]} ({m.name})"
                menciones.append(jid)
            else:
                quien = m.name
            lineas.append(f"- {quien} — {usados}/{guerra.attacks_per_member} ataques")
        return lineas, menciones


async def setup(bot: commands.Bot):
    await bot.add_cog(Vinculos(bot))
