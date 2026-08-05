"""
Punto de entrada del bot.

Crea el cliente de la API de Clash of Clans (coc.py, apuntando al proxy de
RoyaleAPI para no depender de tener una IP fija) y el bot de Discord, carga
los comandos y los sincroniza.
"""
import logging

import coc
import discord
from discord.ext import commands

import config

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("apicocdiscord")

intents = discord.Intents.default()


class ClanBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.coc_client: coc.Client | None = None

    async def setup_hook(self):
        self.coc_client = coc.Client(base_url=config.COC_BASE_URL)
        await self.coc_client.login_with_tokens(config.COC_API_TOKEN)
        log.info("Cliente de Clash of Clans conectado (base_url=%s)", config.COC_BASE_URL)

        await self.load_extension("cogs.clan_stats")

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
