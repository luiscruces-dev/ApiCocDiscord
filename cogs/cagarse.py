"""
Comando de relajo para el clan: le tira un roast en venezolano a quien se
mando una cagada atacando en guerra (o donde sea). Es puro chiste entre
panas, no hay logica de Clash detras -- solo elige una frase al azar y la
rellena con el nombre/mencion de la victima.
"""
import random

import discord
from discord import app_commands
from discord.ext import commands

import storage

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
]


def _armar_roast(jugador: str, motivo: str | None) -> str:
    frase = random.choice(FRASES).format(jugador=jugador)
    if motivo:
        frase += f" (según cuentan, por: _{motivo}_)"
    return frase


class Cagarse(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = storage.conectar()
        bot.comandos_wa["cagarse"] = self._lineas_cagarse

    def cog_unload(self):
        self.db.close()

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Cagarse(bot))
