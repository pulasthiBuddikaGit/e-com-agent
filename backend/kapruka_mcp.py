from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from time import monotonic
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import Settings
from .models import ProductSummary


class KaprukaMCPError(RuntimeError):
    pass


class KaprukaMCPClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._cache: dict[tuple[str, str], tuple[float, Any]] = {}
        self._cache_lock = asyncio.Lock()

    async def list_tools(self) -> Any:
        async def run() -> Any:
            timeout = httpx.Timeout(
                self.settings.mcp_read_timeout_seconds,
                connect=self.settings.mcp_connect_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                async with streamable_http_client(
                    self.settings.kapruka_mcp_url,
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await asyncio.wait_for(
                            session.initialize(),
                            timeout=self.settings.mcp_read_timeout_seconds,
                        )
                        result = await asyncio.wait_for(
                            session.list_tools(),
                            timeout=self.settings.mcp_read_timeout_seconds,
                        )
                        return self._to_python(result)

        return await self._with_total_timeout(run())

    async def search_products(
        self,
        q: str,
        category: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        in_stock_only: bool = True,
        sort: str | None = None,
        limit: int = 12,
        cursor: str | None = None,
        currency: str = "LKR",
    ) -> dict[str, Any]:
        arguments = self._drop_none(
            {
                "q": q,
                "category": category,
                "min_price": min_price,
                "max_price": max_price,
                "in_stock_only": in_stock_only,
                "sort": sort,
                "limit": limit,
                "cursor": cursor,
                "currency": currency,
                "include_stubs": False,
            }
        )
        return await self._cached_call(
            "kapruka_search_products",
            self._tool_arguments(arguments),
            ttl_seconds=self.settings.product_cache_ttl_seconds,
        )

    async def get_product(self, product_id: str, currency: str = "LKR") -> dict[str, Any]:
        arguments = {"product_id": product_id, "currency": currency}
        return await self._cached_call(
            "kapruka_get_product",
            self._tool_arguments(arguments),
            ttl_seconds=self.settings.product_cache_ttl_seconds,
        )

    async def list_categories(self, depth: int = 1) -> dict[str, Any]:
        return await self._cached_call(
            "kapruka_list_categories",
            self._tool_arguments({"depth": depth}),
            ttl_seconds=self.settings.category_cache_ttl_seconds,
        )

    async def list_delivery_cities(self, query: str, limit: int = 20) -> dict[str, Any]:
        return await self._call_tool(
            "kapruka_list_delivery_cities",
            self._tool_arguments({"query": query, "limit": limit}),
        )

    async def check_delivery(
        self,
        city: str,
        delivery_date: date | str,
        product_id: str | None = None,
    ) -> dict[str, Any]:
        if isinstance(delivery_date, date):
            delivery_date = delivery_date.isoformat()
        return await self._call_tool(
            "kapruka_check_delivery",
            self._tool_arguments(
                self._drop_none(
                    {
                        "city": city,
                        "delivery_date": delivery_date,
                        "product_id": product_id,
                    }
                )
            ),
        )

    async def create_order(
        self,
        cart: list[dict[str, Any]],
        recipient: dict[str, Any],
        delivery: dict[str, Any],
        sender: dict[str, Any],
        gift_message: str | None = None,
        currency: str = "LKR",
    ) -> dict[str, Any]:
        return await self._call_tool(
            "kapruka_create_order",
            self._tool_arguments(
                self._drop_none(
                    {
                        "cart": cart,
                        "recipient": recipient,
                        "delivery": delivery,
                        "sender": sender,
                        "gift_message": gift_message,
                        "currency": currency,
                    }
                )
            ),
        )

    async def track_order(self, order_number: str) -> dict[str, Any]:
        return await self._call_tool(
            "kapruka_track_order",
            self._tool_arguments({"order_number": order_number}),
        )

    async def _cached_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        ttl_seconds: int,
    ) -> dict[str, Any]:
        cache_key = (tool_name, json.dumps(arguments, sort_keys=True, default=str))
        now = monotonic()

        async with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < ttl_seconds:
                return cached[1]

        result = await self._call_tool(tool_name, arguments)

        async with self._cache_lock:
            self._cache[cache_key] = (now, result)

        return result

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        async def run() -> dict[str, Any]:
            timeout = httpx.Timeout(
                self.settings.mcp_read_timeout_seconds,
                connect=self.settings.mcp_connect_timeout_seconds,
            )
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                async with streamable_http_client(
                    self.settings.kapruka_mcp_url,
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await asyncio.wait_for(
                            session.initialize(),
                            timeout=self.settings.mcp_read_timeout_seconds,
                        )
                        result = await session.call_tool(
                            tool_name,
                            arguments=arguments,
                            read_timeout_seconds=timedelta(
                                seconds=self.settings.mcp_read_timeout_seconds
                            ),
                        )

            if getattr(result, "isError", False):
                raise KaprukaMCPError(f"Kapruka MCP tool {tool_name} returned an error.")

            parsed = self._decode_result_envelope(self._extract_tool_result(result))
            return parsed if isinstance(parsed, dict) else {"data": parsed}

        return await self._with_total_timeout(run(), tool_name=tool_name)

    async def _with_total_timeout(self, awaitable: Any, tool_name: str = "MCP operation") -> Any:
        try:
            return await asyncio.wait_for(
                awaitable,
                timeout=self.settings.mcp_total_timeout_seconds,
            )
        except TimeoutError as exc:
            raise KaprukaMCPError(f"{tool_name} timed out while contacting Kapruka MCP.") from exc
        except httpx.HTTPError as exc:
            raise KaprukaMCPError(f"{tool_name} failed while contacting Kapruka MCP: {exc}") from exc
        except Exception as exc:
            if isinstance(exc, KaprukaMCPError):
                raise
            raise KaprukaMCPError(f"{tool_name} failed: {exc}") from exc

    def _extract_tool_result(self, result: Any) -> Any:
        structured = getattr(result, "structuredContent", None) or getattr(
            result,
            "structured_content",
            None,
        )
        if structured is not None:
            return self._to_python(structured)

        content = getattr(result, "content", None)
        if content is None:
            return self._to_python(result)

        parsed_items = [self._content_item_to_python(item) for item in content]
        if len(parsed_items) == 1:
            return parsed_items[0]
        return {"content": parsed_items}

    def _content_item_to_python(self, item: Any) -> Any:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            stripped = text.strip()
            if stripped:
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return stripped

        return self._to_python(item)

    def _decode_result_envelope(self, value: Any) -> Any:
        if isinstance(value, dict) and "result" in value:
            decoded = self._maybe_json(value["result"])
            if set(value.keys()) == {"result"}:
                return decoded
            value = value.copy()
            value["result"] = decoded
            return value
        return self._maybe_json(value)

    def _maybe_json(self, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
        return value

    def _to_python(self, value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json", by_alias=True)
        if isinstance(value, list):
            return [self._to_python(item) for item in value]
        if isinstance(value, dict):
            return {key: self._to_python(item) for key, item in value.items()}
        return value

    def normalize_products(self, payload: Any, currency: str = "LKR") -> list[ProductSummary]:
        items = self._find_list(payload, ("products", "items", "results", "data"))
        normalized: list[ProductSummary] = []

        for item in items:
            if not isinstance(item, dict):
                continue
            product_id = self._first_text(
                item,
                ("product_id", "id", "code", "sku", "item_code", "productCode"),
            )
            if not product_id:
                continue
            normalized.append(
                ProductSummary(
                    product_id=product_id,
                    name=self._first_text(item, ("name", "title", "product_name", "display_name")),
                    price=self._first_float(
                        item,
                        ("price", "unit_price", "sale_price", "current_price", "amount"),
                    ),
                    currency=self._product_currency(item, currency),
                    image_url=self._first_text(
                        item,
                        ("image_url", "image", "thumbnail", "thumbnail_url", "main_image"),
                    )
                    or self._first_from_list(item, ("images",)),
                    url=self._first_text(item, ("url", "product_url", "direct_url", "link")),
                    in_stock=self._first_bool(item, ("in_stock", "available", "stock")),
                    raw=item,
                )
            )

        return normalized

    def normalize_product(self, payload: Any, currency: str = "LKR") -> ProductSummary | None:
        product = payload.get("product", payload) if isinstance(payload, dict) else payload
        if isinstance(product, list) and product:
            product = product[0]
        if not isinstance(product, dict):
            return None
        products = self.normalize_products([product], currency=currency)
        return products[0] if products else None

    def _find_list(self, payload: Any, keys: tuple[str, ...]) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []

        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._find_list(value, keys)
                if nested:
                    return nested

        for value in payload.values():
            if isinstance(value, dict):
                nested = self._find_list(value, keys)
                if nested:
                    return nested

        return []

    def _first_text(self, item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if value is None:
                continue
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int | float):
                return str(value)
        return None

    def _first_float(self, item: dict[str, Any], keys: tuple[str, ...]) -> float | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, int | float):
                return float(value)
            if isinstance(value, dict):
                amount = value.get("amount")
                if isinstance(amount, int | float):
                    return float(amount)
                if isinstance(amount, str):
                    try:
                        return float(amount.replace(",", "").strip())
                    except ValueError:
                        continue
            if isinstance(value, str):
                cleaned = (
                    value.replace(",", "")
                    .replace("LKR", "")
                    .replace("Rs.", "")
                    .replace("Rs", "")
                    .strip()
                )
                try:
                    return float(cleaned)
                except ValueError:
                    continue
        return None

    def _product_currency(self, item: dict[str, Any], fallback: str) -> str:
        direct = self._first_text(item, ("currency",))
        if direct:
            return direct
        price = item.get("price")
        if isinstance(price, dict):
            currency = price.get("currency")
            if isinstance(currency, str) and currency.strip():
                return currency.strip()
        return fallback

    def _first_from_list(self, item: dict[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, list):
                for nested in value:
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
        return None

    def _first_bool(self, item: dict[str, Any], keys: tuple[str, ...]) -> bool | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, int):
                return value > 0
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"true", "yes", "available", "in stock", "instock"}:
                    return True
                if lowered in {"false", "no", "unavailable", "out of stock", "outofstock"}:
                    return False
        return None

    def _drop_none(self, values: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in values.items() if value is not None}

    def _tool_arguments(self, params: dict[str, Any]) -> dict[str, Any]:
        params = self._drop_none(params.copy())
        params.setdefault("response_format", "json")
        return {"params": params}
