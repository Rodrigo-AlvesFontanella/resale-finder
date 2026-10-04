import re

PRICE_RE = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:,\d{2})?)")
VALIDADE_RE = re.compile(
    r"(?:validade|val\.?|vence(?:\s+em)?|venc\.?)\s*[:\-]?\s*(\d{1,2})\s*[/\-]\s*(\d{4}|\d{2})\b",
    re.IGNORECASE,
)


def parse_brl(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def parse_promo(text: str) -> dict:
    """Tenta extrair preco, preco antigo, validade e nome de um texto colado
    (mensagem de WhatsApp ou pagina de promocao). O resultado e sugestao: o
    usuario confere antes de salvar."""
    text = text or ""
    warnings = []

    prices = [parse_brl(m.group(1)) for m in PRICE_RE.finditer(text)]
    price = old_price = None
    if prices:
        price = min(prices)
        higher = max(prices)
        old_price = higher if higher > price else None
    else:
        warnings.append("Nao achei nenhum preco no texto (procure por R$).")

    expires_at = None
    m = VALIDADE_RE.search(text)
    if m:
        month = int(m.group(1))
        year = int(m.group(2))
        if year < 100:
            year += 2000
        if 1 <= month <= 12:
            expires_at = f"{month:02d}/{year}"
    if expires_at is None:
        warnings.append("Validade nao encontrada. Preencha se souber.")

    title = None
    for line in text.splitlines():
        clean = re.sub(r"^[\s\-\*•●✅❌\U0001F300-\U0001FAFF]+", "", line).strip()
        if len(clean) < 4 or PRICE_RE.search(clean) or VALIDADE_RE.search(clean):
            continue
        title = clean[:120]
        break
    if title is None:
        warnings.append("Nome do produto nao identificado.")

    return {
        "title": title,
        "price": price,
        "old_price": old_price,
        "expires_at": expires_at,
        "warnings": warnings,
    }
