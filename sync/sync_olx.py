"""
Sync local da OLX -> site hospedado.

Roda no seu computador (usa seu IP de casa, que a Cloudflare da OLX nao
bloqueia — diferente do IP do servidor na nuvem). Busca uma lista de termos
com boa liquidez de revenda, filtra pra Grande Porto Alegre, e manda os
anuncios pro site hospedado via /api/ingest. O site so guarda e pontua o
que chegar por aqui (ou pelo formulario manual) — o botao "Buscar" na
versao hospedada nao funciona sozinho por causa do bloqueio de IP.

Setup (uma vez):
    cd resale-finder
    python -m pip install -r requirements.txt
    cp sync/config.example.json sync/config.json
    # edite sync/config.json com a URL do Render e a mesma SYNC_API_KEY
    # que voce configurou nas env vars do servico no Render

Uso manual:
    python sync/sync_olx.py

Agendar no Windows (roda a cada 4 horas, por exemplo):
    schtasks /create /tn "ResaleFinderSync" /tr "python C:\\caminho\\completo\\resale-finder\\sync\\sync_olx.py" /sc hourly /mo 4

A lista de termos em config.json e a estrategia de "o que priorizar": sao
categorias com giro rapido de revenda (celulares top, consoles, notebook,
ferramentas eletricas, bike, tenis de marca). O score de prioridade de cada
anuncio (preco vs mediana + categoria + recencia) e calculado no servidor
ao receber os itens — veja backend/scoring.py.
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

    resp = creq.post(
        f"{config['api_base_url']}/api/ingest",
        json=payload,
        headers=headers,
        timeout=30,
    )
    return resp


def main():
    config = load_config()
    terms = config["search_terms"]
    max_pages = config.get("max_pages_per_term", 3)
    only_poa = config.get("only_poa_metro", True)
    delay = config.get("delay_between_terms_seconds", 4)

    print(f"Sincronizando {len(terms)} termos para {config['api_base_url']}\n")

    total_found = 0
    total_sent = 0
    total_failed_terms = []

    for idx, term in enumerate(terms, start=1):
        print(f"[{idx}/{len(terms)}] {term} ...", end=" ", flush=True)
        try:
            items = search_olx(term, max_pages=max_pages, only_poa_metro=only_poa)
        except ScrapeError as exc:
            print(f"FALHOU na OLX: {exc}")
            total_failed_terms.append(term)
            time.sleep(delay)
            continue

        if not items:
            print("0 anuncios na regiao.")
            time.sleep(delay)
            continue

        total_found += len(items)
        try:
            resp = send_to_api(config, term, items)
            if resp.status_code == 200:
                print(f"{len(items)} anuncios enviados.")
                total_sent += len(items)
            else:
                print(f"API retornou {resp.status_code}: {resp.text[:200]}")
                total_failed_terms.append(term)
        except Exception as exc:  # curl_cffi levanta varios tipos de erro de conexao
            print(f"erro ao enviar pro site: {exc}")
            total_failed_terms.append(term)

        time.sleep(delay)

    print("\n== Resumo ==")
    print(f"Anuncios encontrados na OLX: {total_found}")
    print(f"Anuncios enviados com sucesso: {total_sent}")
    if total_failed_terms:
        print(f"Termos com falha: {', '.join(total_failed_terms)}")


if __name__ == "__main__":
    main()
