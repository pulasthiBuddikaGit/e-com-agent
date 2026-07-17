export type Currency = "LKR" | "USD" | "AUD" | "CAD" | "EUR" | "GBP";

export interface UIBlock {
  type: string;
  data: Record<string, unknown>;
}

export interface ProductSummary {
  product_id: string;
  name?: string | null;
  price?: number | null;
  currency?: string;
  image_url?: string | null;
  url?: string | null;
  in_stock?: boolean | null;
  raw?: Record<string, unknown>;
}

export interface CartItem {
  product_id: string;
  quantity: number;
  name?: string | null;
  unit_price?: number | null;
  currency?: string;
  image_url?: string | null;
  url?: string | null;
  raw?: Record<string, unknown>;
}

export interface Cart {
  items: CartItem[];
  currency: string;
  estimated_total?: number | null;
}

export interface ChatResponse {
  session_id: string;
  message: string;
  blocks: UIBlock[];
  cart: Cart;
  model?: string | null;
  created_at: string;
}

export interface CartResponse {
  session_id: string;
  cart: Cart;
}

export interface ProductDetailResponse {
  product: Record<string, unknown>;
  normalized?: ProductSummary | null;
}

export interface CheckoutParty {
  name?: string;
  full_name?: string;
  phone?: string;
  email?: string;
  anonymous?: boolean;
}

export interface CheckoutDelivery {
  city: string;
  delivery_date: string;
  address?: string;
  address_line1?: string;
  address_line2?: string;
  location_type?: "house" | "apartment" | "office" | "other";
  instructions?: string;
}

export interface CheckoutPrepareResponse {
  session_id: string;
  ready: boolean;
  missing_fields: string[];
  warnings: string[];
  delivery_checks: Array<Record<string, unknown>>;
  cart: Cart;
}

export interface CheckoutCreateResponse {
  session_id: string;
  order: Record<string, unknown>;
  checkout_url?: string | null;
  expires_in_minutes: number;
  warnings: string[];
}

