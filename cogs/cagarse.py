"""
Comando de relajo para el clan: le tira un roast en venezolano a quien se
mando una cagada atacando en guerra (o donde sea). Es puro chiste entre
panas, no hay logica de Clash detras -- solo elige una frase al azar y la
rellena con el nombre/mencion de la victima.

Ademas de a pedido (/cagarse), un loop de fondo (revisar_ataques) detecta
ataques destacados (para bien o para mal) durante una guerra activa y manda
un mensaje automatico al grupo de WhatsApp -- igual que el resto de avisos
automaticos del clan, nunca a Discord. Tres casos, cada uno con su tono:
- Ataca hacia arriba (rival de TH mas alto) y saca 2+ estrellas: mérito real
  -- FRASES_ELOGIO ("bien ataque, compai").
- Ataca hacia abajo (rival de TH mas bajo) y no saca el pleno (3 estrellas):
  no hay excusa, el TH estaba a favor -- FRASES_INFERIOR ("tratame en serio").
- Ataca parejo o hacia arriba y saca 0 o 1 estrella: cagada normal, ahi si
  hay margen -- FRASES de siempre.
Atacar hacia arriba y sacar 0-1 estrella no dispara nada -- es lo esperable,
ni roast ni elogio. Cada ataque se identifica por su "order" (unico dentro
de la guerra), asi que no se repite en cada poll aunque el ataque siga en la
lista -- la misma tabla sirve tanto para roasts como para elogios, solo
importa que ya se avise una vez.
"""
import logging
import random

import coc
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
import storage
import whatsapp

FRASES = [
    "¡{jugador}, se te fue el ataque más arrecho que un mono con tenis! 🐒👟",
    "{jugador}, dejaste esa base más entera que promesa de político. ¡Qué pena contigo!",
    "Epa {jugador}, ¿tú atacaste o le mandaste un mensaje de texto a la base? Porque estrellas no sacaste ni una.",
    "{jugador}, esa cagada fue tan grande que hasta el Rey Bárbaro se quedó viendo. ¡Vergación!",
    "¡Fino {jugador}! Le regalaste el ataque al enemigo más rápido que pana pidiendo cotufas.",
    "{jugador}, mi pana, esa base te quedó grande. Métete a jugar dominó mejor.",
    "¿Te pico el kulo, {jugador}? Porque esa base la dejaste más sana que abuela en misa.",
    "{jugador} atacó y la base dijo 'ni se sintió'. ¡Qué oso más grande, chamo!",
    "{jugador}, se te salió el hechizo, se te salió la tropa, y se te salió hasta la paciencia del clan. ¡Cágalo!",
    "¡{jugador} en su línea, dejando estrellas ajenas más intactas que su autoestima después de este ataque!",
    "Esa fue peor que arepa quemada, {jugador}. Cero estrellas, cero honor, puro relajo.",
    "{jugador}, hasta tu mamá vio ese ataque y te dijo 'mijo, dedícate a otra cosa'.",
    "¡{jugador}, ese ataque estuvo más perdido que turista de noche sin GPS!",
    "Se cagó todo, {jugador}. Guardaste el ataque pa'l final y lo usaste pa' regalar loot. ¡Aplauso de cotorra! 👏",
    "{jugador}, en tu próxima vida pide nacer con mejor puntería, porque en esta ya se te fue el chance.",
    "¡Qué vaina más arrecha, {jugador}! Esa base se rió de ti en 4K.",
    "¿Y esa táctica, {jugador}? Porque yo vi puro Barbarian corriendo como pollo sin cabeza.",
    "{jugador}, gastaste el CV en tropas y terminaste regalando trofeos como Santa Claus. ¡Ho ho ho, qué oso!",
    "Esa base te agarró de payaso, {jugador}. Ni el Grand Warden se salvó de la vergüenza.",
    "{jugador}, atacaste con más nervios que examinado sin estudiar. Se te olvidó hasta el hechizo de rabia.",
    "¡Mano {jugador}, esa fue una masacre... pero de tu propio ejército! El enemigo ni sudó.",
    "{jugador}, tú no perdiste el ataque, tú lo regalaste envuelto pa' regalo con moñito y todo. 🎀",
    "Esa base quedó más intacta que la virginidad de un monje, {jugador}. ¡Qué fiasco!",
    "{jugador}, si el ataque fuera examen, reprobaste hasta la firma.",
    "¡Epa {jugador}! Con esa puntería deberías dedicarte a lanzar cotufas al zafacón y ver si por lo menos ahí atinas.",
    "{jugador}, tú no atacaste, tú fuiste de visita turística a ver la base y te devolviste.",
    "Ese ataque estuvo tan malo, {jugador}, que hasta el clan enemigo te dio like.",
    "{jugador}, dejaste el CV botado como carro varado en la Cota Mil.",
    "¡Qué show, {jugador}! Le hiciste más daño a tu autoestima que a la base.",
    "{jugador}, ¿tú compraste la Pase de Temporada pa' esto? Ni pa'l saldo del teléfono te alcanzó ese ataque.",
    "Esa base te vio llegar y dijo 'tranquila, este no rompe ni un huevo', {jugador}.",
    "{jugador}, mejor dedícate a donar tropas, porque atacando eres un peligro público.",
    "¡Ay {jugador}! Esa fue floja hasta pa'l TH9 de tu abuela.",
]

# Caso aparte: atacar a un TH mas bajo y no sacar el pleno. Ahi no hay
# excusa de dificultad -- el tono es mas de "faltarle el respeto al clan"
# que de cagada comun.
FRASES_INFERIOR = [
    "Uy mano {jugador}, trátame en serio, ¿cómo no vas a sacar pleno contra un TH más bajo?",
    "{jugador}, ese TH le quedó grande a la base y pequeño a la excusa. ¡Trátame en serio, pana!",
    "¿En serio {jugador}? Le ganabas en TH y ni así completaste. Eso no se hace ni de vaina.",
    "{jugador}, ese rival estaba más fácil que examen de kínder y tú ahí, dejando estrellas botadas.",
    "¡Trátame en serio, {jugador}! Con esa ventaja de TH y no sacaste el pleno, eso ya es falta de respeto.",
    "{jugador}, ibas ganando de arranque por TH y aun así la regaste. ¡Qué oso, mi pana!",
    "Esa base estaba servida en bandeja, {jugador}, y tú la dejaste ahí, sin ni terminar el plato.",
    "{jugador}, con ese TH de ventaja hasta mi abuela saca pleno. Trátame en serio.",
    "¡Ni jugando en fácil, {jugador}! Bajaste a un TH menor y ni así completaste el ataque.",
    "{jugador}, eso fue tirar el examen fácil a la basura. Un TH más bajo y no sacaste el pleno... ¡vergonzoso!",
    "¡Agárrense que ahí viene Jeho! {jugador}, con esa ventaja de TH y sin pleno, te va a sacar del clan por flojo.",
    "{jugador}, eso que hiciste es currículum pa' que Jeho te saque del clan. Un TH más bajo y ni el pleno sacaste.",
    "{jugador}, con esa vagancia contra un TH más bajo, Jeho ya está afilando el botón de kickear.",
    "{jugador}, eso no se hace ni de vaina. Si Jeho se entera de ese TH más bajo sin pleno, te vas del clan de una vez.",
    "Epa Jeho, ¿viste esa cagada de ataque de {jugador}? A ese hay que darle como cuello.",
    "Jeho, fíjate lo que hizo {jugador}: TH más bajo y ni el pleno sacó. A ese sí hay que darle cuello, sin lástima.",
]

# Caso contrario: atacar a un TH mas alto y sacar 2 o 3 estrellas. Ahi si hay
# merito real, tono de elogio en vez de roast.
FRASES_ELOGIO = [
    "¡Bien ataque, compai {jugador}! Le rompiste el rancho a un TH más alto que el tuyo.",
    "¡Eso sí es tener pantalones, {jugador}! Atacaste pa'rriba y te la comiste completa.",
    "¡Qué maquinaria, {jugador}! Ese TH más alto ni se la vio venir.",
    "¡Sepa, {jugador}! Le diste durísimo a un TH por encima tuyo, así se juega.",
    "{jugador}, ese sí es un pana que ataca con hambre. TH más alto y lo dejaste temblando.",
    "¡Fino ese ataque, {jugador}! Subiste de TH y aun así rompiste todo.",
    "¡Eso es nivel, {jugador}! Le ganaste a un TH más grande sin despeinarte.",
    "¡Qué nivel, {jugador}! Esa sí fue una machetiada limpia a un TH más alto.",
    "¡Show completo, compai {jugador}! Ese TH de arriba no le alcanzó pa' pararte.",
    "¡Ese es mi pana, {jugador}! Subiendo de TH y sacando estrellas como si nada.",
]


def _armar_roast(jugador: str, motivo: str | None, pool: list[str] = FRASES) -> str:
    frase = random.choice(pool).format(jugador=jugador)
    if motivo:
        frase += f" (según cuentan, por: _{motivo}_)"
    return frase


class Cagarse(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["cagarse"] = self._lineas_cagarse
        self.revisar_ataques.start()

    def cog_unload(self):
        self.revisar_ataques.cancel()
        self.db.close()

    @property
    def coc_client(self) -> coc.Client:
        return self.bot.coc_client

    async def _lineas_cagarse(
        self, argumentos: str = "", remitente: str = "", citado: str = ""
    ) -> list[str] | tuple[list[str], list[str]]:
        argumentos = (argumentos or "").strip()
        citado = (citado or "").strip()

        if citado:
            # Citaron ("deslizaron sobre") el mensaje de la victima en vez de
            # escribir su nombre -- se la etiqueta de verdad con su JID real,
            # igual que /recordar, y el texto despues de /cagarse (si hay) es
            # directo el motivo, no un nombre.
            cuentas = storage.tags_de_jid(self.db, citado)
            nombre = cuentas[0][1] if cuentas else None
            mencion = f"@{citado.split('@')[0]}"
            jugador = f"{mencion} ({nombre})" if nombre else mencion
            return [_armar_roast(jugador, argumentos or None)], [citado]

        if not argumentos:
            return [
                "Uso: `/cagarse <nombre>` o `/cagarse <nombre> | <motivo>` "
                "(ej. `/cagarse Fulano | dejó el rey en la casa`). "
                "También podés responder (citar) el mensaje de la víctima y mandar `/cagarse` solo."
            ]

        partes = argumentos.split("|", 1)
        jugador = partes[0].strip()
        motivo = partes[1].strip() if len(partes) > 1 and partes[1].strip() else None
        if not jugador:
            return ["Uso: `/cagarse <nombre>` o `/cagarse <nombre> | <motivo>`."]

        return [_armar_roast(jugador, motivo)]

    @app_commands.command(name="cagarse", description="Le tira un roast venezolano a quien se mandó una cagada")
    @app_commands.describe(victima="A quién le vamos a cagar la base", motivo="Opcional: qué fue lo que hizo")
    async def cagarse(self, interaction: discord.Interaction, victima: discord.Member, motivo: str = None):
        await interaction.response.send_message(_armar_roast(victima.mention, motivo))

    @tasks.loop(minutes=10)
    async def revisar_ataques(self):
        # Mismo espiritu que revisar_guerra/aviso_inicio_guerra: este loop
        # tiene que sobrevivir meses corriendo solo, cualquier error se
        # ignora y se reintenta en el proximo ciclo, nunca se cae.
        if not whatsapp.configurado():
            return
        try:
            war = await self.coc_client.get_current_war(config.CLAN_TAG)
            if not war or war.state != "inWar":
                return

            for miembro in war.clan.members:
                for ataque in miembro.attacks:
                    rival = ataque.defender
                    if not rival:
                        continue

                    if rival.town_hall > miembro.town_hall and ataque.stars >= 2:
                        # Atacar hacia arriba y sacar 2-3 estrellas es merito
                        # real -- elogio, no roast.
                        pool = FRASES_ELOGIO
                    elif rival.town_hall < miembro.town_hall and ataque.stars < 3:
                        # Atacar hacia abajo y no sacar pleno no tiene excusa
                        # de dificultad -- tono aparte, mas exigente.
                        pool = FRASES_INFERIOR
                    elif rival.town_hall <= miembro.town_hall and ataque.stars <= 1:
                        # Parejo o hacia abajo y 0-1 estrella: cagada comun.
                        pool = FRASES
                    else:
                        # Hacia arriba con 0-1 estrella (esperable) o parejo
                        # con 2+ (tampoco es cagada): no dispara nada.
                        continue

                    if storage.cagada_avisada(self.db, war.start_time.raw_time, war.opponent.tag, ataque.order):
                        continue
                    storage.marcar_cagada_avisada(self.db, war.start_time.raw_time, war.opponent.tag, ataque.order)

                    jids = storage.jids_de_tag(self.db, miembro.tag)
                    if jids:
                        mencion = " ".join(f"@{jid.split('@')[0]}" for jid in jids)
                        jugador = f"{mencion} ({miembro.name})"
                    else:
                        jugador = miembro.name
                    motivo = f"{ataque.stars}⭐/{ataque.destruction:.0f}% vs TH{rival.town_hall} ({rival.name})"

                    texto = whatsapp.formatear_para_whatsapp(_armar_roast(jugador, motivo, pool))
                    await whatsapp.esperar_jitter(30)
                    ok, detalle = await whatsapp.enviar(texto, mentions=jids)
                    if not ok:
                        logging.getLogger("apicocdiscord").warning("revisar_ataques: no se pudo enviar (%s)", detalle)
        except coc.HTTPException as e:
            logging.getLogger("apicocdiscord").warning("revisar_ataques: error de la API, reintento en 10 min (%s)", e)
        except Exception:
            logging.getLogger("apicocdiscord").exception("revisar_ataques: error inesperado, reintento en 10 min")

    @revisar_ataques.before_loop
    async def antes_de_revisar_ataques(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Cagarse(bot))
