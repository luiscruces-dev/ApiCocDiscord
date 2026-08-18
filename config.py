import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(
            f"Falta la variable de entorno '{name}'. "
            f"Copia .env.example a .env y completa los valores."
        )
    return value


DISCORD_TOKEN = require_env("DISCORD_TOKEN")
COC_API_TOKEN = require_env("COC_API_TOKEN")
CLAN_TAG = require_env("CLAN_TAG")

GUILD_ID = os.getenv("GUILD_ID") or None
CLAN_GAMES_CHANNEL_ID = os.getenv("CLAN_GAMES_CHANNEL_ID") or None

# Opcionales: URL y token del puente de WhatsApp (ver whatsapp-bridge/README.md).
# Sin esto, /enviarwsp avisa que no está configurado en vez de fallar.
WHATSAPP_BRIDGE_URL = os.getenv("WHATSAPP_BRIDGE_URL") or None
WHATSAPP_BRIDGE_TOKEN = os.getenv("WHATSAPP_BRIDGE_TOKEN") or None

# Proxy de RoyaleAPI por defecto soluciona el problema de IP dinámica.
# Docs https://docs.royaleapi.com/proxy.html por si acaso
COC_BASE_URL = os.getenv("COC_BASE_URL", "https://cocproxy.royaleapi.dev/v1")
