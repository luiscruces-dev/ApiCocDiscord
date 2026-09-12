"""API HTTP interna (solo localhost) que usa el puente de WhatsApp para ejecutar bot.comandos_wa."""
import inspect
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
        citado = (datos.get("citado") or "").strip()
        fn = bot.comandos_wa.get(nombre)
        if not fn:
            disponibles = ", ".join(sorted(bot.comandos_wa))
            return web.json_response(
                {"error": f"Comando desconocido. Disponibles: {disponibles}"}, status=404
            )

        kwargs = {"argumentos": argumentos, "remitente": remitente}
        if "citado" in inspect.signature(fn).parameters:
            kwargs["citado"] = citado

        try:
            resultado = await fn(**kwargs)
        except Exception:
            log.exception("api_interna: error ejecutando comando '%s' pedido desde WhatsApp", nombre)
            return web.json_response({"error": "Error interno ejecutando el comando"}, status=500)

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
