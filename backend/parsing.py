import re
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

PRICE_RE = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2}|\d+(?:,\d{2})?)")
VALIDADE_RE = re.compile(
    r"(?:validade|val\.?|vence(?:\s+em)?|venc\.?)\s*[:\-]?\s*(\d{1,2})\s*[/\-]\s*(\d{4}|\d{2})\b",
    re.IGNORECASE,
)
PROMO_END_RE = re.compile(
    r"(?:at[eé]|termina(?:\s+dia)?|v[aá]lido\s+at[eé]|acaba(?:\s+dia)?)\s*(?:dia\s+)?"
    r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?"
    r"(?:\s*(?:[aà]s|[aá]s|-)?\s*(\d{1,2})(?::(\d{2}))?\s*h\b)?",
    re.IGNORECASE,
)
ONLY_TODAY_RE = re.compile(r"s[oó]\s+hoje", re.IGNORECASE)
FLASH_RE = re.compile(r"rel[aâ]mp[aá]go", re.IGNORECASE)


def parse_brl(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _promo_end(text: str, now: datetime) -> str | None:
    if ONLY_TODAY_RE.search(text):
        return now.replace(hour=23, minute=59, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")

    m = PROMO_END_RE.search(text)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year_text = m.group(3)
    if year_text:
        year = int(year_text) + (2000 if len(year_text) == 2 else 0)
    else:
        year = now.year
    hour = int(m.group(4)) if m.group(4) else 23
    minute = int(m.group(5)) if m.group(5) else (0 if m.group(4) else 59)
    try:
        end = datetime(year, month, day, hour, minute, tzinfo=TZ)
    except ValueError:
        return None
    if not year_text and end < now:
        try:
            end = end.replace(year=year + 1)
        except ValueError:
            return None
    return end.strftime("%Y-%m-%dT%H:%M")


PROMO_WORDS = {"de", "por", "a", "o", "em", "apenas", "so", "hoje", "relampago", "ate", "validade"}


def _find_title(text: str) -> str | None:
    for line in text.splitlines():
        s = re.sub(r"^[\s\-\*•●⚡✅❌\U0001F300-\U0001FAFF]+", "", line)
        s = PRICE_RE.sub(" ", s)
        s = PROMO_END_RE.sub(" ", s)
        s = VALIDADE_RE.sub(" ", s)
        s = FLASH_RE.sub(" ", s)
        s = ONLY_TODAY_RE.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip(" -:|.!")
        words = re.findall(r"[a-zA-ZÀ-ÿ0-9]+", s.lower())
        if len(s) < 4 or not words or all(w in PROMO_WORDS for w in words):
            continue
        return s[:120]
    return None


def parse_promo(text: str) -> dict:
    """Tenta extrair preco, preco antigo, validade, nome e prazo da promocao de
    um texto colado ou lido de um print. O resultado e sugestao: o usuario
    pode corrigir depois."""
    text = text or ""
    now = datetime.now(TZ)
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
        warnings.append("Validade do produto nao encontrada.")

    promo_ends_at = _promo_end(text, now)
    flash = bool(FLASH_RE.search(text))
    if promo_ends_at is None and flash:
        warnings.append("Promocao relampago sem prazo: defina quanto tempo dura.")

    title = _find_title(text)
    if title is None:
        warnings.append("Nome do produto nao identificado.")

    return {
        "title": title,
        "price": price,
        "old_price": old_price,
        "expires_at": expires_at,
        "promo_ends_at": promo_ends_at,
        "flash": flash,
        "warnings": warnings,
    }
