import os

from dotenv import load_dotenv

load_dotenv()


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

# Proxy de RoyaleAPI por defecto soluciona el problema de IP dinámica.
# Docs https://docs.royaleapi.com/proxy.html por si acaso
COC_BASE_URL = os.getenv("COC_BASE_URL", "https://cocproxy.royaleapi.dev/v1")
