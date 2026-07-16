from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from .config import Settings
from .kapruka_mcp import KaprukaMCPClient, KaprukaMCPError
from .models import AgentIntent, ChatResponse, ProductSearchRequest, UIBlock
from .session_store import SessionStore


class ShoppingAgent:
    def __init__(
        self,
        settings: Settings,
        mcp_client: KaprukaMCPClient,
        session_store: SessionStore,
    ) -> None:
        self.settings = settings
        self.mcp_client = mcp_client
        self.session_store = session_store
        self.gemini_client = (
            genai.Client(api_key=settings.gemini_api_key) if settings.gemini_api_key else None
        )

    async def handle_chat(self, message: str, session_id: str | None, currency: str) -> ChatResponse:
        session = await self.session_store.get_or_create(session_id)
        await self.session_store.append_message(session.session_id, "user", message)

        intent = await self._classify_intent(message, session.session_id, currency)
        if intent.requires_clarification and intent.clarifying_question:
            return await self._respond(
                session.session_id,
                intent.clarifying_question,
                [UIBlock(type="clarification", data={"question": intent.clarifying_question})],
            )

        try:
            if intent.intent == "track_order":
                response = await self._handle_track_order(intent, session.session_id)
            elif intent.intent == "product_detail":
                response = await self._handle_product_detail(intent, session.session_id, currency)
            elif intent.intent == "check_delivery":
                response = await self._handle_delivery_check(intent, session.session_id)
            elif intent.intent == "view_cart":
                response = await self._respond(
                    session.session_id,
                    "Here is your current cart.",
                    [UIBlock(type="cart", data=session.cart.model_dump(mode="json"))],
                )
            elif intent.intent == "add_to_cart":
                response = await self._handle_add_to_cart(intent, session.session_id, currency)
            elif intent.intent == "remove_from_cart":
                response = await self._handle_remove_from_cart(intent, session.session_id)
            elif intent.intent == "checkout_prepare":
                response = await self._respond(
                    session.session_id,
                    "I can help prepare checkout. I still need recipient, sender, delivery city, delivery date, and confirmation before creating a payment link.",
                    [UIBlock(type="checkout_prompt", data={"requires_explicit_confirmation": True})],
                )
            elif intent.intent == "general":
                response = await self._respond(
                    session.session_id,
                    "Tell me what you want to buy from Kapruka, who it is for, or an order number you want to track.",
                    [],
                )
            else:
                response = await self._handle_search(intent, session.session_id, message, currency)
        except KaprukaMCPError as exc:
            response = await self._respond(
                session.session_id,
                "I could not reach Kapruka live data right now. Please try again in a moment.",
                [UIBlock(type="error", data={"detail": str(exc)})],
            )

        return response

    async def _handle_search(
        self,
        intent: AgentIntent,
        session_id: str,
        fallback_query: str,
        currency: str,
    ) -> ChatResponse:
        search = intent.search or {}
        request = ProductSearchRequest(
            q=str(search.get("q") or fallback_query),
            category=search.get("category"),
            min_price=search.get("min_price"),
            max_price=search.get("max_price"),
            in_stock_only=bool(search.get("in_stock_only", True)),
            sort=search.get("sort"),
            limit=int(search.get("limit") or 12),
            cursor=search.get("cursor"),
            currency=currency,
        )
        raw = await self.mcp_client.search_products(**request.model_dump())
        products = self.mcp_client.normalize_products(raw, currency=currency)

        if not products:
            return await self._respond(
                session_id,
                "I searched Kapruka live inventory but did not find matching products. Try a simpler product name or category.",
                [UIBlock(type="product_grid", data={"products": [], "raw": raw})],
            )

        return await self._respond(
            session_id,
            f"I found {len(products)} live Kapruka option{'s' if len(products) != 1 else ''}.",
            [
                UIBlock(
                    type="product_grid",
                    data={
                        "query": request.q,
                        "products": [product.model_dump(mode="json") for product in products],
                        "raw": raw,
                    },
                )
            ],
        )

    async def _handle_product_detail(
        self,
        intent: AgentIntent,
        session_id: str,
        currency: str,
    ) -> ChatResponse:
        if not intent.product_id:
            return await self._respond(session_id, "Which product would you like me to open?", [])

        raw = await self.mcp_client.get_product(intent.product_id, currency=currency)
        normalized = self.mcp_client.normalize_product(raw, currency=currency)
        return await self._respond(
            session_id,
            normalized.name if normalized and normalized.name else "Here are the live product details.",
            [
                UIBlock(
                    type="product_detail",
                    data={
                        "product": raw,
                        "normalized": normalized.model_dump(mode="json") if normalized else None,
                    },
                )
            ],
        )

    async def _handle_track_order(self, intent: AgentIntent, session_id: str) -> ChatResponse:
        if not intent.order_number:
            return await self._respond(session_id, "Please send the Kapruka order number to track.", [])

        status = await self.mcp_client.track_order(intent.order_number)
        return await self._respond(
            session_id,
            "Here is the latest order status from Kapruka.",
            [UIBlock(type="order_status", data={"order_number": intent.order_number, "status": status})],
        )

    async def _handle_delivery_check(self, intent: AgentIntent, session_id: str) -> ChatResponse:
        session = await self.session_store.get_or_create(session_id)
        city = intent.city or session.delivery_city
        delivery_date = intent.delivery_date or (
            session.delivery_date.isoformat() if session.delivery_date else None
        )
        product_id = intent.product_id or (
            session.cart.items[0].product_id if session.cart.items else None
        )

        if not city or not delivery_date:
            return await self._respond(
                session_id,
                "Please provide the delivery city and date so I can check Kapruka delivery availability.",
                [UIBlock(type="delivery_prompt", data={"needs": ["city", "delivery_date"]})],
            )

        check = await self.mcp_client.check_delivery(city, delivery_date, product_id=product_id)
        try:
            parsed_date = date.fromisoformat(delivery_date)
            await self.session_store.set_delivery(session_id, city=city, delivery_date=parsed_date)
        except ValueError:
            await self.session_store.set_delivery(session_id, city=city)

        return await self._respond(
            session_id,
            "I checked Kapruka delivery availability for that city and date.",
            [UIBlock(type="delivery_check", data={"check": check})],
        )

    async def _handle_add_to_cart(
        self,
        intent: AgentIntent,
        session_id: str,
        currency: str,
    ) -> ChatResponse:
        product_id = intent.product_id or intent.cart_action.get("product_id")
        if not product_id:
            return await self._respond(
                session_id,
                "Please choose a product before I add it to the cart.",
                [],
            )

        raw = await self.mcp_client.get_product(product_id, currency=currency)
        product = self.mcp_client.normalize_product(raw, currency=currency)
        quantity = int(intent.cart_action.get("quantity") or 1)
        session = await self.session_store.update_cart(
            session_id,
            "add",
            product_id=product_id,
            quantity=quantity,
            product=product or raw,
            currency=currency,
        )
        name = product.name if product and product.name else product_id
        return await self._respond(
            session_id,
            f"Added {name} to your cart.",
            [UIBlock(type="cart", data=session.cart.model_dump(mode="json"))],
        )

    async def _handle_remove_from_cart(self, intent: AgentIntent, session_id: str) -> ChatResponse:
        product_id = intent.product_id or intent.cart_action.get("product_id")
        if not product_id:
            return await self._respond(session_id, "Which product should I remove from the cart?", [])
        session = await self.session_store.update_cart(session_id, "remove", product_id=product_id)
        return await self._respond(
            session_id,
            "Removed that product from your cart.",
            [UIBlock(type="cart", data=session.cart.model_dump(mode="json"))],
        )

    async def _respond(
        self,
        session_id: str,
        message: str,
        blocks: list[UIBlock],
    ) -> ChatResponse:
        session = await self.session_store.append_message(session_id, "assistant", message)
        return ChatResponse(
            session_id=session_id,
            message=message,
            blocks=blocks,
            cart=session.cart,
            model=self.settings.gemini_model if self.gemini_client else None,
        )

    async def _classify_intent(
        self,
        message: str,
        session_id: str,
        currency: str,
    ) -> AgentIntent:
        if not self.gemini_client:
            return self._heuristic_intent(message)

        session = await self.session_store.get_or_create(session_id)
        recent_messages = [
            {"role": item.role, "content": item.content}
            for item in session.messages[-8:]
            if item.role in {"user", "assistant"}
        ]
        prompt = {
            "task": "Classify the next shopping action for a Kapruka Sri Lanka ecommerce chat agent.",
            "rules": [
                "Return JSON only.",
                "Never invent prices, stock, delivery availability, or checkout links.",
                "Use search_products for normal shopping requests.",
                "Use checkout_prepare when the user asks to checkout or pay.",
                "Use track_order only when an order number is present or clearly requested.",
                "Use check_delivery when city and delivery date are present or delivery availability is requested.",
                "Do not create orders from chat classification.",
            ],
            "allowed_intents": [
                "search_products",
                "product_detail",
                "check_delivery",
                "track_order",
                "checkout_prepare",
                "view_cart",
                "add_to_cart",
                "remove_from_cart",
                "general",
            ],
            "json_shape": {
                "intent": "search_products",
                "search": {
                    "q": "short product search query",
                    "category": None,
                    "min_price": None,
                    "max_price": None,
                    "in_stock_only": True,
                    "sort": None,
                    "limit": 12,
                },
                "product_id": None,
                "city": None,
                "delivery_date": None,
                "order_number": None,
                "cart_action": {"product_id": None, "quantity": 1},
                "requires_clarification": False,
                "clarifying_question": None,
            },
            "currency": currency,
            "cart": session.cart.model_dump(mode="json"),
            "recent_messages": recent_messages,
            "user_message": message,
        }

        try:
            response_text = await asyncio.to_thread(self._call_gemini_for_intent, prompt)
            data = json.loads(self._strip_json_fence(response_text))
            return AgentIntent.model_validate(data)
        except Exception:
            return self._heuristic_intent(message)

    def _call_gemini_for_intent(self, prompt: dict[str, Any]) -> str:
        response = self.gemini_client.models.generate_content(
            model=self.settings.gemini_model,
            contents=json.dumps(prompt, ensure_ascii=False),
            config=types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=800,
                response_mime_type="application/json",
            ),
        )
        return response.text or "{}"

    def _heuristic_intent(self, message: str) -> AgentIntent:
        lowered = message.lower()
        order_number = self._extract_order_number(message)
        product_id = self._extract_product_id(message)

        if "track" in lowered or (order_number and "order" in lowered):
            return AgentIntent(intent="track_order", order_number=order_number)

        if "cart" in lowered and not any(word in lowered for word in ("add", "remove", "delete")):
            return AgentIntent(intent="view_cart")

        if any(word in lowered for word in ("checkout", "pay", "payment", "buy now")):
            return AgentIntent(intent="checkout_prepare")

        if "deliver" in lowered or "delivery" in lowered:
            return AgentIntent(intent="check_delivery", product_id=product_id)

        if any(word in lowered for word in ("add", "put")) and "cart" in lowered:
            return AgentIntent(
                intent="add_to_cart",
                product_id=product_id,
                cart_action={"product_id": product_id, "quantity": 1},
            )

        if any(word in lowered for word in ("remove", "delete")) and "cart" in lowered:
            return AgentIntent(
                intent="remove_from_cart",
                product_id=product_id,
                cart_action={"product_id": product_id},
            )

        if product_id and any(word in lowered for word in ("details", "open", "show")):
            return AgentIntent(intent="product_detail", product_id=product_id)

        return AgentIntent(intent="search_products", search={"q": message, "in_stock_only": True})

    def _extract_order_number(self, message: str) -> str | None:
        patterns = [
            r"\b(?:order|ord)[\s:#-]*([A-Z0-9-]{5,30})\b",
            r"\b([A-Z]{1,6}\d{4,20})\b",
            r"\b(\d{6,20})\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_product_id(self, message: str) -> str | None:
        match = re.search(r"\b(?:product|item|sku|code)[\s:#-]*([A-Z0-9_-]{3,40})\b", message, re.I)
        if match:
            return match.group(1)
        return None

    def _strip_json_fence(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.I).strip()
            stripped = re.sub(r"```$", "", stripped).strip()
        return stripped
