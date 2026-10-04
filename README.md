# Resale Finder

Site que mostra anúncios da OLX e do Facebook Marketplace na Grande Porto
Alegre, ordenados por um **score de prioridade de revenda** — o que comprar
primeiro pra ter mais chance de vender rápido e com lucro.

## Como está organizado

A OLX (Cloudflare) bloqueia requisições vindas de IPs de servidor/nuvem, só
funciona a partir de um IP residencial normal. Por isso o app é dividido em
duas partes:

- **Site hospedado** (`backend/` + `frontend/`): mostra os anúncios já
  salvos, ordenados por prioridade, com link direto pra cada um. É só pra
  conferir e clicar — rodando na nuvem, o botão "Buscar" não funciona
  sozinho (dá erro 403 da OLX).
- **`sync/sync_olx.py`**: roda no **seu computador** (usa seu IP de casa,
  que funciona), busca uma lista de termos com boa liquidez de revenda,
  filtra pra Grande Porto Alegre, e envia os anúncios pro site hospedado.
  Agende pra rodar sozinho de tempos em tempos (veja abaixo).
- **`facebook/`**: mesma ideia, mas pro Facebook Marketplace, com login de
  verdade (veja a seção própria — tem risco de conta que vale ler antes).

## Como rodar o site localmente (dev)

```
cd resale-finder
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000 --reload
```

Abra http://127.0.0.1:8000 no navegador. Localmente o botão "Buscar" funciona
direto (seu IP de casa não é bloqueado).

## Como funciona o score de prioridade

1. Cada termo buscado (ex: "iphone 11") vira um grupo de anúncios filtrados
   pra Região Metropolitana de Porto Alegre (34 municípios, comparados no
   próprio app — a OLX só filtra por estado via URL).
2. Calcula a mediana de preço entre os anúncios daquele grupo.
3. **Score de preço**: quanto mais abaixo da mediana, maior o score (0–100).
4. **Bônus de urgência**: palavras como "urgente", "aceito proposta",
   "mudança" somam pontos — indicam vendedor disposto a negociar rápido.
5. **Penalidade de risco**: palavras como "defeito", "quebrado", "não liga",
   "para peça", "bloqueado"/"iCloud" tiram pontos.
6. **Score de prioridade** (o que ordena a lista) combina o score de preço
   com um bônus de **categoria de giro rápido** (iPhone, consoles, notebook,
   ferramentas elétricas etc. vendem mais rápido que móveis/eletrodomésticos
   grandes) e um bônus de **anúncio recente** (publicado hoje/ontem = menos
   concorrência pra você chegar primeiro na negociação).
7. Itens manuais ou do sync (Facebook, etc.) usam a mesma mediana do termo
   de busca informado, então entram na mesma régua de comparação.

O bloco "Estratégia de revenda" no topo da página mostra o top 5 com a razão
de cada um (ex: *"preço 44% abaixo da mediana; categoria de giro rápido
(iphone); anunciado ontem"*) — comece chamando esses.

## Hospedar no Render (grátis)

O plano gratuito do Render **dorme após alguns minutos sem acesso** (demora
~30s pra acordar no próximo acesso) e **não tem disco persistente** — o
banco (`resale.db`) é recriado do zero a cada deploy/restart. Como os dados
vêm do sync (re-obteníveis a qualquer momento), isso é aceitável.

1. Suba este repositório pro GitHub (veja seção abaixo).
2. Crie uma conta em https://render.com e conecte com o GitHub.
3. "New" → "Blueprint" → selecione o repositório → o Render lê o
   `render.yaml` e configura tudo sozinho (já fixado em Python 3.12, o
   3.14 default do Render quebra o build do `pydantic-core`).
4. **Defina a variável de ambiente `SYNC_API_KEY`** no serviço criado
   (Render → seu serviço → Environment → Add Environment Variable) com uma
   senha longa qualquer — ela protege o `/api/ingest` pra só o seu script
   de sync poder gravar dados no site. Sem isso, qualquer pessoa na internet
   poderia mandar lixo pro seu banco.
5. Aguarde o build — o site fica em algo como
   `https://resale-finder-XXXX.onrender.com`.

## Sincronizar a OLX (rodando no seu PC)

**Setup (uma vez):**

```
cd resale-finder
cp sync/config.example.json sync/config.json
```

Edite `sync/config.json`:
- `api_base_url`: a URL do seu site no Render
- `sync_api_key`: a mesma senha que você colocou em `SYNC_API_KEY` no Render
- `search_terms`: ajuste a lista de categorias como quiser

**Rodar manualmente:**

```
python sync/sync_olx.py
```

**Modo automático (recomendado):** deixe o watcher rodando no seu PC:

```
python sync/sync_watch.py
```

Ele checa o site a cada 2 minutos e sincroniza quando:
- alguém aperta **"Sincronizar agora"** no site, ou
- o último sync passou de 4 horas (configurável em `interval_hours`).

O botão tem limite de uma sincronização a cada 30 minutos, pra não expor
seu IP a bloqueio da OLX. O watcher precisa estar rodando no PC pra
qualquer sync acontecer.

Pra ele iniciar sozinho quando o Windows ligar, crie uma tarefa:

```
schtasks /create /tn "ResaleFinderWatch" /tr "pythonw C:\caminho\completo\resale-finder\sync\sync_watch.py" /sc onlogon
```

(Ajuste o caminho. Pra remover: `schtasks /delete /tn "ResaleFinderWatch" /f`.)

Obs.: o watcher faz uma requisição a cada 2 minutos, o que mantém o site do
Render acordado — o banco não é apagado por inatividade enquanto ele roda.
Confira as horas do plano gratuito (750 h/mês) porque 24h por dia consome
quase todo o mês.

## Facebook Marketplace (automação local — leia o risco antes)

O Facebook não tem API pública e detecta automação agressivamente.
**Automatizar com sua conta pessoal pode resultar em bloqueio/verificação
ou banimento da conta.** Por isso esse pedaço:

- Roda **só no seu computador**, nunca no servidor hospedado (usar seu login
  a partir de uma nuvem por trás de um IP de datacenter é ainda mais
  arriscado e mais fácil de ser detectado).
- Usa uma janela de navegador de verdade (não headless) com o seu login.
- Deve ser rodado com moderação (algumas vezes por dia, não em loop).

**Setup (uma vez só):**

```
cd resale-finder/facebook
python -m pip install -r requirements.txt
playwright install chromium
python login.py
```

Siga as instruções no terminal: você loga manualmente na janela que abre,
define a localização "Porto Alegre" no filtro do Marketplace, faz uma busca
de teste, e copia a URL resultante da barra de endereços.

Depois copie `config.example.json` para `config.json` e cole essa URL em
`search_url_template`, trocando o termo de busca por `{query}`. Coloque
também a URL do site hospedado em `api_base_url`.

**Uso (sempre que quiser buscar):**

```
python scrape.py "iphone 11"
```

Ele abre o Marketplace já logado, busca o termo, e manda os anúncios
encontrados pro site hospedado via a mesma rota que o formulário manual
usa — eles aparecem misturados com os da OLX, com o mesmo score.

> **Isso não foi testado ao vivo** (não tenho como logar numa conta real do
> Facebook por aqui). O Facebook ofusca nomes de classe CSS e muda o layout
> com frequência — é bem provável que `extract_listings()` em `scrape.py`
> precise de ajustes depois que você rodar a primeira vez. Roda e me manda
> o que aconteceu (funcionou / não achou nada / erro) que a gente ajusta
> junto.

## Subir pro GitHub

```
cd resale-finder
git add .
git commit -m "sua mensagem"
git push
```

(Já está tudo configurado — o repositório é
https://github.com/Rodrigo-AlvesFontanella/resale-finder.)

## Limitações conhecidas

- A OLX usa Cloudflare; usamos `curl_cffi` (imita TLS de navegador) pra não
  ser bloqueado por fingerprint — mas IPs de datacenter (Render, AWS etc.)
  ainda tomam 403 por reputação de IP, por isso o sync roda local.
- O filtro de Grande Porto Alegre é feito comparando o texto de localização
  de cada anúncio com a lista de municípios da RMPA (`scoring.py`); cidades
  fora dessa lista nunca aparecem mesmo que estejam próximas.
- Os sinais de urgência/risco/categoria são por palavra-chave — não pega
  tudo, é uma ajuda, não uma garantia.
- `/api/ingest` sem `SYNC_API_KEY` configurada fica aberto pra qualquer um
  gravar dados — defina a variável de ambiente antes de divulgar a URL do
  site.
