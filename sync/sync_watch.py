"""
Fica rodando no seu PC e sincroniza a OLX quando:
  - alguem aperta "Sincronizar agora" no site (pedido pendente), ou
  - o ultimo sync passou do intervalo configurado (agendamento automatico).

Uso:
    python sync/sync_watch.py

Pra iniciar sozinho quando o Windows ligar, crie uma tarefa no Agendador
(veja o README). Deixe a janela aberta ou rode em segundo plano.
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curl_cffi import requests as creq  # noqa: E402

from sync_olx import load_config, run_sync  # noqa: E402


def log(msg):
    print(f"[{datetime.now():%d/%m %H:%M}] {msg}", flush=True)


def parse_ts(value):
    return datetime.fromisoformat(value) if value else None


def api_headers(config):
    return {"X-Sync-Key": config["sync_api_key"]} if config.get("sync_api_key") else {}


def fetch_status(config):
    resp = creq.get(f"{config['api_base_url']}/api/sync-status", timeout=30)
    resp.raise_for_status()
    return resp.json()


def mark_done(config, summary):
    resp = creq.post(
        f"{config['api_base_url']}/api/sync-done",
        headers=api_headers(config),
        timeout=30,
    )
    if resp.status_code != 200:
        log(f"Nao consegui marcar o sync como concluido ({resp.status_code}): {resp.text[:200]}")


def is_due(status, interval):
    if status.get("pending"):
        return True
    last = parse_ts(status.get("last_sync_at"))
    if last is None:
        return True
    return datetime.now(timezone.utc) - last >= interval


def main():
    config = load_config()
    poll_seconds = config.get("poll_seconds", 120)
    interval = timedelta(hours=config.get("interval_hours", 4))

    log(f"Watcher iniciado. Checando {config['api_base_url']} a cada {poll_seconds}s; "
        f"sync automatico a cada {interval.total_seconds() / 3600:g}h.")

    while True:
        try:
            status = fetch_status(config)
            if is_due(status, interval):
                reason = "pedido pelo botao" if status.get("pending") else "agendamento"
                log(f"Iniciando sync ({reason}).")
                summary = run_sync(config, log=log)
                log(f"Sync concluido: {summary['sent']} de {summary['found']} anuncios enviados.")
                mark_done(config, summary)
        except KeyboardInterrupt:
            log("Encerrado.")
            return
        except Exception as exc:  # rede caiu, site dormindo, etc.: tenta de novo no proximo ciclo
            log(f"Erro na checagem: {exc}")

        try:
            time.sleep(poll_seconds)
        except KeyboardInterrupt:
            log("Encerrado.")
            return


if __name__ == "__main__":
    main()
