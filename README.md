# Resale Finder

App web que busca anúncios na OLX (filtrado pra Região Metropolitana de
Porto Alegre), calcula um **score de prioridade de revenda** por item, e
deixa adicionar manualmente itens do Facebook Marketplace (ou automatizar
isso com o script local em `facebook/`) pra entrarem na mesma comparação.

## Como rodar localmente

```
cd resale-finder
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000 --reload
```

Abra http://127.0.0.1:8000 no navegador.

## Como funciona o score de prioridade

1. Você busca um termo (ex: "iphone 11") — o app raspa a OLX no estado do RS
   e filtra só os 34 municípios da Região Metropolitana de Porto Alegre
   (a OLX só filtra por estado via URL, então esse recorte é feito no app).
2. Calcula a mediana de preço entre os anúncios daquele termo.
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
7. Itens manuais (Facebook, etc.) usam a mesma mediana do termo de busca
   informado, então entram na mesma régua de comparação.

O bloco "Estratégia de revenda" na página mostra o top 5 com a razão de
cada um (ex: *"preço 44% abaixo da mediana; categoria de giro rápido
(iphone); anunciado ontem"*) — comece negociando por esses.

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
`search_url_template`, trocando o termo de busca por `{query}`.

**Uso (sempre que quiser buscar):**

```
python scrape.py "iphone 11"
```

Ele abre o Marketplace já logado, busca o termo, e manda os anúncios
encontrados pro `api_base_url` configurado (local ou o site já hospedado)
via a mesma rota que o formulário manual usa — eles aparecem no site
misturados com os da OLX, com o mesmo score.

> **Isso não foi testado ao vivo** (não tenho como logar numa conta real do
> Facebook por aqui). O Facebook ofusca nomes de classe CSS e muda o layout
> com frequência — é bem provável que `extract_listings()` em `scrape.py`
> precise de ajustes depois que você rodar a primeira vez. Roda e me manda
> o que aconteceu (funcionou / não achou nada / erro) que a gente ajusta
> junto.

## Hospedar no Render (grátis)

O plano gratuito do Render **dorme após alguns minutos sem acesso** (demora
~30s pra acordar no próximo acesso) e **não tem disco persistente** — o
banco (`resale.db`) é recriado do zero a cada deploy/restart. Como os dados
são só o resultado de buscas (re-obteníveis), isso é aceitável pra começar.

1. Suba este repositório pro GitHub (veja seção abaixo).
2. Crie uma conta em https://render.com e conecte com o GitHub.
3. "New" → "Blueprint" → selecione o repositório → o Render lê o
   `render.yaml` daqui e configura tudo sozinho.
4. Aguarde o build (alguns minutos) — o site fica em algo como
   `https://resale-finder-XXXX.onrender.com`.

## Subir pro GitHub

```
cd resale-finder
git init
git add .
git commit -m "Resale finder: busca OLX POA + score de prioridade"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/resale-finder.git
git push -u origin main
```

(Crie o repositório vazio antes em https://github.com/new — sem README/gitignore,
pra não conflitar com o que já existe aqui.)

## Limitações conhecidas

- A OLX usa Cloudflare; usamos `curl_cffi` (imita TLS de navegador) pra não
  ser bloqueado — se parar de funcionar, o erro retornado indica isso
  (`backend/scraper.py`).
- O filtro de Grande Porto Alegre é feito comparando o texto de localização
  de cada anúncio com a lista de municípios da RMPA (`scoring.py`); cidades
  fora dessa lista nunca aparecem mesmo que estejam próximas.
- Os sinais de urgência/risco são por palavra-chave — não pega tudo, é uma
  ajuda, não uma garantia.
