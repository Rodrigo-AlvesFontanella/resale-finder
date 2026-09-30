import time

from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException
from bs4 import BeautifulSoup

from .scoring import location_in_poa_metro, parse_price

# A OLX fica atrás da Cloudflare, que bloqueia com base na "impressão digital"
# TLS da conexão (nao so nos headers). curl_cffi imita o TLS de um Chrome real
# (impersonate=), o que a lib `requests` padrao nao consegue fazer.
HEADERS = {
    "Accept-Language": "pt-BR,pt;q=0.9",
}
IMPERSONATE = "chrome124"

# A OLX so filtra de verdade por estado via URL (o segmento de
# cidade/regiao na URL e so cosmetico e nao muda o resultado). Por isso
# buscamos no estado inteiro e filtramos a regiao metropolitana no nosso
# lado (ver scoring.location_in_poa_metro).
BASE_URL = "https://www.olx.com.br/estado-rs"


class ScrapeError(Exception):
    pass


def search_olx(
    query: str,
    max_pages: int = 1,
    timeout: int = 15,
    only_poa_metro: bool = True,
) -> list[dict]:
    """Busca anúncios na OLX (RS) para um termo. Levanta ScrapeError se o
    site bloquear a requisição ou mudar de estrutura."""
    results = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        params = {"q": query}
        if page > 1:
            params["o"] = page

        try:
            resp = requests.get(
                BASE_URL,
                params=params,
                headers=HEADERS,
                impersonate=IMPERSONATE,
                timeout=timeout,
            )
        except RequestException as exc:
            raise ScrapeError(f"Falha de conexao com a OLX: {exc}") from exc

        if resp.status_code != 200:
            raise ScrapeError(
                f"OLX retornou status {resp.status_code} (pode ter bloqueado a requisicao)"
            )

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('a[data-testid="adcard-link"]')
        if not cards:
            if page == 1:
                raise ScrapeError(
                    "Nao encontrei anuncios na pagina. A OLX pode ter mudado o "
                    "layout ou bloqueado a busca automatizada."
                )
            break

        for a in cards:
            container = a.find_parent("section", class_="olx-adcard")
            if container is None:
                continue

            url = a.get("href")
            if not url or url in seen_urls:
                continue

            price_el = container.select_one(".olx-adcard__price")
            price = parse_price(price_el.get_text(strip=True) if price_el else None)
            if price is None:
                continue

            loc_el = container.select_one(".olx-adcard__location")
            location = loc_el.get_text(strip=True) if loc_el else None

            if only_poa_metro and not location_in_poa_metro(location):
                continue

            title = a.get("title") or a.get_text(strip=True)
            old_price_el = container.select_one(".olx-adcard__old-price")
            date_el = container.select_one(".olx-adcard__date")

            seen_urls.add(url)
            results.append(
                {
                    "title": title,
                    "url": url,
                    "price": price,
                    "old_price": parse_price(
                        old_price_el.get_text(strip=True) if old_price_el else None
                    ),
                    "location": location,
                    "posted_at_text": date_el.get_text(strip=True) if date_el else None,
                }
            )

        if page < max_pages:
            time.sleep(0.6)

    return results
