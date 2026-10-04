from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class Listing(Base):
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    section = Column(String, default="revenda", index=True)  # revenda | farmacia
    source = Column(String, default="olx", index=True)  # olx | panvel | facebook | manual | ...
    search_term = Column(String, index=True)
    title = Column(String)
    price = Column(Float, nullable=True)
    old_price = Column(Float, nullable=True)
    min_price = Column(Float, nullable=True)
    prev_price = Column(Float, nullable=True)
    location = Column(String, nullable=True)
    url = Column(String, unique=True)
    posted_at_text = Column(String, nullable=True)
    expires_at = Column(String, nullable=True)  # MM/AAAA
    hidden = Column(Boolean, default=False)
    description = Column(Text, nullable=True)

    price_score = Column(Float, nullable=True)
    final_score = Column(Float, nullable=True)
    label = Column(String, nullable=True)
    flags = Column(String, nullable=True)
    priority_score = Column(Float, nullable=True)
    priority_reasons = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True)
    listing_id = Column(Integer, index=True, nullable=False)
    price = Column(Float, nullable=False)
    seen_at = Column(DateTime(timezone=True), server_default=func.now())


class SyncState(Base):
    __tablename__ = "sync_state"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
