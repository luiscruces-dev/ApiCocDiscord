import asyncio
import os
import sys

import coc
from dotenv import load_dotenv

# Gracias Cris por hacerme crashear el bot por los caracteres especiales de tu nombre

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

load_dotenv()
COC_API_TOKEN = os.environ["COC_API_TOKEN"]
CLAN_TAG = os.environ["CLAN_TAG"]
COC_BASE_URL = os.getenv("COC_BASE_URL", "https://cocproxy.royaleapi.dev/v1")


async def main():
    print(f"Conectando via {COC_BASE_URL} ...")
    client = coc.Client(base_url=COC_BASE_URL)
    try:
        await client.login_with_tokens(COC_API_TOKEN)
        print("Login OK, la key funciona.\n")

        clan = await client.get_clan(CLAN_TAG)
        print(f"Clan encontrado: {clan.name} ({clan.tag})")
        print(f"Nivel: {clan.level} | Miembros: {len(clan.members)}/50 | Puntos: {clan.points}\n")

        print("Todos los miembros (por trofeos):")
        for m in sorted(clan.members, key=lambda m: -m.trophies):
            print(
                f"  `{m.clan_rank:>2}` {m.name} — TH{m.town_hall} · {m.trophies} trofeos · "
                f"{m.donations} donadas / {m.received} recibidas"
            )
    except coc.InvalidCredentials:
        print("ERROR: la key no es valida o no tiene el scope correcto.")
    except coc.Forbidden as e:
        print(f"ERROR 403 Forbidden: {e}")
        print("Revisa que la IP whitelisteada en developer.clashofclans.com sea 45.79.218.79")
    except coc.NotFound:
        print(f"ERROR: no se encontro ningun clan con el tag {CLAN_TAG!r}. Revisa el tag.")
    except Exception as e:
        print(f"ERROR inesperado ({type(e).__name__}): {e}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
