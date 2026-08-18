import discord
from discord import app_commands
from discord.ext import commands


class Ayuda(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.comandos_wa["comandos"] = self._lineas_comandos_wa

    @app_commands.command(name="comandos", description="Lista todos los comandos disponibles del bot")
    async def comandos(self, interaction: discord.Interaction):
        comandos = sorted(
            (c for c in self.bot.tree.walk_commands() if isinstance(c, app_commands.Command)),
            key=lambda c: c.qualified_name,
        )
        lineas = ["**Comandos disponibles**\n"]
        lineas += [f"`/{c.qualified_name}` — {c.description}" for c in comandos]
        await interaction.response.send_message("\n".join(lineas))

    async def _lineas_comandos_wa(self, argumentos: str = "", remitente: str = "") -> list[str]:
        lineas = ["**Comandos disponibles por acá**\n"]
        lineas += [f"/{nombre}" for nombre in sorted(self.bot.comandos_wa)]
        return lineas


async def setup(bot: commands.Bot):
    await bot.add_cog(Ayuda(bot))
