"""
API interna (solo localhost) que consulta el puente de WhatsApp para
responder comandos de solo lectura escritos en el grupo. El bot de Discord
sigue siendo el único que habla con la API de Clash y con la base de datos;
esto solo expone esa misma lógica por HTTP para que el puente (Node) la
pueda pedir.

Cada cog registra sus comandos disponibles en bot.comandos_wa: nombre ->
función async(argumentos: str, remitente: str) -> list[str] (las mismas
líneas que arma cada comando de Discord, antes de paginarlas). argumentos es
el resto del texto después del nombre del comando (ej. el tag en
"/vincular #ABC123"), y remitente es el JID de WhatsApp de quien lo escribió
— la mayoría de los comandos ignoran ambos.
"""
import logging

from aiohttp import web

import config
import whatsapp

log = logging.getLogger("apicocdiscord")


def _crear_app(bot) -> web.Application:
    app = web.Application()

    async def comando(request: web.Request) -> web.Response:
        if request.headers.get("Authorization") != f"Bearer {config.BOT_API_TOKEN}":
            return web.json_response({"error": "Token inválido"}, status=401)

        try:
            datos = await request.json()
        except ValueError:
            return web.json_response({"error": "Body inválido, esperaba JSON"}, status=400)

        nombre = (datos.get("nombre") or "").strip().lower()
        argumentos = (datos.get("argumentos") or "").strip()
        remitente = (datos.get("remitente") or "").strip()
        fn = bot.comandos_wa.get(nombre)
        if not fn:
            disponibles = ", ".join(sorted(bot.comandos_wa))
            return web.json_response(
                {"error": f"Comando desconocido. Disponibles: {disponibles}"}, status=404
            )

        try:
            resultado = await fn(argumentos, remitente)
        except Exception:
            log.exception("api_interna: error ejecutando comando '%s' pedido desde WhatsApp", nombre)
            return web.json_response({"error": "Error interno ejecutando el comando"}, status=500)

        # La mayoría de los comandos devuelven solo list[str]. Los que
        # etiquetan gente (ej. /recordar) devuelven además la lista de JIDs
        # reales a mencionar — el puente los usa tal cual, sin reconstruirlos.
        if isinstance(resultado, tuple):
            lineas, menciones = resultado
        else:
            lineas, menciones = resultado, []

        return web.json_response({
            "texto": whatsapp.formatear_para_whatsapp("\n".join(lineas)),
            "menciones": menciones,
        })

    app.router.add_post("/comando", comando)
    return app


async def iniciar(bot):
    app = _crear_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", config.BOT_API_PORT)
    await site.start()
    log.info("API interna escuchando en 127.0.0.1:%s (comandos de WhatsApp)", config.BOT_API_PORT)
