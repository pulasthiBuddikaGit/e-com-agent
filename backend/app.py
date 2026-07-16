from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .agent import ShoppingAgent
from .config import Settings, get_settings
from .kapruka_mcp import KaprukaMCPClient, KaprukaMCPError
from .models import (
    CartResponse,
    CartUpdateRequest,
    ChatRequest,
    ChatResponse,
    CheckoutCreateRequest,
    CheckoutCreateResponse,
    CheckoutPrepareRequest,
    CheckoutPrepareResponse,
    DeliveryCheckRequest,
    DeliveryCitySearchResponse,
    OrderTrackResponse,
    ProductDetailResponse,
    ProductSearchRequest,
)
from .rate_limit import InMemoryRateLimiter
from .session_store import SessionStore


settings = get_settings()
session_store = SessionStore()
rate_limiter = InMemoryRateLimiter()
mcp_client = KaprukaMCPClient(settings)
shopping_agent = ShoppingAgent(settings, mcp_client, session_store)

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_client_id(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


async def enforce_mcp_limit(request: Request, response: Response) -> None:
    decision = await rate_limiter.check(
        get_client_id(request),
        "mcp",
        settings.mcp_requests_per_minute,
        60,
    )
    if not decision.allowed:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=decision.detail)


async def enforce_create_order_limit(request: Request, response: Response) -> None:
    await enforce_mcp_limit(request, response)
    decision = await rate_limiter.check(
        get_client_id(request),
        "kapruka_create_order",
        settings.create_order_requests_per_hour,
        3600,
    )
    if not decision.allowed:
        response.headers["Retry-After"] = str(decision.retry_after_seconds)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=decision.detail)


async def mcp_guard(dependency: Annotated[None, Depends(enforce_mcp_limit)] = None) -> None:
    return dependency


async def create_order_guard(
    dependency: Annotated[None, Depends(enforce_create_order_limit)] = None,
) -> None:
    return dependency


def mcp_http_exception(exc: KaprukaMCPError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=str(exc),
    )


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
        "gemini_model": settings.gemini_model,
        "gemini_configured": bool(settings.gemini_api_key),
        "kapruka_mcp_url": settings.kapruka_mcp_url,
    }


@app.get(f"{settings.api_prefix}/mcp/tools", dependencies=[Depends(mcp_guard)])
async def list_mcp_tools() -> Any:
    try:
        return await mcp_client.list_tools()
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.post(f"{settings.api_prefix}/chat", response_model=ChatResponse, dependencies=[Depends(mcp_guard)])
async def chat(request: ChatRequest) -> ChatResponse:
    return await shopping_agent.handle_chat(
        message=request.message,
        session_id=request.session_id,
        currency=request.currency,
    )


@app.get(f"{settings.api_prefix}/categories", dependencies=[Depends(mcp_guard)])
async def categories(depth: int = Query(default=1, ge=1, le=2)) -> Any:
    try:
        return await mcp_client.list_categories(depth=depth)
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.post(f"{settings.api_prefix}/products/search", dependencies=[Depends(mcp_guard)])
async def search_products(request: ProductSearchRequest) -> dict[str, Any]:
    try:
        raw = await mcp_client.search_products(**request.model_dump())
        normalized = mcp_client.normalize_products(raw, currency=request.currency)
        return {
            "products": [product.model_dump(mode="json") for product in normalized],
            "raw": raw,
        }
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.get(
    f"{settings.api_prefix}/products/{{product_id}}",
    response_model=ProductDetailResponse,
    dependencies=[Depends(mcp_guard)],
)
async def get_product(
    product_id: Annotated[str, Path(min_length=1, max_length=120)],
    currency: str = Query(default="LKR"),
) -> ProductDetailResponse:
    try:
        raw = await mcp_client.get_product(product_id=product_id, currency=currency)
        normalized = mcp_client.normalize_product(raw, currency=currency)
        return ProductDetailResponse(product=raw, normalized=normalized)
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.get(
    f"{settings.api_prefix}/delivery/cities",
    response_model=DeliveryCitySearchResponse,
    dependencies=[Depends(mcp_guard)],
)
async def delivery_cities(
    query: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=50),
) -> DeliveryCitySearchResponse:
    try:
        return DeliveryCitySearchResponse(
            matches=await mcp_client.list_delivery_cities(query=query, limit=limit)
        )
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.post(f"{settings.api_prefix}/delivery/check", dependencies=[Depends(mcp_guard)])
async def check_delivery(request: DeliveryCheckRequest) -> dict[str, Any]:
    try:
        return await mcp_client.check_delivery(
            city=request.city,
            delivery_date=request.delivery_date,
            product_id=request.product_id,
        )
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


@app.post(f"{settings.api_prefix}/cart", response_model=CartResponse)
async def update_cart(request: CartUpdateRequest) -> CartResponse:
    session = await session_store.get_or_create(request.session_id)
    try:
        updated = await session_store.update_cart(
            session.session_id,
            request.action,
            product_id=request.product_id,
            quantity=request.quantity,
            product=request.product,
            currency=request.currency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return CartResponse(session_id=updated.session_id, cart=updated.cart)


@app.post(
    f"{settings.api_prefix}/checkout/prepare",
    response_model=CheckoutPrepareResponse,
    dependencies=[Depends(mcp_guard)],
)
async def prepare_checkout(request: CheckoutPrepareRequest) -> CheckoutPrepareResponse:
    session = await session_store.get_or_create(request.session_id)
    missing_fields = checkout_missing_fields(
        cart_empty=not session.cart.items,
        recipient=recipient_payload(request.recipient) if request.recipient else None,
        delivery=request.delivery.to_kapruka_payload() if request.delivery else None,
        sender=sender_payload(request.sender) if request.sender else None,
    )

    delivery_checks: list[dict[str, Any]] = []
    warnings: list[str] = []

    if request.delivery and session.cart.items:
        await session_store.set_delivery(
            session.session_id,
            city=request.delivery.city,
            delivery_date=request.delivery.delivery_date,
        )
        for item in session.cart.items:
            try:
                check = await mcp_client.check_delivery(
                    city=request.delivery.city,
                    delivery_date=request.delivery.delivery_date,
                    product_id=item.product_id,
                )
                delivery_checks.append({"product_id": item.product_id, "result": check})
                warnings.extend(extract_warnings(check))
            except KaprukaMCPError as exc:
                delivery_checks.append({"product_id": item.product_id, "error": str(exc)})
                warnings.append(f"Could not verify delivery for {item.product_id}.")

    await session_store.set_checkout_context(
        session.session_id,
        {
            "recipient": recipient_payload(request.recipient) if request.recipient else None,
            "delivery": request.delivery.to_kapruka_payload() if request.delivery else None,
            "sender": sender_payload(request.sender) if request.sender else None,
            "gift_message": request.gift_message,
            "currency": request.currency,
        },
    )

    return CheckoutPrepareResponse(
        session_id=session.session_id,
        ready=not missing_fields
        and not any("error" in item for item in delivery_checks)
        and not any(delivery_unavailable(item.get("result")) for item in delivery_checks),
        missing_fields=missing_fields,
        warnings=sorted(set(warnings)),
        delivery_checks=delivery_checks,
        cart=session.cart,
    )


@app.post(
    f"{settings.api_prefix}/checkout/create",
    response_model=CheckoutCreateResponse,
    dependencies=[Depends(create_order_guard)],
)
async def create_checkout(request: CheckoutCreateRequest) -> CheckoutCreateResponse:
    session = await session_store.get_or_create(request.session_id)
    if not session.cart.items and not request.cart:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty.")

    missing_fields = checkout_missing_fields(
        cart_empty=not session.cart.items and not request.cart,
        recipient=recipient_payload(request.recipient),
        delivery=request.delivery.to_kapruka_payload(),
        sender=sender_payload(request.sender),
    )
    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Checkout details are incomplete.", "missing_fields": missing_fields},
        )

    cart_payload = sanitize_cart_payload(
        request.cart
        or [
            {
                "product_id": item.product_id,
                "quantity": item.quantity,
            }
            for item in session.cart.items
        ]
    )

    warnings: list[str] = []
    product_ids = [item.product_id for item in session.cart.items] or [
        str(item.get("product_id") or item.get("product_code") or item.get("code"))
        for item in cart_payload
        if item.get("product_id") or item.get("product_code") or item.get("code")
    ]
    for product_id in product_ids:
        try:
            check = await mcp_client.check_delivery(
                city=request.delivery.city,
                delivery_date=request.delivery.delivery_date,
                product_id=product_id,
            )
        except KaprukaMCPError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not verify delivery before checkout: {exc}",
            ) from exc

        warnings.extend(extract_warnings(check))
        if delivery_unavailable(check):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Kapruka delivery is not available for product {product_id} on the selected city/date.",
            )

    try:
        order = await mcp_client.create_order(
            cart=cart_payload,
            recipient=recipient_payload(request.recipient),
            delivery=request.delivery.to_kapruka_payload(),
            sender=sender_payload(request.sender),
            gift_message=request.gift_message,
            currency=request.currency,
        )
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc

    return CheckoutCreateResponse(
        session_id=session.session_id,
        order=order,
        checkout_url=extract_checkout_url(order),
        warnings=sorted(set(warnings)),
    )


@app.get(
    f"{settings.api_prefix}/orders/{{order_number}}",
    response_model=OrderTrackResponse,
    dependencies=[Depends(mcp_guard)],
)
async def track_order(
    order_number: Annotated[str, Path(min_length=3, max_length=80)],
) -> OrderTrackResponse:
    try:
        return OrderTrackResponse(
            order_number=order_number,
            status=await mcp_client.track_order(order_number=order_number),
        )
    except KaprukaMCPError as exc:
        raise mcp_http_exception(exc) from exc


def checkout_missing_fields(
    cart_empty: bool,
    recipient: dict[str, Any] | None,
    delivery: dict[str, Any] | None,
    sender: dict[str, Any] | None,
) -> list[str]:
    missing: list[str] = []
    if cart_empty:
        missing.append("cart")
    if recipient is None:
        missing.append("recipient")
    else:
        if not (recipient.get("name") or recipient.get("full_name")):
            missing.append("recipient.name")
        if not recipient.get("phone"):
            missing.append("recipient.phone")
    if delivery is None:
        missing.append("delivery")
    else:
        if not delivery.get("city"):
            missing.append("delivery.city")
        if not (delivery.get("date") or delivery.get("delivery_date")):
            missing.append("delivery.delivery_date")
        if not delivery.get("address"):
            missing.append("delivery.address")
    if sender is None:
        missing.append("sender")
    else:
        if not (sender.get("name") or sender.get("full_name")):
            missing.append("sender.name")
    return missing


def recipient_payload(recipient: Any) -> dict[str, Any]:
    name = recipient.name or recipient.full_name
    payload = {"name": name, "phone": recipient.phone}
    payload.update(
        {
            key: value
            for key, value in recipient.raw.items()
            if key in {"name", "phone"} and value is not None
        }
    )
    return {key: value for key, value in payload.items() if value is not None}


def sender_payload(sender: Any) -> dict[str, Any]:
    name = sender.name or sender.full_name
    anonymous = sender.anonymous
    if anonymous is None:
        anonymous = bool(sender.raw.get("anonymous", False))
    payload = {"name": name, "anonymous": anonymous}
    payload.update(
        {
            key: value
            for key, value in sender.raw.items()
            if key in {"name", "anonymous"} and value is not None
        }
    )
    return {key: value for key, value in payload.items() if value is not None}


def sanitize_cart_payload(cart: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sanitized = []
    for item in cart:
        product_id = item.get("product_id") or item.get("product_code") or item.get("code")
        if not product_id:
            continue
        clean_item = {
            "product_id": product_id,
            "quantity": int(item.get("quantity") or item.get("qty") or 1),
        }
        if item.get("icing_text"):
            clean_item["icing_text"] = item["icing_text"]
        sanitized.append(clean_item)
    return sanitized


def extract_warnings(payload: Any) -> list[str]:
    warnings: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if "warning" in key.lower() and isinstance(nested, str):
                    warnings.append(nested)
                else:
                    walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)
    return warnings


def extract_checkout_url(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("checkout_url", "payment_url", "pay_url", "url", "paymentLink", "click_to_pay_url"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        for value in payload.values():
            nested = extract_checkout_url(value)
            if nested:
                return nested
    if isinstance(payload, list):
        for value in payload:
            nested = extract_checkout_url(value)
            if nested:
                return nested
    return None


def delivery_unavailable(payload: Any) -> bool:
    availability_keys = {
        "can_deliver",
        "deliverable",
        "delivery_available",
        "available",
        "is_available",
        "serviceable",
    }

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                lowered = key.lower()
                if lowered in availability_keys:
                    if nested is False:
                        return True
                    if isinstance(nested, str) and nested.strip().lower() in {
                        "false",
                        "no",
                        "unavailable",
                        "not available",
                        "not deliverable",
                    }:
                        return True
                if isinstance(nested, str) and lowered in {"status", "delivery_status"}:
                    if nested.strip().lower() in {"unavailable", "not available", "not deliverable"}:
                        return True
                if walk(nested):
                    return True
        elif isinstance(value, list):
            return any(walk(nested) for nested in value)
        return False

    return walk(payload)
