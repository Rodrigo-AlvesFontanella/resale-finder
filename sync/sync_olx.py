"""
Sync local da OLX -> site hospedado.

Roda no seu computador (usa seu IP de casa, que a Cloudflare da OLX nao
bloqueia — diferente do IP do servidor na nuvem). Busca uma lista de termos
com boa liquidez de revenda, filtra pra Grande Porto Alegre, e manda os
anuncios pro site hospedado via /api/ingest.

Uso manual:
    python sync/sync_olx.py

Para o botao "Sincronizar agora" do site e o agendamento automatico, use
sync/sync_watch.py (ele chama run_sync() daqui).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests as creq  # noqa: E402

from backend.scraper import ScrapeError, search_olx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(
            f"Crie {CONFIG_PATH} a partir de config.example.json antes de rodar."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def send_to_api(config, search_term, items):
    payload = {
        "search_term": search_term,
        "source": "olx",
        "items": [
            {
                "title": i["title"],
                "price": i["price"],
                "url": i["url"],
                "old_price": i.get("old_price"),
                "location": i.get("location"),
                "posted_at_text": i.get("posted_at_text"),
            }
            for i in items
        ],
    }
    headers = {}
    if config.get("sync_api_key"):
        headers["X-Sync-Key"] = config["sync_api_key"]

    return creq.post(
        f"{config['api_base_url']}/api/ingest",
        json=payload,
        headers=headers,
        timeout=30,
    )


def run_sync(config, log=print):
    terms = config["search_terms"]
    max_pages = config.get("max_pages_per_term", 3)
    only_poa = config.get("only_poa_metro", True)
    delay = config.get("delay_between_terms_seconds", 4)

    log(f"Sincronizando {len(terms)} termos para {config['api_base_url']}\n")

    found = 0
    sent = 0
    failed_terms = []

    for idx, term in enumerate(terms, start=1):
        log(f"[{idx}/{len(terms)}] {term} ...")
        try:
            items = search_olx(term, max_pages=max_pages, only_poa_metro=only_poa)
        except ScrapeError as exc:
            log(f"  FALHOU na OLX: {exc}")
            failed_terms.append(term)
            time.sleep(delay)
            continue

        if not items:
            log("  0 anuncios na regiao.")
            time.sleep(delay)
            continue

        found += len(items)
        try:
            resp = send_to_api(config, term, items)
            if resp.status_code == 200:
                log(f"  {len(items)} anuncios enviados.")
                sent += len(items)
            else:
                log(f"  API retornou {resp.status_code}: {resp.text[:200]}")
                failed_terms.append(term)
        except Exception as exc:  # curl_cffi levanta varios tipos de erro de conexao
            log(f"  erro ao enviar pro site: {exc}")
            failed_terms.append(term)

        time.sleep(delay)

    return {"found": found, "sent": sent, "failed_terms": failed_terms}


def main():
    config = load_config()
    summary = run_sync(config)

    print("\n== Resumo ==")
    print(f"Anuncios encontrados na OLX: {summary['found']}")
    print(f"Anuncios enviados com sucesso: {summary['sent']}")
    if summary["failed_terms"]:
        print(f"Termos com falha: {', '.join(summary['failed_terms'])}")


if __name__ == "__main__":
    main()
