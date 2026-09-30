"""
Login unico e manual no Facebook, rodado APENAS no seu computador.

Abre uma janela de navegador de verdade (nao headless) para voce fazer
login manualmente (usuario/senha, 2FA, o que for). Depois de logar, aperte
Enter aqui no terminal — o script salva a sessao (cookies/local storage) em
`fb_state.json`, pra os proximos scrapes nao precisarem logar de novo.

Esse arquivo fb_state.json equivale a estar logado na sua conta. Nunca suba
ele pro GitHub nem mande pra ninguem (ja esta no .gitignore).

Uso:
    python login.py
"""

import json
import os

from playwright.sync_api import sync_playwright

STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb_state.json")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="pt-BR")
        page = context.new_page()
        page.goto("https://www.facebook.com/marketplace/")

        print("\n== Login manual ==")
        print("1. Faca login normalmente na janela que abriu.")
        print("2. Va ate o Marketplace, clique no filtro de localizacao e")
        print("   defina 'Porto Alegre, RS' com o raio que quiser.")
        print("3. Faca uma busca de teste (ex: iphone) so pra a URL do")
        print("   Marketplace ficar com a localizacao aplicada.")
        print("4. Copie a URL da barra de enderecos e cole no config.json")
        print("   (campo 'search_url_template'), trocando o termo buscado")
        print("   por {query} -- veja config.example.json.")
        input("\nQuando terminar os passos acima, volte aqui e aperte Enter... ")

        state = context.storage_state()
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f)

        print(f"Sessao salva em {STATE_PATH}")
        if not os.path.exists(CONFIG_PATH):
            print(
                f"Nao esqueca de criar {CONFIG_PATH} a partir de "
                "config.example.json antes de rodar o scrape.py."
            )

        browser.close()


if __name__ == "__main__":
    main()
