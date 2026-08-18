import logging

import httpx

import config

log = logging.getLogger("apicocdiscord")


def configurado() -> bool:
    return bool(config.WHATSAPP_BRIDGE_URL and config.WHATSAPP_BRIDGE_TOKEN)


async def enviar(texto: str) -> tuple[bool, str]:
    """Reenvía texto al grupo de WhatsApp vía whatsapp-bridge. Devuelve (ok, detalle)."""
    if not configurado():
        return False, "El puente de WhatsApp no está configurado (faltan WHATSAPP_BRIDGE_URL / WHATSAPP_BRIDGE_TOKEN en .env)."

    url = config.WHATSAPP_BRIDGE_URL.rstrip("/") + "/send"
    headers = {"Authorization": f"Bearer {config.WHATSAPP_BRIDGE_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={"text": texto}, headers=headers)
    except httpx.RequestError as e:
        log.warning("whatsapp.enviar: no se pudo contactar el puente (%s)", e)
        return False, "No se pudo contactar el puente de WhatsApp (¿está corriendo?)."

    if resp.status_code == 200:
        return True, "Enviado."

    log.warning("whatsapp.enviar: el puente respondió %s: %s", resp.status_code, resp.text)
    return False, f"El puente respondió con error ({resp.status_code})."
