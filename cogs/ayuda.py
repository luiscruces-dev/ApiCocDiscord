import discord
from discord import app_commands
from discord.ext import commands


class Ayuda(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="comandos", description="Lista todos los comandos disponibles del bot")
    async def comandos(self, interaction: discord.Interaction):
        comandos = sorted(
            (c for c in self.bot.tree.walk_commands() if isinstance(c, app_commands.Command)),
            key=lambda c: c.qualified_name,
        )
        lineas = ["**Comandos disponibles**\n"]
        lineas += [f"`/{c.qualified_name}` — {c.description}" for c in comandos]
        await interaction.response.send_message("\n".join(lineas))


async def setup(bot: commands.Bot):
    await bot.add_cog(Ayuda(bot))
