import logging
import sys

import coc
import discord
from discord.ext import commands

import config

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("apicocdiscord")

intents = discord.Intents.default()


class ClanBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.coc_client: coc.Client | None = None
        # nombre de comando -> función async que devuelve list[str], para que
        # el puente de WhatsApp pueda pedir la misma info que dan los slash
        # commands de solo lectura. Cada cog se registra sola (ver api_interna.py).
        self.comandos_wa: dict = {}

    async def setup_hook(self):
        self.coc_client = coc.Client(base_url=config.COC_BASE_URL)
        await self.coc_client.login_with_tokens(config.COC_API_TOKEN)
        log.info("Cliente de Clash of Clans conectado (base_url=%s)", config.COC_BASE_URL)

        await self.load_extension("cogs.clan_stats")
        await self.load_extension("cogs.historial_guerras")
        await self.load_extension("cogs.clan_games")
        await self.load_extension("cogs.reputacion")
        await self.load_extension("cogs.vinculos")
        await self.load_extension("cogs.perfil")
        await self.load_extension("cogs.ayuda")
        await self.load_extension("cogs.whatsapp")

        if config.BOT_API_TOKEN:
            import api_interna
            await api_interna.iniciar(self)

        if config.GUILD_ID:
            guild = discord.Object(id=int(config.GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands sincronizados al servidor %s", config.GUILD_ID)
        else:
            await self.tree.sync()
            log.info("Slash commands sincronizados globalmente (puede tardar ~1h en aparecer)")

    async def close(self):
        if self.coc_client:
            await self.coc_client.close()
        await super().close()


bot = ClanBot()


@bot.event
async def on_ready():
    log.info("Conectado como %s (id: %s)", bot.user, bot.user.id)


if __name__ == "__main__":
    bot.run(config.DISCORD_TOKEN, log_handler=None)
