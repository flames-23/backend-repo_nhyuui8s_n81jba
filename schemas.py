"""
Database Schemas for SneakSync Marketplace

Each Pydantic model below maps to a MongoDB collection. The collection name is the
lowercase of the class name (e.g., Product -> "product").

These schemas are used for validation in API endpoints and to document the data model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, HttpUrl, EmailStr
from typing import List, Optional, Literal, Dict
from datetime import datetime


# --- Core domain schemas ---

class Dimensions(BaseModel):
    length: int = Field(..., ge=0, description="Length in mm")
    width: int = Field(..., ge=0, description="Width in mm")
    height: int = Field(..., ge=0, description="Height in mm")


class SizeVariant(BaseModel):
    size: str
    sku: str
    price: float = Field(..., ge=0)
    currency: str = Field(..., min_length=3, max_length=3, description="ISO currency code e.g., USD")
    inventory_quantity: int = Field(..., ge=0)


class Product(BaseModel):
    """
    Sneakers product master data
    Collection name: "product"
    """
    title: str
    slug: str
    brand: str
    model: str
    release_year: int
    condition: Literal["new", "used", "like_new", "open_box"]
    size_variants: List[SizeVariant]
    images: List[HttpUrl]
    gallery_video: Optional[HttpUrl] = None
    description: str
    materials: Optional[str] = None
    colorway: Optional[str] = None
    tags: List[str] = []
    authenticity_certificate: bool = False
    seller_id: str
    shipping_weight_grams: int = Field(..., ge=0)
    dimensions_mm: Dimensions
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Listing(BaseModel):
    """
    Marketplace listing. A Listing can be fixed price, auction, or make-offer.
    Collection name: "listing"
    """
    seller_id: str
    product_id: str
    price: float = Field(..., ge=0)
    listing_type: Literal["fixed_price", "auction", "make_offer"]
    currency: str = Field("USD", min_length=3, max_length=3)
    status: Literal["active", "sold", "paused", "ended"] = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Offer(BaseModel):
    """
    Buyer offer on a listing
    Collection name: "offer"
    """
    buyer_id: str
    listing_id: str
    offer_price: float = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)
    status: Literal["pending", "accepted", "rejected", "countered", "expired", "withdrawn"] = "pending"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Order(BaseModel):
    """
    Checkout order (escrow-enabled)
    Collection name: "order"
    """
    buyer_id: str
    listing_id: str
    amount: float = Field(..., ge=0)
    currency: str = Field("USD", min_length=3, max_length=3)
    payment_method: Dict[str, str] = Field(default_factory=dict)
    shipping_option: Literal["standard", "express", "store_pickup", "dropship"]
    status: Literal["created", "paid", "shipped", "delivered", "refunded", "cancelled"] = "created"
    escrow_status: Literal["held", "released", "refunded"] = "held"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Auxiliary/example user schema for reference (not used directly in MVP endpoints)
class User(BaseModel):
    name: str
    email: EmailStr
    is_active: bool = True
