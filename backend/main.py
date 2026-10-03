import os

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models
from .database import Base, engine, get_db
from .scoring import compute_group_median, score_listing
from .scraper import ScrapeError, search_olx

# Chave opcional pra proteger o /api/ingest (usado pelo script de sync local).
# Se nao estiver configurada, o endpoint fica aberto — defina SYNC_API_KEY
# no ambiente (local e no Render) pra travar isso.
SYNC_API_KEY = os.environ.get("SYNC_API_KEY")

# Na versao hospedada a OLX bloqueia o IP do servidor, entao a busca direta
# fica desligada la (ALLOW_LIVE_SEARCH=false no render.yaml) e os dados vem
# do sync local.
LIVE_SEARCH = os.environ.get("ALLOW_LIVE_SEARCH", "true").lower() == "true"

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Resale Finder")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


class SearchRequest(BaseModel):
    query: str
    max_pages: int = 2
    only_poa_metro: bool = True


class ManualItem(BaseModel):
    title: str
    price: float
    search_term: str
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


def rescore_group(db: Session, search_term: str):
    """Recalcula o score de todos os anuncios de um termo de busca, usando a
    mediana de preco do grupo inteiro (OLX + manuais) como referencia."""
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.search_term == search_term)
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

    db.commit()
    return median


def ingest_items(db: Session, search_term: str, source: str, items: list[dict]):
    """Grava (upsert) anuncios ja obtidos (de onde for) e recalcula os scores
    do grupo. Usado tanto pelo /api/search (scraping ao vivo) quanto pelo
    /api/ingest (recebendo anuncios ja raspados por um script local)."""
    for item in items:
        existing = db.query(models.Listing).filter(models.Listing.url == item["url"]).first()
        if existing:
            existing.price = item["price"]
            existing.old_price = item.get("old_price")
            existing.location = item.get("location")
            existing.posted_at_text = item.get("posted_at_text")
            continue
        db.add(
            models.Listing(
                source=source,
                search_term=search_term,
                title=item["title"],
                price=item["price"],
                old_price=item.get("old_price"),
                location=item.get("location"),
                url=item["url"],
                posted_at_text=item.get("posted_at_text"),
                description=item.get("description"),
            )
        )
    db.commit()

    rescore_group(db, search_term)

    listings = (
        db.query(models.Listing)
        .filter(models.Listing.search_term == search_term)
        .order_by(models.Listing.priority_score.desc())
        .all()
    )
    return listings


def check_sync_key(x_sync_key: str | None):
    if SYNC_API_KEY and x_sync_key != SYNC_API_KEY:
        raise HTTPException(401, "Chave de sincronizacao invalida")


@app.get("/api/config")
def api_config():
    return {"live_search": LIVE_SEARCH}


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

    listings = ingest_items(db, query, "olx", items)
    return {"count": len(listings), "items": [to_dict(l) for l in listings]}


@app.post("/api/ingest")
def api_ingest(
    payload: IngestRequest,
    db: Session = Depends(get_db),
    x_sync_key: str | None = Header(default=None),
):
    """Recebe anuncios ja raspados por um script rodando em outra maquina
    (ex: o sync local, que busca na OLX a partir de um IP residencial pra
    nao ser bloqueado pela Cloudflare quando o servidor esta na nuvem)."""
    check_sync_key(x_sync_key)

    search_term = payload.search_term.strip()
    if not search_term:
        raise HTTPException(400, "Informe search_term")
    if not payload.items:
        raise HTTPException(400, "Lista de items vazia")

    items = [i.model_dump() for i in payload.items]
    listings = ingest_items(db, search_term, payload.source, items)
    return {"count": len(listings), "items": [to_dict(l) for l in listings]}


@app.get("/api/listings")
def api_listings(
    search_term: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(models.Listing)
    if search_term:
        q = q.filter(models.Listing.search_term == search_term)
    total = q.count()
    q = q.order_by(models.Listing.priority_score.desc())
    if limit > 0:
        q = q.limit(limit)
    listings = q.all()
    return {"total": total, "count": len(listings), "items": [to_dict(l) for l in listings]}


@app.get("/api/search-terms")
def api_search_terms(db: Session = Depends(get_db)):
    rows = db.query(models.Listing.search_term, func.count(models.Listing.id)).group_by(
        models.Listing.search_term
    ).all()
    return {"terms": [{"term": t, "count": c} for t, c in rows]}


@app.post("/api/manual")
def api_manual(payload: ManualItem, db: Session = Depends(get_db)):
    search_term = payload.search_term.strip()
    if not search_term:
        raise HTTPException(400, "Informe a que busca/categoria esse item pertence")

    url = payload.url or f"manual://{search_term}/{payload.title}"

    existing = db.query(models.Listing).filter(models.Listing.url == url).first()
    if existing:
        existing.title = payload.title
        existing.price = payload.price
        existing.description = payload.description
        existing.location = payload.location
    else:
        db.add(
            models.Listing(
                source=payload.source,
                search_term=search_term,
                title=payload.title,
                price=payload.price,
                description=payload.description,
                location=payload.location,
                url=url,
            )
        )
    db.commit()

    rescore_group(db, search_term)

    listing = db.query(models.Listing).filter(models.Listing.url == url).first()
    return to_dict(listing)


@app.delete("/api/listings/{listing_id}")
def api_delete(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(models.Listing).filter(models.Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(404, "Item nao encontrado")
    search_term = listing.search_term
    db.delete(listing)
    db.commit()
    rescore_group(db, search_term)
    return {"ok": True}


def to_dict(listing: models.Listing) -> dict:
    return {
        "id": listing.id,
        "source": listing.source,
        "search_term": listing.search_term,
        "title": listing.title,
        "price": listing.price,
        "old_price": listing.old_price,
        "location": listing.location,
        "url": listing.url,
        "posted_at_text": listing.posted_at_text,
        "description": listing.description,
        "price_score": listing.price_score,
        "final_score": listing.final_score,
        "label": listing.label,
        "flags": listing.flags,
        "priority_score": listing.priority_score,
        "priority_reasons": listing.priority_reasons,
    }


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
