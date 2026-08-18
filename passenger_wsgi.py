import asyncio
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))

import bot as bot_module  # noqa: E402

log = logging.getLogger("apicocdiscord.passenger")

_bot_thread: threading.Thread | None = None
_lock = threading.Lock()


def _run_bot():
    try:
        asyncio.run(bot_module.bot.start(bot_module.config.DISCORD_TOKEN))
    except Exception:
        log.exception("El bot se cayo, se reintentara en el proximo request")


def ensure_bot_running():
    global _bot_thread
    with _lock:
        if _bot_thread is None or not _bot_thread.is_alive():
            _bot_thread = threading.Thread(target=_run_bot, daemon=True)
            _bot_thread.start()


ensure_bot_running()


def application(environ, start_response):
    ensure_bot_running()
    alive = _bot_thread is not None and _bot_thread.is_alive()
    body = b"Bot activo" if alive else b"Bot reiniciando..."
    status = "200 OK"
    headers = [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))]
    start_response(status, headers)
    return [body]
