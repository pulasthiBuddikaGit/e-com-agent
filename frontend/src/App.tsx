import {
  FormEvent,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  Eye,
  Loader2,
  Minus,
  PackageSearch,
  Plus,
  Search,
  Send,
  ShoppingBag,
  Sparkles,
  Trash2,
  Truck,
  X
} from "lucide-react";
import { api } from "./api";
import type {
  Cart,
  CartItem,
  CheckoutCreateResponse,
  CheckoutDelivery,
  CheckoutParty,
  CheckoutPrepareResponse,
  Currency,
  ProductDetailResponse,
  ProductSummary,
  UIBlock
} from "./types";

type ChatRole = "assistant" | "user";
type SideTab = "cart" | "delivery" | "track";

interface ChatEntry {
  id: string;
  role: ChatRole;
  content: string;
  blocks?: UIBlock[];
}

const emptyCart: Cart = {
  items: [],
  currency: "LKR",
  estimated_total: null
};

const promptChips = [
  "Find a birthday cake for Colombo under 8000",
  "Show me flower gifts available in Sri Lanka",
  "Tea gifts under 5000 rupees",
  "Track my Kapruka order"
];

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function nextId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | null>(() =>
    localStorage.getItem("kapruka_session_id")
  );
  const [currency, setCurrency] = useState<Currency>("LKR");
  const [messages, setMessages] = useState<ChatEntry[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "What would you like to send from Kapruka today?"
    }
  ]);
  const [cart, setCart] = useState<Cart>(emptyCart);
  const [message, setMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [busyProductId, setBusyProductId] = useState<string | null>(null);
  const [sideTab, setSideTab] = useState<SideTab>("cart");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProductDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [recipient, setRecipient] = useState<CheckoutParty>({
    name: "",
    phone: ""
  });
  const [sender, setSender] = useState<CheckoutParty>({
    name: "",
    phone: "",
    anonymous: false
  });
  const [delivery, setDelivery] = useState<CheckoutDelivery>({
    city: "Colombo 03",
    delivery_date: todayIso(),
    address: "",
    location_type: "house",
    instructions: ""
  });
  const [giftMessage, setGiftMessage] = useState("");
  const [deliveryResult, setDeliveryResult] = useState<Record<string, unknown> | null>(null);
  const [prepareResult, setPrepareResult] = useState<CheckoutPrepareResponse | null>(null);
  const [checkoutResult, setCheckoutResult] = useState<CheckoutCreateResponse | null>(null);
  const [checkoutBusy, setCheckoutBusy] = useState(false);
  const [orderNumber, setOrderNumber] = useState("");
  const [trackingResult, setTrackingResult] = useState<Record<string, unknown> | null>(null);
  const [trackingBusy, setTrackingBusy] = useState(false);

  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth"
    });
  }, [messages, isSending]);

  const cartCount = useMemo(
    () => cart.items.reduce((total, item) => total + item.quantity, 0),
    [cart.items]
  );

  function syncSession(id: string) {
    setSessionId(id);
    localStorage.setItem("kapruka_session_id", id);
  }

  async function sendChat(text: string) {
    const trimmed = text.trim();
    if (!trimmed || isSending) {
      return;
    }

    setError(null);
    setNotice(null);
    setMessage("");
    setMessages((current) => [
      ...current,
      {
        id: nextId("user"),
        role: "user",
        content: trimmed
      }
    ]);
    setIsSending(true);

    try {
      const response = await api.chat(trimmed, sessionId, currency);
      syncSession(response.session_id);
      setCart(response.cart);
      setMessages((current) => [
        ...current,
        {
          id: nextId("assistant"),
          role: "assistant",
          content: response.message,
          blocks: response.blocks
        }
      ]);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "The backend request failed.";
      setError(detail);
      setMessages((current) => [
        ...current,
        {
          id: nextId("assistant"),
          role: "assistant",
          content: "I could not complete that request. Check the backend and try again."
        }
      ]);
    } finally {
      setIsSending(false);
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await sendChat(message);
  }

  async function handleAddProduct(product: ProductSummary) {
    setBusyProductId(product.product_id);
    setError(null);
    setNotice(null);

    try {
      const response = await api.addToCart(sessionId, product, 1, currency);
      syncSession(response.session_id);
      setCart(response.cart);
      setSideTab("cart");
      setNotice(`${product.name ?? product.product_id} was added to your cart.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add product to cart.");
    } finally {
      setBusyProductId(null);
    }
  }

  async function updateQuantity(item: CartItem, quantity: number) {
    if (!sessionId) {
      return;
    }
    const safeQuantity = Math.max(1, quantity);
    const response = await api.updateCart(sessionId, item.product_id, safeQuantity, currency);
    setCart(response.cart);
  }

  async function removeItem(item: CartItem) {
    if (!sessionId) {
      return;
    }
    const response = await api.removeFromCart(sessionId, item.product_id, currency);
    setCart(response.cart);
  }

  async function clearCart() {
    if (!sessionId) {
      return;
    }
    const response = await api.clearCart(sessionId, currency);
    setCart(response.cart);
    setCheckoutResult(null);
    setPrepareResult(null);
  }

  async function openProduct(product: ProductSummary) {
    setDetail(null);
    setDetailLoading(true);
    setError(null);
    try {
      const response = await api.product(product.product_id, currency);
      setDetail(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load product details.");
    } finally {
      setDetailLoading(false);
    }
  }

  async function checkDelivery() {
    setCheckoutBusy(true);
    setError(null);
    setDeliveryResult(null);
    try {
      const productId = cart.items[0]?.product_id;
      const response = await api.checkDelivery(
        delivery.city,
        delivery.delivery_date,
        productId
      );
      setDeliveryResult(response);
      setSideTab("delivery");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not check delivery.");
    } finally {
      setCheckoutBusy(false);
    }
  }

  async function prepareCheckout() {
    if (!sessionId) {
      setError("Add a product before preparing checkout.");
      return;
    }
    setCheckoutBusy(true);
    setError(null);
    setPrepareResult(null);
    setCheckoutResult(null);

    try {
      const response = await api.prepareCheckout(
        sessionId,
        recipient,
        delivery,
        sender,
        giftMessage,
        currency
      );
      setPrepareResult(response);
      setCart(response.cart);
      setNotice(
        response.ready
          ? "Checkout is ready for final confirmation."
          : "Checkout details still need attention."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not prepare checkout.");
    } finally {
      setCheckoutBusy(false);
    }
  }

  async function createCheckout() {
    if (!sessionId) {
      setError("Add a product before creating checkout.");
      return;
    }
    setCheckoutBusy(true);
    setError(null);
    setCheckoutResult(null);

    try {
      const response = await api.createCheckout(
        sessionId,
        recipient,
        delivery,
        sender,
        giftMessage,
        currency
      );
      setCheckoutResult(response);
      setNotice("Kapruka checkout link created. The price lock lasts 60 minutes.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create checkout.");
    } finally {
      setCheckoutBusy(false);
    }
  }

  async function trackOrder(event: FormEvent) {
    event.preventDefault();
    if (!orderNumber.trim()) {
      return;
    }
    setTrackingBusy(true);
    setTrackingResult(null);
    setError(null);

    try {
      setTrackingResult(await api.trackOrder(orderNumber.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not track order.");
    } finally {
      setTrackingBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <section className="chat-surface">
        <header className="topbar">
          <div className="brand-mark" aria-hidden="true">
            <ShoppingBag size={25} />
          </div>
          <div className="brand-copy">
            <h1>Kapruka AI Shopper</h1>
            <div className="status-line">
              <span className="status-dot" />
              <span>Live catalog, delivery, checkout</span>
            </div>
          </div>
          <div className="topbar-actions">
            <select
              aria-label="Currency"
              value={currency}
              onChange={(event) => setCurrency(event.target.value as Currency)}
            >
              <option value="LKR">LKR</option>
              <option value="USD">USD</option>
              <option value="GBP">GBP</option>
              <option value="AUD">AUD</option>
              <option value="CAD">CAD</option>
              <option value="EUR">EUR</option>
            </select>
            <button
              className="icon-button"
              title="Open cart"
              type="button"
              onClick={() => setSideTab("cart")}
            >
              <ShoppingBag size={18} />
              <span>{cartCount}</span>
            </button>
          </div>
        </header>

        <div className="prompt-strip">
          {promptChips.map((chip) => (
            <button
              type="button"
              key={chip}
              className="prompt-chip"
              onClick={() => sendChat(chip)}
              disabled={isSending}
            >
              <Sparkles size={14} />
              <span>{chip}</span>
            </button>
          ))}
        </div>

        {notice && (
          <div className="notice-bar success">
            <CheckCircle2 size={18} />
            <span>{notice}</span>
          </div>
        )}
        {error && (
          <div className="notice-bar danger">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        <div className="transcript" ref={transcriptRef}>
          {messages.map((entry) => (
            <article className={`message-row ${entry.role}`} key={entry.id}>
              <div className="avatar" aria-hidden="true">
                {entry.role === "assistant" ? <Bot size={18} /> : "You"}
              </div>
              <div className="bubble">
                <p>{entry.content}</p>
                {entry.blocks?.map((block, index) => (
                  <MessageBlock
                    key={`${entry.id}-${block.type}-${index}`}
                    block={block}
                    busyProductId={busyProductId}
                    onAddProduct={handleAddProduct}
                    onOpenProduct={openProduct}
                  />
                ))}
              </div>
            </article>
          ))}

          {isSending && (
            <article className="message-row assistant">
              <div className="avatar" aria-hidden="true">
                <Bot size={18} />
              </div>
              <div className="bubble loading-bubble">
                <Loader2 className="spin" size={18} />
                <span>Checking Kapruka live data</span>
              </div>
            </article>
          )}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <Search size={20} aria-hidden="true" />
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Search gifts, cakes, flowers, groceries, or track an order"
          />
          <button type="submit" disabled={!message.trim() || isSending} title="Send">
            {isSending ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            <span>Send</span>
          </button>
        </form>
      </section>

      <aside className="action-rail">
        <div className="rail-tabs" role="tablist" aria-label="Shopping actions">
          <button
            type="button"
            className={sideTab === "cart" ? "active" : ""}
            onClick={() => setSideTab("cart")}
          >
            <ShoppingBag size={17} />
            <span>Cart</span>
          </button>
          <button
            type="button"
            className={sideTab === "delivery" ? "active" : ""}
            onClick={() => setSideTab("delivery")}
          >
            <Truck size={17} />
            <span>Checkout</span>
          </button>
          <button
            type="button"
            className={sideTab === "track" ? "active" : ""}
            onClick={() => setSideTab("track")}
          >
            <PackageSearch size={17} />
            <span>Track</span>
          </button>
        </div>

        {sideTab === "cart" && (
          <CartPanel
            cart={cart}
            currency={currency}
            onUpdateQuantity={updateQuantity}
            onRemove={removeItem}
            onClear={clearCart}
            onCheckout={() => setSideTab("delivery")}
          />
        )}

        {sideTab === "delivery" && (
          <CheckoutPanel
            cart={cart}
            recipient={recipient}
            sender={sender}
            delivery={delivery}
            giftMessage={giftMessage}
            deliveryResult={deliveryResult}
            prepareResult={prepareResult}
            checkoutResult={checkoutResult}
            busy={checkoutBusy}
            onRecipientChange={setRecipient}
            onSenderChange={setSender}
            onDeliveryChange={setDelivery}
            onGiftMessageChange={setGiftMessage}
            onCheckDelivery={checkDelivery}
            onPrepare={prepareCheckout}
            onCreate={createCheckout}
          />
        )}

        {sideTab === "track" && (
          <TrackPanel
            orderNumber={orderNumber}
            result={trackingResult}
            busy={trackingBusy}
            onOrderNumberChange={setOrderNumber}
            onTrack={trackOrder}
          />
        )}
      </aside>

      {(detail || detailLoading) && (
        <ProductModal
          detail={detail}
          loading={detailLoading}
          currency={currency}
          onClose={() => {
            setDetail(null);
            setDetailLoading(false);
          }}
          onAddProduct={(product) => handleAddProduct(product)}
        />
      )}
    </main>
  );
}

function MessageBlock({
  block,
  busyProductId,
  onAddProduct,
  onOpenProduct
}: {
  block: UIBlock;
  busyProductId: string | null;
  onAddProduct: (product: ProductSummary) => void;
  onOpenProduct: (product: ProductSummary) => void;
}) {
  if (block.type === "product_grid") {
    const products = readProducts(block);
    return (
      <div className="product-grid-shell">
        <div className="product-grid">
          {products.map((product) => (
            <ProductCard
              key={product.product_id}
              product={product}
              busy={busyProductId === product.product_id}
              onAdd={() => onAddProduct(product)}
              onOpen={() => onOpenProduct(product)}
            />
          ))}
        </div>
      </div>
    );
  }

  if (block.type === "delivery_check") {
    return <DataBlock title="Delivery result" payload={block.data} />;
  }

  if (block.type === "cart") {
    return <DataBlock title="Cart updated" payload={block.data} />;
  }

  if (block.type === "order_status") {
    return <DataBlock title="Order status" payload={block.data} />;
  }

  if (block.type === "error") {
    return <DataBlock title="Backend detail" payload={block.data} tone="danger" />;
  }

  return null;
}

function ProductCard({
  product,
  busy,
  onAdd,
  onOpen
}: {
  product: ProductSummary;
  busy: boolean;
  onAdd: () => void;
  onOpen: () => void;
}) {
  return (
    <article className="product-card">
      <div className="product-image-wrap">
        {product.image_url ? (
          <img src={product.image_url} alt={product.name ?? "Kapruka product"} />
        ) : (
          <div className="image-fallback">
            <ShoppingBag size={26} />
          </div>
        )}
      </div>
      <div className="product-card-body">
        <h3>{product.name ?? product.product_id}</h3>
        <div className="product-meta">
          <strong>{formatMoney(product.price, product.currency ?? "LKR")}</strong>
          <span className={product.in_stock === false ? "stock out" : "stock"}>
            {product.in_stock === false ? "Out of stock" : "In stock"}
          </span>
        </div>
      </div>
      <div className="product-actions">
        <button type="button" className="ghost-button" onClick={onOpen} title="View details">
          <Eye size={16} />
          <span>Details</span>
        </button>
        <button
          type="button"
          className="primary-button"
          onClick={onAdd}
          disabled={busy || product.in_stock === false}
          title="Add to cart"
        >
          {busy ? <Loader2 className="spin" size={16} /> : <Plus size={16} />}
          <span>Add</span>
        </button>
      </div>
    </article>
  );
}

function CartPanel({
  cart,
  currency,
  onUpdateQuantity,
  onRemove,
  onClear,
  onCheckout
}: {
  cart: Cart;
  currency: Currency;
  onUpdateQuantity: (item: CartItem, quantity: number) => void;
  onRemove: (item: CartItem) => void;
  onClear: () => void;
  onCheckout: () => void;
}) {
  return (
    <div className="rail-panel">
      <div className="rail-heading">
        <div>
          <p className="eyebrow">Current order</p>
          <h2>Your cart</h2>
        </div>
        {cart.items.length > 0 && (
          <button type="button" className="icon-button quiet" onClick={onClear} title="Clear cart">
            <Trash2 size={17} />
          </button>
        )}
      </div>

      {cart.items.length === 0 ? (
        <div className="empty-state">
          <ShoppingBag size={28} />
          <p>Your selected Kapruka products will appear here.</p>
        </div>
      ) : (
        <div className="cart-list">
          {cart.items.map((item) => (
            <div className="cart-line" key={item.product_id}>
              <div className="cart-thumb">
                {item.image_url ? <img src={item.image_url} alt={item.name ?? item.product_id} /> : null}
              </div>
              <div className="cart-line-main">
                <h3>{item.name ?? item.product_id}</h3>
                <p>{formatMoney(item.unit_price, item.currency ?? currency)}</p>
                <div className="quantity-control">
                  <button
                    type="button"
                    title="Decrease quantity"
                    onClick={() => onUpdateQuantity(item, item.quantity - 1)}
                    disabled={item.quantity <= 1}
                  >
                    <Minus size={14} />
                  </button>
                  <span>{item.quantity}</span>
                  <button
                    type="button"
                    title="Increase quantity"
                    onClick={() => onUpdateQuantity(item, item.quantity + 1)}
                  >
                    <Plus size={14} />
                  </button>
                  <button type="button" title="Remove item" onClick={() => onRemove(item)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="cart-total">
        <span>Estimated total</span>
        <strong>{formatMoney(cart.estimated_total, cart.currency ?? currency)}</strong>
      </div>

      <button
        type="button"
        className="checkout-button"
        onClick={onCheckout}
        disabled={cart.items.length === 0}
      >
        <CreditCard size={18} />
        <span>Delivery and checkout</span>
      </button>
    </div>
  );
}

function CheckoutPanel({
  cart,
  recipient,
  sender,
  delivery,
  giftMessage,
  deliveryResult,
  prepareResult,
  checkoutResult,
  busy,
  onRecipientChange,
  onSenderChange,
  onDeliveryChange,
  onGiftMessageChange,
  onCheckDelivery,
  onPrepare,
  onCreate
}: {
  cart: Cart;
  recipient: CheckoutParty;
  sender: CheckoutParty;
  delivery: CheckoutDelivery;
  giftMessage: string;
  deliveryResult: Record<string, unknown> | null;
  prepareResult: CheckoutPrepareResponse | null;
  checkoutResult: CheckoutCreateResponse | null;
  busy: boolean;
  onRecipientChange: (value: CheckoutParty) => void;
  onSenderChange: (value: CheckoutParty) => void;
  onDeliveryChange: (value: CheckoutDelivery) => void;
  onGiftMessageChange: (value: string) => void;
  onCheckDelivery: () => void;
  onPrepare: () => void;
  onCreate: () => void;
}) {
  return (
    <div className="rail-panel">
      <div className="rail-heading">
        <div>
          <p className="eyebrow">Guest checkout</p>
          <h2>Delivery details</h2>
        </div>
      </div>

      <fieldset className="form-section">
        <legend>Recipient</legend>
        <label>
          Name
          <input
            value={recipient.name ?? ""}
            onChange={(event) => onRecipientChange({ ...recipient, name: event.target.value })}
            placeholder="Recipient name"
          />
        </label>
        <label>
          Phone
          <input
            value={recipient.phone ?? ""}
            onChange={(event) => onRecipientChange({ ...recipient, phone: event.target.value })}
            placeholder="0771234567"
          />
        </label>
      </fieldset>

      <fieldset className="form-section">
        <legend>Delivery</legend>
        <label>
          City
          <input
            value={delivery.city}
            onChange={(event) => onDeliveryChange({ ...delivery, city: event.target.value })}
            placeholder="Colombo 03"
          />
        </label>
        <label>
          Date
          <input
            type="date"
            value={delivery.delivery_date}
            onChange={(event) =>
              onDeliveryChange({ ...delivery, delivery_date: event.target.value })
            }
          />
        </label>
        <label>
          Address
          <textarea
            value={delivery.address ?? ""}
            onChange={(event) => onDeliveryChange({ ...delivery, address: event.target.value })}
            placeholder="Street address"
            rows={3}
          />
        </label>
        <label>
          Location type
          <select
            value={delivery.location_type ?? "house"}
            onChange={(event) =>
              onDeliveryChange({
                ...delivery,
                location_type: event.target.value as CheckoutDelivery["location_type"]
              })
            }
          >
            <option value="house">House</option>
            <option value="apartment">Apartment</option>
            <option value="office">Office</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Instructions
          <textarea
            value={delivery.instructions ?? ""}
            onChange={(event) =>
              onDeliveryChange({ ...delivery, instructions: event.target.value })
            }
            placeholder="Gate code, landmark, preferred time"
            rows={2}
          />
        </label>
      </fieldset>

      <fieldset className="form-section">
        <legend>Sender</legend>
        <label>
          Name
          <input
            value={sender.name ?? ""}
            onChange={(event) => onSenderChange({ ...sender, name: event.target.value })}
            placeholder="Sender name"
          />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={Boolean(sender.anonymous)}
            onChange={(event) => onSenderChange({ ...sender, anonymous: event.target.checked })}
          />
          Send as anonymous
        </label>
        <label>
          Gift message
          <textarea
            value={giftMessage}
            onChange={(event) => onGiftMessageChange(event.target.value)}
            placeholder="Your message"
            rows={3}
            maxLength={300}
          />
        </label>
      </fieldset>

      <div className="checkout-actions">
        <button
          type="button"
          className="ghost-button wide"
          disabled={busy || cart.items.length === 0}
          onClick={onCheckDelivery}
        >
          {busy ? <Loader2 className="spin" size={16} /> : <Truck size={16} />}
          <span>Check delivery</span>
        </button>
        <button
          type="button"
          className="primary-button wide"
          disabled={busy || cart.items.length === 0}
          onClick={onPrepare}
        >
          {busy ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
          <span>Prepare checkout</span>
        </button>
      </div>

      {deliveryResult && <DataBlock title="Delivery quote" payload={deliveryResult} />}

      {prepareResult && (
        <div className={`checkout-status ${prepareResult.ready ? "ready" : "needs-work"}`}>
          <div>
            <strong>{prepareResult.ready ? "Ready for payment link" : "Needs attention"}</strong>
            <p>
              {prepareResult.ready
                ? "Delivery is checked and the required checkout fields are present."
                : "Complete the missing fields before creating the payment link."}
            </p>
          </div>
          {prepareResult.missing_fields.length > 0 && (
            <div className="missing-list">
              {prepareResult.missing_fields.map((field) => (
                <span key={field}>{field}</span>
              ))}
            </div>
          )}
          {prepareResult.warnings.length > 0 && (
            <div className="warning-list">
              {prepareResult.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
        </div>
      )}

      <button
        type="button"
        className="checkout-button"
        disabled={busy || !prepareResult?.ready}
        onClick={onCreate}
      >
        {busy ? <Loader2 className="spin" size={18} /> : <CreditCard size={18} />}
        <span>Create payment link</span>
      </button>

      {checkoutResult && (
        <div className="payment-link">
          <CheckCircle2 size={20} />
          <div>
            <strong>Payment link ready</strong>
            <p>Prices are locked for {checkoutResult.expires_in_minutes} minutes.</p>
            {checkoutResult.checkout_url ? (
              <a href={checkoutResult.checkout_url} target="_blank" rel="noreferrer">
                Open Kapruka checkout
                <ExternalLink size={15} />
              </a>
            ) : (
              <DataBlock title="Order response" payload={checkoutResult.order} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function TrackPanel({
  orderNumber,
  result,
  busy,
  onOrderNumberChange,
  onTrack
}: {
  orderNumber: string;
  result: Record<string, unknown> | null;
  busy: boolean;
  onOrderNumberChange: (value: string) => void;
  onTrack: (event: FormEvent) => void;
}) {
  return (
    <div className="rail-panel">
      <div className="rail-heading">
        <div>
          <p className="eyebrow">Order status</p>
          <h2>Track delivery</h2>
        </div>
      </div>
      <form className="track-form" onSubmit={onTrack}>
        <label>
          Order number
          <input
            value={orderNumber}
            onChange={(event) => onOrderNumberChange(event.target.value)}
            placeholder="VIMP34456CB2"
          />
        </label>
        <button type="submit" className="primary-button wide" disabled={!orderNumber.trim() || busy}>
          {busy ? <Loader2 className="spin" size={16} /> : <PackageSearch size={16} />}
          <span>Track order</span>
        </button>
      </form>
      {result && <DataBlock title="Latest Kapruka status" payload={result} />}
    </div>
  );
}

function ProductModal({
  detail,
  loading,
  currency,
  onClose,
  onAddProduct
}: {
  detail: ProductDetailResponse | null;
  loading: boolean;
  currency: Currency;
  onClose: () => void;
  onAddProduct: (product: ProductSummary) => void;
}) {
  const normalized = detail?.normalized ?? normalizeDetailProduct(detail?.product, currency);
  const raw = normalized?.raw ?? detail?.product ?? {};
  const description = pickText(raw, ["description", "summary"]);
  const images = productImages(raw, normalized);
  const category = categoryName(raw);

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="product-modal">
        <button type="button" className="close-button" onClick={onClose} title="Close">
          <X size={18} />
        </button>
        {loading ? (
          <div className="modal-loading">
            <Loader2 className="spin" size={24} />
            <span>Loading live product details</span>
          </div>
        ) : normalized ? (
          <>
            <div className="modal-gallery">
              {images[0] ? (
                <img src={images[0]} alt={normalized.name ?? normalized.product_id} />
              ) : (
                <div className="image-fallback">
                  <ShoppingBag size={36} />
                </div>
              )}
            </div>
            <div className="modal-copy">
              <p className="eyebrow">{category ?? normalized.product_id}</p>
              <h2>{normalized.name ?? normalized.product_id}</h2>
              <div className="modal-price-row">
                <strong>{formatMoney(normalized.price, normalized.currency ?? currency)}</strong>
                <span className={normalized.in_stock === false ? "stock out" : "stock"}>
                  {normalized.in_stock === false ? "Out of stock" : "In stock"}
                </span>
              </div>
              {description && <p className="description">{description}</p>}
              <div className="modal-actions">
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => onAddProduct(normalized)}
                  disabled={normalized.in_stock === false}
                >
                  <Plus size={16} />
                  <span>Add to cart</span>
                </button>
                {normalized.url && (
                  <a className="ghost-link" href={normalized.url} target="_blank" rel="noreferrer">
                    Kapruka page
                    <ExternalLink size={15} />
                  </a>
                )}
              </div>
            </div>
          </>
        ) : (
          <div className="modal-loading">
            <AlertCircle size={24} />
            <span>Product details are unavailable.</span>
          </div>
        )}
      </div>
    </div>
  );
}

function DataBlock({
  title,
  payload,
  tone = "neutral"
}: {
  title: string;
  payload: unknown;
  tone?: "neutral" | "danger";
}) {
  return (
    <div className={`data-block ${tone}`}>
      <strong>{title}</strong>
      <pre>{JSON.stringify(payload, null, 2)}</pre>
    </div>
  );
}

function readProducts(block: UIBlock): ProductSummary[] {
  const products = block.data.products;
  if (!Array.isArray(products)) {
    return [];
  }
  return products.filter(isProductSummary);
}

function isProductSummary(value: unknown): value is ProductSummary {
  return (
    isRecord(value) &&
    typeof value.product_id === "string" &&
    value.product_id.trim().length > 0
  );
}

function normalizeDetailProduct(
  payload: Record<string, unknown> | undefined,
  currency: Currency
): ProductSummary | null {
  if (!payload) {
    return null;
  }
  const source = isRecord(payload.product) ? payload.product : payload;
  const productId = pickText(source, ["product_id", "id", "code", "sku"]);
  if (!productId) {
    return null;
  }
  return {
    product_id: productId,
    name: pickText(source, ["name", "title", "product_name"]),
    price: pickNumber(source, ["price", "amount"]),
    currency: productCurrency(source) ?? currency,
    image_url: productImages(source, null)[0] ?? null,
    url: pickText(source, ["url", "product_url", "direct_url"]),
    in_stock: pickBoolean(source, ["in_stock", "available"]),
    raw: source
  };
}

function productImages(raw: Record<string, unknown>, normalized?: ProductSummary | null) {
  const images = raw.images;
  if (Array.isArray(images)) {
    return images.filter((value): value is string => typeof value === "string" && value.length > 0);
  }
  const single =
    normalized?.image_url ??
    pickText(raw, ["image_url", "image", "thumbnail", "thumbnail_url", "main_image"]);
  return single ? [single] : [];
}

function categoryName(raw: Record<string, unknown>) {
  const category = raw.category;
  if (isRecord(category)) {
    return pickText(category, ["name", "title", "slug"]);
  }
  return typeof category === "string" ? category : null;
}

function productCurrency(raw: Record<string, unknown>) {
  const direct = pickText(raw, ["currency"]);
  if (direct) {
    return direct;
  }
  const price = raw.price;
  if (isRecord(price)) {
    return pickText(price, ["currency"]);
  }
  return null;
}

function pickText(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof value === "number") {
      return String(value);
    }
  }
  return null;
}

function pickNumber(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "number") {
      return value;
    }
    if (isRecord(value)) {
      const amount = value.amount;
      if (typeof amount === "number") {
        return amount;
      }
    }
    if (typeof value === "string") {
      const parsed = Number(value.replace(/[^0-9.]/g, ""));
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
  }
  return null;
}

function pickBoolean(source: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatMoney(value: number | null | undefined, currency: string) {
  if (typeof value !== "number") {
    return "Price on request";
  }
  try {
    return new Intl.NumberFormat("en-LK", {
      style: "currency",
      currency,
      maximumFractionDigits: 0
    }).format(value);
  } catch {
    return `${currency} ${value.toLocaleString("en-LK")}`;
  }
}

