import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, Listing, Offer, Order

app = FastAPI(title="SneakSync Marketplace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----- Helpers -----
class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if isinstance(v, ObjectId):
            return v
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

def serialize_doc(doc: Dict[str, Any]):
    if not doc:
        return doc
    doc = dict(doc)
    _id = doc.pop("_id", None)
    if _id is not None:
        doc["id"] = str(_id)
    # Convert any nested ObjectIds (best-effort)
    for k, v in list(doc.items()):
        if isinstance(v, ObjectId):
            doc[k] = str(v)
        if isinstance(v, list):
            doc[k] = [str(x) if isinstance(x, ObjectId) else x for x in v]
        if isinstance(v, dict):
            for nk, nv in list(v.items()):
                if isinstance(nv, ObjectId):
                    v[nk] = str(nv)
    return doc


@app.get("/")
def read_root():
    return {"message": "SneakSync Marketplace API is running"}


# ----- Products -----
@app.get("/products")
def list_products(
    q: Optional[str] = Query(None, description="Search query across title/brand/model"),
    brand: Optional[str] = None,
    size: Optional[str] = None,
    condition: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=100),
):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    filter_q: Dict[str, Any] = {}

    if q:
        filter_q["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"brand": {"$regex": q, "$options": "i"}},
            {"model": {"$regex": q, "$options": "i"}},
        ]
    if brand:
        filter_q["brand"] = {"$regex": f"^{brand}$", "$options": "i"}
    if condition:
        filter_q["condition"] = condition
    if size:
        filter_q["size_variants.size"] = size

    total = db["product"].count_documents(filter_q)
    cursor = (
        db["product"].find(filter_q)
        .sort("created_at", -1)
        .skip((page - 1) * per_page)
        .limit(per_page)
    )

    items = [serialize_doc(d) for d in cursor]
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": items,
    }


# ----- Listings -----
class ListingCreate(BaseModel):
    seller_id: str
    product: Product
    price: float
    listing_type: str


@app.post("/listings")
def create_listing(payload: ListingCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Upsert product (by slug if provided, else insert new)
    product_data = payload.product.model_dump()
    existing = None
    if product_data.get("slug"):
        existing = db["product"].find_one({"slug": product_data["slug"]})

    if existing:
        product_id = str(existing["._id"]) if "._id" in existing else str(existing["_id"])  # safety
    else:
        product_id = create_document("product", product_data)

    listing = Listing(
        seller_id=payload.seller_id,
        product_id=product_id,
        price=payload.price,
        listing_type=payload.listing_type,  # validated by schema on DB write
    )

    listing_id = create_document("listing", listing)
    return {"status": "listing_created", "listing_id": listing_id, "product_id": product_id}


# ----- Offers -----
class OfferCreate(BaseModel):
    buyer_id: str
    listing_id: str
    offer_price: float


@app.post("/offers")
def create_offer(payload: OfferCreate):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Ensure listing exists
    listing = db["listing"].find_one({"_id": ObjectId(payload.listing_id)}) if ObjectId.is_valid(payload.listing_id) else None
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    offer = Offer(
        buyer_id=payload.buyer_id,
        listing_id=payload.listing_id,
        offer_price=payload.offer_price,
    )
    offer_id = create_document("offer", offer)
    return {"status": "offer_created", "offer_id": offer_id}


# ----- Checkout / Orders -----
class CheckoutRequest(BaseModel):
    cart_id: Optional[str] = None  # placeholder for future cart expansion
    listing_id: str
    buyer_id: str
    payment_method: Dict[str, Any]
    shipping_option: str


@app.post("/checkout")
def checkout(payload: CheckoutRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    listing = db["listing"].find_one({"_id": ObjectId(payload.listing_id)}) if ObjectId.is_valid(payload.listing_id) else None
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    if listing.get("status") and listing["status"] != "active":
        raise HTTPException(status_code=400, detail="Listing not available")

    order = Order(
        buyer_id=payload.buyer_id,
        listing_id=str(listing["_id"]),
        amount=float(listing["price"]),
        currency=listing.get("currency", "USD"),
        payment_method={k: str(v) for k, v in payload.payment_method.items()},
        shipping_option=payload.shipping_option,
    )
    order_id = create_document("order", order)

    # Mark listing as sold (simple flow for MVP; real escrow settles later)
    db["listing"].update_one({"_id": listing["_id"]}, {"$set": {"status": "sold"}})

    return {"status": "order_confirmation", "order_id": order_id}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
