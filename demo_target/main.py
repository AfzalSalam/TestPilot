"""Demo API under test.

A tiny "store" API with a switch that deliberately breaks it, so you can watch TestPilot's
regression detection work:

    curl -X POST localhost:9000/admin/mode -H 'content-type: application/json' -d '{"mode":"broken"}'
    # modes: healthy | broken (500s + wrong payloads) | slow (adds ~600 ms latency)
"""

import asyncio
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Demo Store API", version="1.0.0")
STATE = {"mode": "healthy"}
PRODUCTS = {
    1: {"id": 1, "name": "Mechanical Keyboard", "price": 89.0, "stock": 24, "tags": ["peripherals", "office"]},
    2: {"id": 2, "name": "USB-C Dock", "price": 129.5, "stock": 8, "tags": ["peripherals"]},
    3: {"id": 3, "name": "27in Monitor", "price": 249.99, "stock": 12, "tags": ["display", "office"]},
}


class ProductIn(BaseModel):
    name: str = Field(min_length=1)
    price: float = Field(gt=0)
    stock: int = Field(default=0, ge=0)
    tags: list[str] = []


class ModeIn(BaseModel):
    mode: Literal["healthy", "broken", "slow"]


async def simulate_latency() -> None:
    if STATE["mode"] == "slow":
        await asyncio.sleep(0.6)
    else:
        await asyncio.sleep(0.01)


def require_token(authorization: str | None = Header(default=None)) -> str:
    if authorization != "Bearer demo-token":
        raise HTTPException(401, "Invalid or missing token")
    return "demo-user"


@app.get("/health")
async def health():
    return {"status": "ok", "mode": STATE["mode"]}


@app.get("/products")
async def list_products(limit: int = 10):
    await simulate_latency()
    items = list(PRODUCTS.values())[:limit]
    return {"count": len(items), "items": items}


@app.get("/products/{product_id}")
async def get_product(product_id: int):
    await simulate_latency()
    if STATE["mode"] == "broken":
        raise HTTPException(500, "database connection lost")
    if product_id not in PRODUCTS:
        raise HTTPException(404, "Product not found")
    return PRODUCTS[product_id]


@app.post("/products", status_code=201)
async def create_product(body: ProductIn):
    await simulate_latency()
    new_id = max(PRODUCTS) + 1
    PRODUCTS[new_id] = {"id": new_id, **body.model_dump()}
    if STATE["mode"] == "broken":  # silent contract break: wrong status payload shape
        return {"created": True}
    return PRODUCTS[new_id]


@app.get("/users/me")
async def me(user: str = Depends(require_token)):
    await simulate_latency()
    return {"username": user, "plan": "pro"}


@app.get("/admin/mode")
async def get_mode():
    return STATE


@app.post("/admin/mode")
async def set_mode(body: ModeIn):
    STATE["mode"] = body.mode
    return STATE
