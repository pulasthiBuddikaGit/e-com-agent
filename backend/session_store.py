from __future__ import annotations

import asyncio
from datetime import date

from .models import Cart, CartItem, ChatMessage, ProductSummary, ShoppingSession, utc_now


class SessionStore:
    """Small in-memory store for MVP chat/cart state.

    This is intentionally process-local. Replace it with Redis or a database before
    running multiple backend workers.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, ShoppingSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str | None = None) -> ShoppingSession:
        async with self._lock:
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]

            session = ShoppingSession(session_id=session_id) if session_id else ShoppingSession()
            self._sessions[session.session_id] = session
            return session

    async def append_message(self, session_id: str, role: str, content: str) -> ShoppingSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.messages.append(ChatMessage(role=role, content=content))
            session.updated_at = utc_now()
            return session

    async def set_delivery(
        self,
        session_id: str,
        city: str | None = None,
        delivery_date: date | None = None,
    ) -> ShoppingSession:
        async with self._lock:
            session = self._sessions[session_id]
            if city is not None:
                session.delivery_city = city
            if delivery_date is not None:
                session.delivery_date = delivery_date
            session.updated_at = utc_now()
            return session

    async def set_checkout_context(self, session_id: str, context: dict) -> ShoppingSession:
        async with self._lock:
            session = self._sessions[session_id]
            session.checkout_context.update(context)
            session.updated_at = utc_now()
            return session

    async def update_cart(
        self,
        session_id: str,
        action: str,
        product_id: str | None = None,
        quantity: int = 1,
        product: ProductSummary | dict | None = None,
        currency: str = "LKR",
    ) -> ShoppingSession:
        async with self._lock:
            session = self._sessions[session_id]

            if action == "clear":
                session.cart = Cart(currency=currency)
                session.updated_at = utc_now()
                return session

            if not product_id:
                raise ValueError("product_id is required for cart add, update, and remove actions.")

            existing_index = next(
                (index for index, item in enumerate(session.cart.items) if item.product_id == product_id),
                None,
            )

            if action == "remove":
                if existing_index is not None:
                    session.cart.items.pop(existing_index)
            elif action == "update":
                if existing_index is None:
                    raise ValueError(f"Product {product_id} is not in the cart.")
                session.cart.items[existing_index].quantity = quantity
            elif action == "add":
                if existing_index is not None:
                    session.cart.items[existing_index].quantity += quantity
                else:
                    session.cart.items.append(
                        self._cart_item_from_product(product_id, quantity, product, currency)
                    )
            else:
                raise ValueError(f"Unsupported cart action: {action}")

            session.cart.currency = currency
            session.cart = self._recalculate_cart(session.cart)
            session.updated_at = utc_now()
            return session

    def _cart_item_from_product(
        self,
        product_id: str,
        quantity: int,
        product: ProductSummary | dict | None,
        currency: str,
    ) -> CartItem:
        if isinstance(product, ProductSummary):
            return CartItem(
                product_id=product.product_id,
                quantity=quantity,
                name=product.name,
                unit_price=product.price,
                currency=product.currency or currency,
                image_url=product.image_url,
                url=product.url,
                raw=product.raw,
            )

        product_dict = product if isinstance(product, dict) else {}
        return CartItem(
            product_id=product_id,
            quantity=quantity,
            name=product_dict.get("name") or product_dict.get("title") or product_dict.get("product_name"),
            unit_price=self._coerce_float(
                product_dict.get("price")
                or product_dict.get("unit_price")
                or product_dict.get("sale_price")
                or product_dict.get("current_price")
            ),
            currency=product_dict.get("currency") or currency,
            image_url=product_dict.get("image_url") or product_dict.get("image") or product_dict.get("thumbnail"),
            url=product_dict.get("url") or product_dict.get("product_url"),
            raw=product_dict,
        )

    def _recalculate_cart(self, cart: Cart) -> Cart:
        total = 0.0
        has_prices = False
        for item in cart.items:
            if item.unit_price is None:
                continue
            has_prices = True
            total += item.unit_price * item.quantity
        cart.estimated_total = round(total, 2) if has_prices else None
        return cart

    def _coerce_float(self, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("LKR", "").replace("Rs.", "").strip()
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

