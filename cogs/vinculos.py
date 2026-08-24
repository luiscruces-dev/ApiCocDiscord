"""
Vincula un numero de WhatsApp con un tag de jugador del clan, para poder
etiquetarlo directo cuando /recordar detecta que le faltan ataques en la
guerra activa. Relacion muchos-a-muchos: un mismo numero puede tener
varias cuentas vinculadas (multicuenta, cada /vincular con un tag nuevo
suma, no reemplaza), y una misma cuenta puede tener mas de un numero
vinculado (ej. una pareja que juega desde un tag compartido — a los dos
les llega la mencion cuando le falta atacar a esa cuenta).

A diferencia del resto de comandos_wa, estos SI escriben en la base de
datos (ver README de whatsapp-bridge, que documenta por que los comandos
que cambian estado del clan quedan exclusivos de Discord). Se hace una
excepcion acá porque vincularse no afecta al clan en nada — en el peor caso
alguien se vincula con el tag equivocado, y se corrige mandando /vincular
de nuevo o /desvincular.

Ademas de /recordar (a pedido, en el grupo), tres loops de fondo avisan
solos por WhatsApp:
- aviso_pre_guerra (cada 10 min) manda un chiste avisando que la guerra
  arranca en <=30 min, mientras siga en dia de preparacion.
- aviso_inicio_guerra (cada 10 min) manda un aviso especial UNA vez apenas
  arranca cada guerra ("hemos iniciado guerra").
- recordatorio_automatico (cada 4h) manda el recordatorio normal mientras
  la guerra siga activa y falte alguien por atacar.
Los tres son silenciosos el resto del tiempo (no avisan "no hay guerra"
seguido, eso solo lo dice /recordar cuando alguien lo pide a mano).
"""
import logging
import random
from datetime import datetime, timedelta, timezone

import coc
from discord.ext import commands, tasks

import config
import storage
import whatsapp
from utils import tiempo_legible

MINUTOS_AVISO_PRE_GUERRA = 30

FRASES_PRE_GUERRA = [
    "¡Preparen esas nalgas, mi gente! La guerra contra **{rival}** arranca en {tiempo}.",
    "Alerta clan: en {tiempo} empieza la guerra vs **{rival}**. Guarden el celular y saquen las tropas.",
    "¡Se acabó el relajo! Guerra contra **{rival}** en {tiempo} — quien no esté listo que se vaya despidiendo del pleno.",
    "En {tiempo} arranca la guerra vs **{rival}**. Revisen su ejército, que después no digan que no avisé.",
    "¡Prepárense panas! {tiempo} para que empiece la guerra contra **{rival}**, no me dejen a nadie durmiendo.",
    "Faltan {tiempo} pa' la guerra vs **{rival}**. El que no tenga hechizos listos, que vaya corriendo.",
    "¡Se respira guerra! En {tiempo} arrancamos contra **{rival}**, ánimo y a dar cátedra.",
    "{tiempo} y contando pa' la guerra vs **{rival}**. Ojalá tengan el CV lleno, no vayan a salir con excusas después.",
    "Última llamada: guerra contra **{rival}** en {tiempo}. Preparen tropas, hechizos y las nalgas.",
    "¡Aquí no se juega, mi gente! {tiempo} pa' la guerra vs **{rival}**, el que no ataque bien ya sabe lo que le espera.",
    "En {tiempo} se prende la guerra contra **{rival}**. Bájense el nervio y suban el ejército.",
    "¡Sepan que viene guerra! {tiempo} contra **{rival}** — a calentar motores, que después no hay excusa.",
]


class Vinculos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["vincular"] = self._vincular
        bot.comandos_wa["desvincular"] = self._desvincular
        bot.comandos_wa["recordar"] = self._recordar
        self.aviso_pre_guerra.start()
        self.aviso_inicio_guerra.start()
        self.recordatorio_automatico.start()

    def cog_unload(self):
        self.aviso_pre_guerra.cancel()
        self.aviso_inicio_guerra.cancel()
        self.recordatorio_automatico.cancel()
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

        otros_numeros = [jid for jid in storage.jids_de_tag(self.db, miembro.tag) if jid != remitente]
        if otros_numeros:
            # Cuenta compartida (ej. una pareja): a partir de ahora se
            # etiqueta a todos los numeros vinculados a esta cuenta, no
            # solo al que acaba de escribir /vincular.
            lineas.append(
                f"Ojo: esta cuenta ya tenía {len(otros_numeros)} número(s) vinculado(s) — "
                f"ahora a todos les va a llegar la mención en `/recordar`."
            )
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

    async def _estado_guerra_faltan(self):
        """(estado, guerra, faltan). estado in: privado, error_api, sin_guerra,
        preparacion, terminada, ok. guerra/faltan solo estan poblados en los
        casos donde tiene sentido (preparacion/terminada traen guerra sin
        faltan; ok trae los dos)."""
        try:
            guerra = await self.coc_client.get_current_war(config.CLAN_TAG)
        except coc.PrivateWarLog:
            return "privado", None, None
        except coc.HTTPException:
            return "error_api", None, None

        if guerra is None or guerra.state == "notInWar":
            return "sin_guerra", None, None
        if guerra.state == "preparation":
            return "preparacion", guerra, None
        if guerra.state == "warEnded":
            return "terminada", guerra, None

        faltan = [m for m in guerra.clan.members if len(m.attacks) < guerra.attacks_per_member]
        return "ok", guerra, faltan

    def _armar_recordatorio(self, guerra, faltan, encabezado: str | None = None) -> tuple[list[str], list[str]]:
        jids = storage.jids_por_tag(self.db)
        tiempo = tiempo_legible(guerra.end_time.seconds_until)
        encabezado = encabezado or f"Muchachos, recuerden atacar en guerra contra **{guerra.opponent.name}**"
        marcador = f"Vamos {guerra.clan.stars}⭐ vs {guerra.opponent.stars}⭐ del rival"
        lineas = [f"{encabezado}, tienen {tiempo}:", marcador, ""]
        menciones = []
        for m in sorted(faltan, key=lambda m: m.map_position):
            usados = len(m.attacks)
            jids_cuenta = jids.get(m.tag, [])
            if jids_cuenta:
                # El JID real (con su dominio real: @s.whatsapp.net o @lid segun
                # como direccione WhatsApp a esta persona en el grupo) va tal
                # cual en "menciones" — el puente NO debe reconstruirlo a mano,
                # porque adivinar mal el dominio hace que WhatsApp no lo
                # reconozca como mencion real. Si la cuenta tiene mas de un
                # numero vinculado (ej. una pareja compartiendo un tag), se
                # etiqueta a todos.
                menciones_texto = " ".join(f"@{jid.split('@')[0]}" for jid in jids_cuenta)
                quien = f"{menciones_texto} ({m.name})"
                menciones.extend(jids_cuenta)
            else:
                quien = m.name
            lineas.append(f"- {quien} — {usados}/{guerra.attacks_per_member} ataques")
        return lineas, menciones

    async def _recordar(self, argumentos: str = "", remitente: str = "") -> tuple[list[str], list[str]]:
        estado, guerra, faltan = await self._estado_guerra_faltan()
        if estado == "privado":
            return ["El registro de guerra de este clan está en privado, no puedo ver quién atacó."], []
        if estado == "error_api":
            return ["La API tuvo un error consultando la guerra, intenta de nuevo en un rato."], []
        if estado == "sin_guerra":
            return ["El clan no está en guerra ahora mismo."], []
        if estado == "preparacion":
            faltan_para_iniciar = tiempo_legible(guerra.start_time.seconds_until)
            return [
                f"La guerra vs **{guerra.opponent.name}** está en día de preparación todavía — "
                f"arranca en aproximadamente {faltan_para_iniciar}."
            ], []
        if estado == "terminada":
            return ["La guerra ya terminó."], []

        if not faltan:
            return [f"Ya atacaron todos contra **{guerra.opponent.name}**, no falta nadie."], []
        return self._armar_recordatorio(guerra, faltan)

    @tasks.loop(minutes=10)
    async def aviso_pre_guerra(self):
        # Mismo espiritu que aviso_inicio_guerra: chequeo cada 10 min, se
        # guarda en avisos_pre_guerra para no repetirlo si el bot reinicia
        # a mitad de la ventana de 30 min ya avisada.
        if not whatsapp.configurado():
            return
        try:
            estado, guerra, _faltan = await self._estado_guerra_faltan()
            if estado != "preparacion":
                return

            segundos = guerra.start_time.seconds_until
            if segundos > MINUTOS_AVISO_PRE_GUERRA * 60:
                return

            start_time = guerra.start_time.raw_time
            opponent_tag = guerra.opponent.tag
            if storage.guerra_pre_avisada(self.db, start_time, opponent_tag):
                return
            storage.marcar_guerra_pre_avisada(self.db, start_time, opponent_tag)

            frase = random.choice(FRASES_PRE_GUERRA).format(
                rival=guerra.opponent.name, tiempo=tiempo_legible(segundos)
            )
            texto = whatsapp.formatear_para_whatsapp(frase)
            await whatsapp.esperar_jitter(30)
            ok, detalle = await whatsapp.enviar(texto)
            if not ok:
                logging.getLogger("apicocdiscord").warning("aviso_pre_guerra: no se pudo enviar (%s)", detalle)
        except Exception:
            logging.getLogger("apicocdiscord").exception("aviso_pre_guerra: error inesperado, reintento en 10 min")

    @aviso_pre_guerra.before_loop
    async def antes_de_avisar_pre_guerra(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def aviso_inicio_guerra(self):
        # Chequeo frecuente (mismo intervalo que revisar_guerra en
        # historial_guerras.py) para pescar el arranque de la guerra rapido,
        # no recien en el proximo tick del recordatorio de 4h. Se guarda en
        # avisos_inicio_guerra para no repetir el aviso si el bot reinicia
        # a mitad de una guerra ya avisada.
        if not whatsapp.configurado():
            return
        try:
            estado, guerra, faltan = await self._estado_guerra_faltan()
            if estado != "ok":
                return

            start_time = guerra.start_time.raw_time
            opponent_tag = guerra.opponent.tag
            if storage.guerra_inicio_avisado(self.db, start_time, opponent_tag):
                return

            storage.marcar_guerra_inicio_avisado(self.db, start_time, opponent_tag)
            if not faltan:
                return

            lineas, menciones = self._armar_recordatorio(
                guerra, faltan, encabezado="📢 *CLAN, HEMOS INICIADO GUERRA. RECUERDEN ATACAR*"
            )
            texto = whatsapp.formatear_para_whatsapp("\n".join(lineas))
            await whatsapp.esperar_jitter(60)
            ok, detalle = await whatsapp.enviar(texto, mentions=menciones)
            if not ok:
                logging.getLogger("apicocdiscord").warning("aviso_inicio_guerra: no se pudo enviar (%s)", detalle)
        except Exception:
            logging.getLogger("apicocdiscord").exception("aviso_inicio_guerra: error inesperado, reintento en 10 min")

    @aviso_inicio_guerra.before_loop
    async def antes_de_avisar_inicio(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=4)
    async def recordatorio_automatico(self):
        # Mismo espiritu que revisar_guerra en historial_guerras.py: este loop
        # tiene que sobrevivir meses corriendo solo, cualquier error se ignora
        # y se reintenta en el proximo ciclo, nunca se cae. A diferencia de
        # /recordar (a pedido), acá NO se avisa nada si no hay guerra activa o
        # ya atacaron todos — solo interrumpe cuando hay algo que decir.
        if not whatsapp.configurado():
            return
        try:
            estado, guerra, faltan = await self._estado_guerra_faltan()
            if estado != "ok" or not faltan:
                return

            # tasks.loop dispara una vez apenas arranca (osea, en cada
            # reinicio/deploy del bot) ademas de cada 4h. Sin este chequeo,
            # reiniciar el bot durante una guerra activa manda un
            # recordatorio de mas cada vez -- por eso se guarda el ultimo
            # envio real y se exige un margen (un poco menos de 4h, por si
            # el tick natural cae un ratito antes) antes de repetir.
            ultimo = storage.ultimo_recordatorio_automatico(self.db)
            if ultimo:
                desde_ultimo = datetime.now(timezone.utc) - datetime.fromisoformat(ultimo)
                if desde_ultimo < timedelta(hours=3, minutes=30):
                    return

            lineas, menciones = self._armar_recordatorio(guerra, faltan)
            texto = whatsapp.formatear_para_whatsapp("\n".join(lineas))
            await whatsapp.esperar_jitter(180)
            ok, detalle = await whatsapp.enviar(texto, mentions=menciones)
            if ok:
                storage.marcar_recordatorio_automatico_enviado(self.db)
            else:
                logging.getLogger("apicocdiscord").warning("recordatorio_automatico: no se pudo enviar (%s)", detalle)
        except Exception:
            logging.getLogger("apicocdiscord").exception("recordatorio_automatico: error inesperado, reintento en 4h")

    @recordatorio_automatico.before_loop
    async def antes_de_recordar_auto(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Vinculos(bot))
