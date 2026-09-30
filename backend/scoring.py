import re
import statistics

# Palavras que sugerem que o vendedor topa negociar / quer vender rápido.
URGENCY_KEYWORDS = [
    "urgente", "urgencia", "preciso vender", "preciso do dinheiro",
    "pechincha", "baixei o preco", "ultima semana", "aceito proposta",
    "aceito ofertas", "mudanca", "vendo logo", "saindo do pais",
    "vendo hoje", "negociavel", "negocio",
]

# Palavras que sugerem risco/defeito — reduzem o score mesmo com preço baixo.
RISK_KEYWORDS = [
    "defeito", "nao liga", "para retirar pecas", "sem garantia",
    "quebrado", "quebrada", "trincado", "trincada", "tela quebrada",
    "no estado", "so pecas", "para peca", "avariado", "avariada",
    "molhado", "molhada", "sinistro", "bloqueado", "bloqueada", "icloud",
]

# Municípios da Região Metropolitana de Porto Alegre (RMPA), usados para
# filtrar os anúncios da OLX (que só filtra por estado, não por região).
POA_METRO_CITIES = [
    "porto alegre", "alvorada", "ararica", "arroio dos ratos", "cachoeirinha",
    "campo bom", "canoas", "capela de santana", "charqueadas", "dois irmaos",
    "eldorado do sul", "estancia velha", "esteio", "glorinha", "gravatai",
    "guaiba", "igrejinha", "ivoti", "montenegro", "nova hartz",
    "nova santa rita", "novo hamburgo", "parobe", "portao", "rolante",
    "santo antonio da patrulha", "sao jeronimo", "sao leopoldo", "sapiranga",
    "sapucaia do sul", "taquara", "triunfo", "vale real", "viamao",
]

# Categorias com boa "liquidez" de revenda (giro rápido) no mercado de usados,
# usadas para priorizar o que vale mais a pena buscar/comprar para revender.
LIQUIDITY_TIERS = [
    (25, [
        "iphone", "galaxy s", "galaxy a", "galaxy z", "xiaomi", "redmi",
        "playstation", "ps4", "ps5", "xbox", "nintendo switch",
        "notebook", "macbook", "airpods", "apple watch", "ipad",
    ]),
    (15, [
        "furadeira", "parafusadeira", "esmerilhadeira", "serra circular",
        "smart tv", "televisao", " tv ", "ar condicionado", "bicicleta",
        "bike", "tenis", "camera", "gopro", "drone", "caixa de som",
        "monitor", "console",
    ]),
    (5, [
        "sofa", "guarda-roupa", "geladeira", "fogao", "maquina de lavar",
        "instrumento musical", "violao", "guitarra",
    ]),
]


def location_in_poa_metro(location: str | None) -> bool:
    norm = normalize_text(location)
    if not norm:
        return False
    return any(norm.startswith(city) for city in POA_METRO_CITIES)


def liquidity_bonus(text: str) -> tuple[float, str | None]:
    norm = normalize_text(text)
    for bonus, keywords in LIQUIDITY_TIERS:
        for kw in keywords:
            if kw in norm:
                return float(bonus), kw.strip()
    return 0.0, None


def recency_bonus(posted_at_text: str | None) -> float:
    norm = normalize_text(posted_at_text)
    if norm.startswith("hoje"):
        return 15.0
    if norm.startswith("ontem"):
        return 8.0
    return 0.0


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower()
    text = (
        text.replace("á", "a").replace("à", "a").replace("â", "a").replace("ã", "a")
        .replace("é", "e").replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o").replace("ô", "o").replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    return text


def parse_price(text: str | None):
    if not text:
        return None
    cleaned = re.sub(r"[^\d,.]", "", text)
    if not cleaned:
        return None
    # Formato brasileiro: milhar com ponto, decimal com vírgula.
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        value = float(cleaned)
        return value if value > 0 else None
    except ValueError:
        return None


def find_keywords(text: str, keywords: list[str]) -> list[str]:
    norm = normalize_text(text)
    return [k for k in keywords if k in norm]


def price_score_from_ratio(ratio: float | None):
    if ratio is None:
        return None
    score = (1 - ratio) * 200
    return max(0.0, min(100.0, score))


def compute_group_median(prices: list[float]) -> float | None:
    valid = [p for p in prices if p and p > 0]
    if len(valid) < 3:
        return None
    return statistics.median(valid)


def score_listing(price, group_median, title, description, posted_at_text=None):
    text = f"{title or ''} {description or ''}"
    urgency_hits = find_keywords(text, URGENCY_KEYWORDS)
    risk_hits = find_keywords(text, RISK_KEYWORDS)

    ratio = (price / group_median) if (price and group_median) else None
    p_score = price_score_from_ratio(ratio)

    base = p_score if p_score is not None else 50.0
    bonus = min(20.0, 10.0 * len(urgency_hits))
    penalty = min(45.0, 25.0 * len(risk_hits))
    final = max(0.0, min(100.0, base + bonus - penalty))

    if final >= 75:
        label = "Excelente oportunidade"
    elif final >= 55:
        label = "Boa oportunidade"
    elif final >= 35:
        label = "Vale avaliar"
    else:
        label = "Preco na media ou acima"

    if p_score is None:
        label += " (sem base de comparacao ainda)"

    flags = []
    if urgency_hits:
        flags.append("indicio de urgencia do vendedor")
    if risk_hits:
        flags.append("possivel defeito ou risco")

    # Score de prioridade: pondera qualidade do preco + categoria de giro
    # rapido + anuncio recente (menos concorrencia pra negociar primeiro).
    liq_bonus, liq_category = liquidity_bonus(text)
    rec_bonus = recency_bonus(posted_at_text)
    priority = max(0.0, min(100.0, final * 0.6 + liq_bonus + rec_bonus))

    priority_reasons = []
    if ratio is not None and ratio <= 0.85:
        priority_reasons.append(f"preco {round((1 - ratio) * 100)}% abaixo da mediana do grupo")
    if liq_category:
        priority_reasons.append(f"categoria de giro rapido ({liq_category})")
    if rec_bonus >= 15:
        priority_reasons.append("anunciado hoje (pouca concorrencia ainda)")
    elif rec_bonus >= 8:
        priority_reasons.append("anunciado ontem")
    if urgency_hits:
        priority_reasons.append("vendedor sinaliza urgencia/negociacao")
    if risk_hits:
        priority_reasons.append("atencao: possivel defeito ou risco")

    return {
        "price_score": round(p_score, 1) if p_score is not None else None,
        "final_score": round(final, 1),
        "label": label,
        "flags": ", ".join(flags),
        "ratio": round(ratio, 3) if ratio is not None else None,
        "priority_score": round(priority, 1),
        "priority_reasons": "; ".join(priority_reasons),
    }
