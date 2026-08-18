import discord
from discord import app_commands
from discord.ext import commands

import whatsapp


class WhatsApp(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="enviarwsp", description="Reenvía un mensaje al grupo de WhatsApp del clan")
    @app_commands.describe(mensaje="Texto a mandar al grupo de WhatsApp")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enviarwsp(self, interaction: discord.Interaction, mensaje: str):
        await interaction.response.defer(ephemeral=True)
        ok, detalle = await whatsapp.enviar(mensaje)
        if ok:
            await interaction.followup.send(f"Enviado al grupo de WhatsApp:\n> {mensaje}")
        else:
            await interaction.followup.send(f"No se pudo enviar: {detalle}", ephemeral=True)

    @enviarwsp.error
    async def enviarwsp_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "Este comando es solo para quienes pueden gestionar el servidor (para evitar spam al grupo de WhatsApp).",
                ephemeral=True,
            )
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(WhatsApp(bot))
