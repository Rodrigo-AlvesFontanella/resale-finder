import os
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .parsing import parse_promo
from .scoring import compute_group_median, score_listing
from .scraper import ScrapeError, search_olx

SECTIONS = ("revenda", "farmacia")

# Chave opcional pra proteger o /api/ingest, /api/sync-done (sync local).
SYNC_API_KEY = os.environ.get("SYNC_API_KEY")

# Na versao hospedada a OLX bloqueia o IP do servidor: a busca direta fica
# desligada la (ALLOW_LIVE_SEARCH=false no render.yaml).
LIVE_SEARCH = os.environ.get("ALLOW_LIVE_SEARCH", "true").lower() == "true"

SYNC_COOLDOWN = timedelta(minutes=30)
EXPIRY_WARNING_MONTHS = 6

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


def ensure_schema():
    Base.metadata.create_all(bind=engine)
    existing = {c["name"] for c in inspect(engine).get_columns("listings")}
    additions = {
        "section": "VARCHAR DEFAULT 'revenda'",
        "expires_at": "VARCHAR",
        "hidden": "BOOLEAN DEFAULT FALSE",
        "prev_price": "FLOAT",
        "min_price": "FLOAT",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE listings ADD COLUMN {name} {ddl}"))


ensure_schema()

app = FastAPI(title="Resale Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str
    max_pages: int = 2
    only_poa_metro: bool = True


class ManualItem(BaseModel):
    title: str
    price: float
    search_term: str
    section: str = "revenda"
    old_price: float | None = None
    expires_at: str | None = None
    url: str | None = None
    description: str | None = None
    location: str | None = None
    source: str = "facebook"


class IngestItem(BaseModel):
    title: str
    price: float
    url: str
    old_price: float | None = None
    location: str | None = None
    posted_at_text: str | None = None
    description: str | None = None


class IngestRequest(BaseModel):
    search_term: str
    items: list[IngestItem]
    source: str = "olx"
    section: str = "revenda"


class ListingPatch(BaseModel):
    hidden: bool | None = None


class ParseRequest(BaseModel):
    text: str


def validate_section(section: str) -> str:
    if section not in SECTIONS:
        raise HTTPException(400, f"Secao invalida. Use uma de: {', '.join(SECTIONS)}")
    return section


def normalize_expiry(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    m = re.match(r"^\s*(\d{1,2})\s*[/\-]\s*(\d{4})\s*$", value)
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise HTTPException(400, "Validade deve estar no formato MM/AAAA")
    return f"{int(m.group(1)):02d}/{m.group(2)}"


def expiry_status(expires_at: str | None):
    if not expires_at:
        return None
    month, year = (int(p) for p in expires_at.split("/"))
    today = date.today()
    months = (year - today.year) * 12 + (month - today.month)
    if months < 0:
        return {"level": "vencido", "text": f"vencido em {expires_at}"}
    if months <= EXPIRY_WARNING_MONTHS:
        return {"level": "atencao", "text": f"vence em {months} mes(es) ({expires_at})"}
    return {"level": "ok", "text": f"vence em {expires_at}"}


def record_price(db: Session, listing: models.Listing, price: float):
    if listing.price is not None and abs(listing.price - price) > 0.01:
        listing.prev_price = listing.price
    listing.price = price
    listing.min_price = price if listing.min_price is None else min(listing.min_price, price)

    last = (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.listing_id == listing.id)
        .order_by(models.PriceHistory.id.desc())
        .first()
    )
    if last is None or abs(last.price - price) > 0.01:
        db.add(models.PriceHistory(listing_id=listing.id, price=price))


def rescore_group(db: Session, search_term: str, section: str):
    """Recalcula o score dos anuncios de um termo dentro de uma secao, usando a
    mediana de preco do grupo como referencia."""
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.search_term == search_term, models.Listing.section == section)
        .all()
    )
    median = compute_group_median([l.price for l in listings])

    for listing in listings:
        result = score_listing(
            listing.price, median, listing.title, listing.description, listing.posted_at_text
        )
        listing.price_score = result["price_score"]
        listing.final_score = result["final_score"]
        listing.label = result["label"]
        listing.flags = result["flags"]
        listing.priority_score = result["priority_score"]
        listing.priority_reasons = result["priority_reasons"]
        expiry = expiry_status(listing.expires_at)
        if expiry and expiry["level"] == "vencido":
            listing.priority_score = 0.0
            listing.priority_reasons = "vencido: nao vale comprar"

    db.commit()
    return median


def ingest_items(db: Session, search_term: str, section: str, source: str, items: list[dict]):
    for item in items:
        listing = db.query(models.Listing).filter(models.Listing.url == item["url"]).first()
        if listing is None:
            listing = models.Listing(
                section=section,
                source=source,
                search_term=search_term,
                title=item["title"],
                url=item["url"],
                old_price=item.get("old_price"),
                location=item.get("location"),
                posted_at_text=item.get("posted_at_text"),
                description=item.get("description"),
                expires_at=item.get("expires_at"),
                hidden=False,
            )
            db.add(listing)
            db.flush()
        else:
            listing.old_price = item.get("old_price")
            listing.location = item.get("location")
            listing.posted_at_text = item.get("posted_at_text")
        record_price(db, listing, item["price"])
    db.commit()

    rescore_group(db, search_term, section)

    return (
        db.query(models.Listing)
        .filter(models.Listing.search_term == search_term, models.Listing.section == section)
        .order_by(models.Listing.priority_score.desc())
        .all()
    )


def check_sync_key(x_sync_key: str | None):
    if SYNC_API_KEY and x_sync_key != SYNC_API_KEY:
        raise HTTPException(401, "Chave de sincronizacao invalida")


def get_sync_state(db: Session, key: str) -> datetime | None:
    row = db.query(models.SyncState).filter(models.SyncState.key == key).first()
    return datetime.fromisoformat(row.value) if row and row.value else None


def set_sync_state(db: Session, key: str, value: str):
    row = db.query(models.SyncState).filter(models.SyncState.key == key).first()
    if row:
        row.value = value
    else:
        db.add(models.SyncState(key=key, value=value))
    db.commit()


def sync_status(db: Session) -> dict:
    requested = get_sync_state(db, "requested_at")
    last = get_sync_state(db, "last_sync_at")
    pending = requested is not None and (last is None or requested > last)
    return {
        "pending": pending,
        "requested_at": requested.isoformat() if requested else None,
        "last_sync_at": last.isoformat() if last else None,
    }


def to_dict(listing: models.Listing) -> dict:
    return {
        "id": listing.id,
        "section": listing.section,
        "source": listing.source,
        "search_term": listing.search_term,
        "title": listing.title,
        "price": listing.price,
        "old_price": listing.old_price,
        "min_price": listing.min_price,
        "prev_price": listing.prev_price,
        "dropped": listing.prev_price is not None and listing.price is not None and listing.price < listing.prev_price - 0.01,
        "location": listing.location,
        "url": listing.url,
        "posted_at_text": listing.posted_at_text,
        "expires_at": listing.expires_at,
        "expiry": expiry_status(listing.expires_at),
        "hidden": bool(listing.hidden),
        "description": listing.description,
        "price_score": listing.price_score,
        "final_score": listing.final_score,
        "label": listing.label,
        "flags": listing.flags,
        "priority_score": listing.priority_score,
        "priority_reasons": listing.priority_reasons,
    }


@app.get("/api/config")
def api_config():
    return {"live_search": LIVE_SEARCH}


@app.get("/api/sync-status")
def api_sync_status(db: Session = Depends(get_db)):
    return sync_status(db)


@app.post("/api/sync-request")
def api_sync_request(db: Session = Depends(get_db)):
    """Pede pro watcher local rodar um sync. Uma sincronizacao a cada 30 min,
    pra nao expor o IP do seu PC a bloqueio da OLX."""
    status = sync_status(db)
    if status["pending"]:
        return status

    last = get_sync_state(db, "last_sync_at")
    if last:
        wait = SYNC_COOLDOWN - (datetime.now(timezone.utc) - last)
        if wait > timedelta(0):
            minutes = int(wait.total_seconds() // 60) + 1
            raise HTTPException(429, f"Ultima sincronizacao ha pouco. Tente de novo em ~{minutes} min.")

    set_sync_state(db, "requested_at", datetime.now(timezone.utc).isoformat())
    return sync_status(db)


@app.post("/api/sync-done")
def api_sync_done(db: Session = Depends(get_db), x_sync_key: str | None = Header(default=None)):
    check_sync_key(x_sync_key)
    set_sync_state(db, "last_sync_at", datetime.now(timezone.utc).isoformat())
    return sync_status(db)


@app.post("/api/search")
def api_search(payload: SearchRequest, db: Session = Depends(get_db)):
    if not LIVE_SEARCH:
        raise HTTPException(403, "Busca direta desativada nesta versao. Os dados vem do sync local.")

    query = payload.query.strip()
    if not query:
        raise HTTPException(400, "Informe um termo de busca")

    try:
        items = search_olx(
            query,
            max_pages=max(1, min(payload.max_pages, 8)),
            only_poa_metro=payload.only_poa_metro,
        )
    except ScrapeError as exc:
        raise HTTPException(502, str(exc)) from exc

    if not items:
        raise HTTPException(
            404,
            "Nenhum anuncio encontrado na Grande Porto Alegre para esse termo "
            "nas paginas buscadas. Tente aumentar o numero de paginas.",
        )

    listings = ingest_items(db, query, "revenda", "olx", items)
    return {"count": len(listings), "items": [to_dict(l) for l in listings]}


@app.post("/api/ingest")
def api_ingest(
    payload: IngestRequest,
    db: Session = Depends(get_db),
    x_sync_key: str | None = Header(default=None),
):
    """Recebe anuncios ja coletados pelo sync local (IP residencial)."""
    check_sync_key(x_sync_key)

    search_term = payload.search_term.strip()
    if not search_term:
        raise HTTPException(400, "Informe search_term")
    if not payload.items:
        raise HTTPException(400, "Lista de items vazia")

    section = validate_section(payload.section)
    items = [i.model_dump() for i in payload.items]
    listings = ingest_items(db, search_term, section, payload.source, items)
    return {"count": len(listings), "items": [to_dict(l) for l in listings]}


@app.get("/api/listings")
def api_listings(
    section: str = "revenda",
    search_term: str | None = None,
    limit: int = 50,
    include_hidden: bool = False,
    db: Session = Depends(get_db),
):
    validate_section(section)
    q = db.query(models.Listing).filter(models.Listing.section == section)
    if search_term:
        q = q.filter(models.Listing.search_term == search_term)
    if not include_hidden:
        q = q.filter(models.Listing.hidden.isnot(True))
    total = q.count()
    q = q.order_by(models.Listing.priority_score.desc())
    if limit > 0:
        q = q.limit(limit)
    listings = q.all()
    return {"total": total, "count": len(listings), "items": [to_dict(l) for l in listings]}


@app.get("/api/listings/{listing_id}/history")
def api_history(listing_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.listing_id == listing_id)
        .order_by(models.PriceHistory.id.asc())
        .all()
    )
    return {
        "items": [
            {"price": r.price, "seen_at": r.seen_at.isoformat() if r.seen_at else None}
            for r in rows
        ]
    }


@app.get("/api/search-terms")
def api_search_terms(section: str = "revenda", db: Session = Depends(get_db)):
    validate_section(section)
    rows = (
        db.query(models.Listing.search_term, func.count(models.Listing.id))
        .filter(models.Listing.section == section, models.Listing.hidden.isnot(True))
        .group_by(models.Listing.search_term)
        .all()
    )
    return {"terms": [{"term": t, "count": c} for t, c in rows]}


@app.post("/api/parse-promo")
def api_parse_promo(payload: ParseRequest):
    return parse_promo(payload.text)


@app.post("/api/manual")
def api_manual(payload: ManualItem, db: Session = Depends(get_db)):
    search_term = payload.search_term.strip()
    if not search_term:
        raise HTTPException(400, "Informe a que busca/categoria esse item pertence")
    section = validate_section(payload.section)
    expires_at = normalize_expiry(payload.expires_at)

    url = payload.url or f"manual://{section}/{search_term}/{payload.title}"

    listing = db.query(models.Listing).filter(models.Listing.url == url).first()
    if listing is None:
        listing = models.Listing(
            section=section,
            source=payload.source,
            search_term=search_term,
            title=payload.title,
            url=url,
            hidden=False,
        )
        db.add(listing)
        db.flush()
    listing.title = payload.title
    listing.old_price = payload.old_price
    listing.expires_at = expires_at
    listing.description = payload.description
    listing.location = payload.location
    listing.search_term = search_term
    record_price(db, listing, payload.price)
    db.commit()

    rescore_group(db, search_term, section)

    db.refresh(listing)
    return to_dict(listing)


@app.patch("/api/listings/{listing_id}")
def api_patch(listing_id: int, payload: ListingPatch, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Item nao encontrado")
    if payload.hidden is not None:
        listing.hidden = payload.hidden
    db.commit()
    db.refresh(listing)
    return to_dict(listing)


@app.delete("/api/listings/{listing_id}")
def api_delete(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Item nao encontrado")
    search_term, section = listing.search_term, listing.section
    db.query(models.PriceHistory).filter(models.PriceHistory.listing_id == listing_id).delete()
    db.delete(listing)
    db.commit()
    rescore_group(db, search_term, section)
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
