"""
Scraper do Facebook Marketplace — roda SÓ no seu computador, usando a sessão
salva por login.py. Abre um navegador de verdade (nao headless) com o seu
login, busca um termo e manda os anuncios encontrados pro app (via a mesma
rota /api/manual que o formulario manual usa).

AVISO DE RISCO: automatizar o Facebook com sua conta pessoal pode disparar
deteccao de bot e resultar em bloqueio/verificacao/banimento da conta. Para
reduzir o risco:
  - Rode isso raramente (algumas vezes por dia, no maximo), nunca em loop.
  - Nao rode headless (deixe a janela visivel, como esta configurado).
  - Se puder, use uma conta secundaria do Facebook em vez da principal.
  - Se o Facebook pedir verificacao/captcha, resolva manualmente na janela
    e nao insista tentando rodar de novo na hora.

O Facebook muda o layout com frequencia e ofusca nomes de classe CSS, entao
esse script busca os anuncios pelo padrao de link '/marketplace/item/...'
(mais estavel que classes CSS) e tenta extrair preco/titulo do texto ao
redor. Se parar de funcionar, me avise que ajustamos junto.

Uso:
    python scrape.py [termo de busca opcional, sobrescreve o config.json]
"""

import json
import os
import re
import sys
import time
import urllib.parse

import requests
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, "fb_state.json")
CONFIG_PATH = os.path.join(HERE, "config.json")

PRICE_RE = re.compile(r"R\$\s?[\d\.]{1,3}(?:\.\d{3})*(?:,\d{2})?")
ITEM_ID_RE = re.compile(r"/marketplace/item/(\d+)")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(
            f"Crie {CONFIG_PATH} a partir de config.example.json antes de rodar."
        )
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def parse_price(text):
    m = PRICE_RE.search(text)
    if not m:
        return None
    cleaned = re.sub(r"[^\d,.]", "", m.group())
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_listings(page):
    links = page.query_selector_all('a[href*="/marketplace/item/"]')
    seen = {}
    for link in links:
        href = link.get_attribute("href") or ""
        m = ITEM_ID_RE.search(href)
        if not m:
            continue
        item_id = m.group(1)
        if item_id in seen:
            continue

        # Sobe alguns niveis pra pegar o card inteiro (preco + titulo ficam
        # em elementos irmaos do link, nao dentro dele).
        block_text = link.evaluate(
            "el => { let n = el; for (let i = 0; i < 4 && n.parentElement; i++) n = n.parentElement; return n.innerText; }"
        ) or ""
        lines = [l.strip() for l in block_text.split("\n") if l.strip()]

        price = parse_price(block_text)
        title = None
        for l in lines:
            if PRICE_RE.search(l):
                continue
            if len(l) < 3:
                continue
            title = l
            break

        if not title or price is None:
            continue

        seen[item_id] = {
            "title": title,
            "price": price,
            "url": f"https://www.facebook.com/marketplace/item/{item_id}/",
        }

    return list(seen.values())


def send_to_api(api_base_url, search_term, items):
    ok, failed = 0, 0
    for item in items:
        payload = {
            "title": item["title"],
            "price": item["price"],
            "search_term": search_term,
            "url": item["url"],
            "source": "facebook",
        }
        try:
            resp = requests.post(f"{api_base_url}/api/manual", json=payload, timeout=15)
            if resp.status_code == 200:
                ok += 1
            else:
                failed += 1
                print("  falhou:", resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            failed += 1
            print("  erro de conexao:", exc)
    return ok, failed


def main():
    config = load_config()
    search_term = sys.argv[1] if len(sys.argv) > 1 else config["search_term"]

    if not os.path.exists(STATE_PATH):
        raise SystemExit("Nao encontrei fb_state.json — rode login.py primeiro.")

    url = config["search_url_template"].format(query=urllib.parse.quote(search_term))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=STATE_PATH, locale="pt-BR")
        page = context.new_page()
        page.goto(url)
        page.wait_for_timeout(3000)

        for _ in range(config.get("max_scrolls", 6)):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1200)

        items = extract_listings(page)
        print(f"Encontrei {len(items)} anuncios para '{search_term}'.")

        browser.close()

    if items:
        ok, failed = send_to_api(config["api_base_url"], search_term, items)
        print(f"Enviados: {ok} ok, {failed} falharam.")
    else:
        print(
            "Nenhum anuncio extraido. O layout do Facebook pode ter mudado — "
            "avise para ajustarmos o extract_listings()."
        )


if __name__ == "__main__":
    main()
