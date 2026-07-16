from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


Currency = Literal["LKR", "USD", "AUD", "CAD", "EUR", "GBP"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UIBlock(BaseModel):
    type: str
    data: dict[str, Any] = Field(default_factory=dict)


class ProductSummary(BaseModel):
    product_id: str
    name: str | None = None
    price: float | None = None
    currency: str = "LKR"
    image_url: str | None = None
    url: str | None = None
    in_stock: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class CartItem(BaseModel):
    product_id: str
    quantity: int = Field(default=1, ge=1, le=30)
    name: str | None = None
    unit_price: float | None = None
    currency: str = "LKR"
    image_url: str | None = None
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Cart(BaseModel):
    items: list[CartItem] = Field(default_factory=list)
    currency: str = "LKR"
    estimated_total: float | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None
    currency: Currency = "LKR"


class ChatResponse(BaseModel):
    session_id: str
    message: str
    blocks: list[UIBlock] = Field(default_factory=list)
    cart: Cart
    model: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ProductSearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=200)
    category: str | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    in_stock_only: bool = True
    sort: str | None = None
    limit: int = Field(default=12, ge=1, le=30)
    cursor: str | None = None
    currency: Currency = "LKR"


class ProductDetailResponse(BaseModel):
    product: dict[str, Any]
    normalized: ProductSummary | None = None


class CartUpdateRequest(BaseModel):
    session_id: str | None = None
    action: Literal["add", "update", "remove", "clear"]
    product_id: str | None = None
    quantity: int = Field(default=1, ge=1, le=30)
    product: ProductSummary | dict[str, Any] | None = None
    currency: Currency = "LKR"


class CartResponse(BaseModel):
    session_id: str
    cart: Cart


class DeliveryCitySearchResponse(BaseModel):
    matches: Any


class DeliveryCheckRequest(BaseModel):
    city: str = Field(min_length=1, max_length=120)
    delivery_date: date
    product_id: str | None = None


class CheckoutParty(BaseModel):
    name: str | None = None
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    anonymous: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_kapruka_payload(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True, exclude={"raw"})
        payload.update(self.raw)
        return payload


class CheckoutDelivery(BaseModel):
    city: str
    delivery_date: date
    address: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    location_type: Literal["house", "apartment", "office", "other"] = "house"
    instructions: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

    def to_kapruka_payload(self) -> dict[str, Any]:
        address = self.address
        if not address:
            address = ", ".join(
                item for item in (self.address_line1, self.address_line2) if item
            )
        payload = {
            "address": address,
            "city": self.city,
            "location_type": self.location_type,
            "date": self.delivery_date.isoformat(),
        }
        if self.instructions:
            payload["instructions"] = self.instructions
        payload = {key: value for key, value in payload.items() if value}
        payload.update(self.raw)
        return payload


class CheckoutPrepareRequest(BaseModel):
    session_id: str
    recipient: CheckoutParty | None = None
    delivery: CheckoutDelivery | None = None
    sender: CheckoutParty | None = None
    gift_message: str | None = Field(default=None, max_length=1000)
    currency: Currency = "LKR"


class CheckoutPrepareResponse(BaseModel):
    session_id: str
    ready: bool
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    delivery_checks: list[dict[str, Any]] = Field(default_factory=list)
    cart: Cart


class CheckoutCreateRequest(BaseModel):
    session_id: str
    confirm: bool = False
    recipient: CheckoutParty
    delivery: CheckoutDelivery
    sender: CheckoutParty
    gift_message: str | None = Field(default=None, max_length=1000)
    currency: Currency = "LKR"
    cart: list[dict[str, Any]] | None = None

    @field_validator("confirm")
    @classmethod
    def confirmation_must_be_explicit(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Checkout creation requires confirm=true.")
        return value


class CheckoutCreateResponse(BaseModel):
    session_id: str
    order: dict[str, Any]
    checkout_url: str | None = None
    expires_in_minutes: int = 60
    warnings: list[str] = Field(default_factory=list)


class OrderTrackResponse(BaseModel):
    order_number: str
    status: Any


class AgentIntent(BaseModel):
    intent: Literal[
        "search_products",
        "product_detail",
        "check_delivery",
        "track_order",
        "checkout_prepare",
        "view_cart",
        "add_to_cart",
        "remove_from_cart",
        "general",
    ] = "search_products"
    search: dict[str, Any] = Field(default_factory=dict)
    product_id: str | None = None
    city: str | None = None
    delivery_date: str | None = None
    order_number: str | None = None
    cart_action: dict[str, Any] = Field(default_factory=dict)
    requires_clarification: bool = False
    clarifying_question: str | None = None


class ShoppingSession(BaseModel):
    session_id: str = Field(default_factory=lambda: uuid4().hex)
    messages: list[ChatMessage] = Field(default_factory=list)
    cart: Cart = Field(default_factory=Cart)
    delivery_city: str | None = None
    delivery_date: date | None = None
    checkout_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
