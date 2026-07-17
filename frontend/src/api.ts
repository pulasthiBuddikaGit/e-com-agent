import type {
  CartResponse,
  ChatResponse,
  CheckoutCreateResponse,
  CheckoutDelivery,
  CheckoutParty,
  CheckoutPrepareResponse,
  Currency,
  ProductDetailResponse,
  ProductSummary
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || "Request failed");
  }

  return response.json() as Promise<T>;
}

export const api = {
  baseUrl: API_BASE_URL,

  chat(message: string, sessionId: string | null, currency: Currency) {
    return request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        currency
      })
    });
  },

  addToCart(
    sessionId: string | null,
    product: ProductSummary,
    quantity = 1,
    currency: Currency = "LKR"
  ) {
    return request<CartResponse>("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        action: "add",
        product_id: product.product_id,
        quantity,
        product,
        currency
      })
    });
  },

  updateCart(sessionId: string, productId: string, quantity: number, currency: Currency) {
    return request<CartResponse>("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        action: "update",
        product_id: productId,
        quantity,
        currency
      })
    });
  },

  removeFromCart(sessionId: string, productId: string, currency: Currency) {
    return request<CartResponse>("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        action: "remove",
        product_id: productId,
        currency
      })
    });
  },

  clearCart(sessionId: string, currency: Currency) {
    return request<CartResponse>("/api/cart", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        action: "clear",
        currency
      })
    });
  },

  product(productId: string, currency: Currency) {
    return request<ProductDetailResponse>(
      `/api/products/${encodeURIComponent(productId)}?currency=${encodeURIComponent(currency)}`
    );
  },

  checkDelivery(city: string, deliveryDate: string, productId?: string) {
    return request<Record<string, unknown>>("/api/delivery/check", {
      method: "POST",
      body: JSON.stringify({
        city,
        delivery_date: deliveryDate,
        product_id: productId || undefined
      })
    });
  },

  prepareCheckout(
    sessionId: string,
    recipient: CheckoutParty,
    delivery: CheckoutDelivery,
    sender: CheckoutParty,
    giftMessage: string,
    currency: Currency
  ) {
    return request<CheckoutPrepareResponse>("/api/checkout/prepare", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        recipient,
        delivery,
        sender,
        gift_message: giftMessage || undefined,
        currency
      })
    });
  },

  createCheckout(
    sessionId: string,
    recipient: CheckoutParty,
    delivery: CheckoutDelivery,
    sender: CheckoutParty,
    giftMessage: string,
    currency: Currency
  ) {
    return request<CheckoutCreateResponse>("/api/checkout/create", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        confirm: true,
        recipient,
        delivery,
        sender,
        gift_message: giftMessage || undefined,
        currency
      })
    });
  },

  trackOrder(orderNumber: string) {
    return request<Record<string, unknown>>(`/api/orders/${encodeURIComponent(orderNumber)}`);
  }
};

