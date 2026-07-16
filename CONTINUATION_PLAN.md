# Kapruka AI Shopping Agent Continuation Plan

## Current Project State

This repository is still at the early scaffold stage.

- `README.md` only contains the project name.
- `backend/app.py` is empty.
- `backend/requirements.txt` includes the right direction of dependencies: FastAPI, MCP client support, Google Gemini SDK, Pydantic, dotenv, Uvicorn, and related packages.
- `backend/test_mcp.py` is a standalone MCP connectivity probe for `https://mcp.kapruka.com/mcp`.
- `gemini-test/test.py` is a standalone Gemini API smoke test.
- `frontend/` exists but is empty. There is no React app yet.
- `backend/.env` and `gemini-test/.env` exist locally and should be treated as secret files.
- The local `backend/venv` can import `mcp`, `fastapi`, and `google-genai`, but the current MCP probe timed out during a live connection test and still needs proper timeout/error handling.

In practical terms, the project has proven dependency intent, but the actual shopping agent, backend API, frontend UI, and checkout flow have not been built yet.

## Product Goal

Build a Sri Lankan AI shopping agent for Kapruka that feels like a full-screen premium chat shopping experience. Customers should be able to describe what they need, compare live Kapruka products, check delivery availability, build a cart, create a guest checkout link, and track orders through a conversational interface.

## Kapruka MCP Capabilities To Integrate

The backend should wrap these tools behind safe internal service functions:

- `kapruka_search_products`: Search catalog by keyword, category, price range, stock, sort, pagination, and currency.
- `kapruka_get_product`: Fetch full product details by product ID.
- `kapruka_list_categories`: Fetch top-level category names and browse URLs.
- `kapruka_list_delivery_cities`: Search supported delivery cities by canonical name or alias.
- `kapruka_check_delivery`: Check city/date delivery availability, flat LKR rate, and perishable warnings.
- `kapruka_create_order`: Create a guest-checkout order and return a 60-minute click-to-pay URL.
- `kapruka_track_order`: Track an existing Kapruka order by order number.

Important operational limits:

- 60 requests per minute per client IP across all MCP tools.
- 30 `kapruka_create_order` calls per hour per client IP.
- Product and category reads may be cached server-side for up to 30 minutes.
- Write endpoints must not be cached.
- Checkout links lock prices for 60 minutes.

## Recommended Architecture

### Backend: Python FastAPI

Build `backend/app.py` into a real FastAPI application.

Core modules to add:

- `backend/main.py` or complete `backend/app.py`: FastAPI app entrypoint.
- `backend/config.py`: environment loading and settings.
- `backend/kapruka_mcp.py`: MCP client wrapper and typed tool calls.
- `backend/agent.py`: AI shopping agent orchestration.
- `backend/models.py`: Pydantic request/response models.
- `backend/session_store.py`: temporary in-memory chat/cart state for MVP.
- `backend/rate_limit.py`: lightweight client-side protection around MCP limits.

Recommended API surface:

- `GET /health`: backend health check.
- `POST /api/chat`: main chat endpoint.
- `POST /api/cart`: update cart explicitly from UI actions.
- `POST /api/checkout/prepare`: validate cart, recipient, sender, city, and date before checkout.
- `POST /api/checkout/create`: call `kapruka_create_order` only after explicit user confirmation.
- `GET /api/orders/{order_number}`: track order.
- `GET /api/categories`: optional category bootstrap for frontend browse suggestions.

For a richer UX, add streaming later with `WebSocket /ws/chat` or Server-Sent Events. For the first working version, a normal `POST /api/chat` endpoint is enough.

### Frontend: React

Create a React app inside `frontend/`, preferably with Vite.

Recommended stack:

- React + TypeScript.
- Vite.
- CSS modules or Tailwind CSS.
- `lucide-react` for icons.
- A small client API layer for backend calls.

Main UI:

- Full-screen chat layout, not a landing page.
- Left or top context area for active cart, delivery city/date, and checkout status.
- Main chat timeline with assistant responses, product cards, and checkout prompts.
- Product result cards with image, name, price, stock state, delivery hints, and actions.
- Cart drawer or side panel with quantity controls, remove actions, estimated total, and checkout readiness.
- Delivery form embedded naturally in the conversation.
- Order tracking view for users who already have an order number.

Design direction:

- Clean, premium, Sri Lanka-aware shopping assistant.
- Product images should be prominent.
- Use clear visual states: searching, checking delivery, ready to checkout, checkout link created, rate limited, unavailable.
- Avoid a marketing-style hero page. The first screen should be the usable chat shopping experience.

## Agent Behavior Requirements

The assistant should behave like a careful shopping concierge, not just a generic chatbot.

It should:

- Ask clarifying questions when the customer request is vague.
- Search Kapruka live inventory before recommending products.
- Prefer in-stock items when the user is ready to buy.
- Use `kapruka_get_product` before adding uncertain products to cart.
- Ask for delivery city and date before promising delivery.
- Call `kapruka_check_delivery` before checkout.
- Show perishable warnings for cakes, flowers, and combos.
- Collect recipient, delivery, sender, and gift message details before order creation.
- Require explicit user confirmation before calling `kapruka_create_order`.
- Explain that the payment link expires after 60 minutes.
- Track orders using `kapruka_track_order` when the user provides an order number.

It should not:

- Invent prices, stock, delivery availability, or checkout links.
- Call `kapruka_create_order` from casual conversation.
- Retry checkout creation aggressively if rate-limited.
- Store payment card details.

## Step-By-Step Continuation Plan

### Phase 1: Stabilize Environment

1. Keep `.env` files ignored and do not commit secrets.
2. Confirm which AI provider will power the agent. The current repo points to Gemini via `google-genai`.
3. Add a root-level `.env.example` documenting required variables, such as `GEMINI_API_KEY`, `KAPRUKA_MCP_URL`, and frontend/backend URLs.
4. Update `README.md` with setup commands for backend and frontend.
5. Add backend timeout handling so MCP connectivity failures fail fast and return useful errors.

### Phase 2: Build Kapruka MCP Service Layer

1. Create a reusable MCP client wrapper.
2. Add typed Python methods for each Kapruka MCP tool.
3. Normalize product, category, city, delivery, order, and rate-limit responses.
4. Add defensive timeouts, retries only for safe read operations, and clear error mapping.
5. Add lightweight caching for product/category reads if useful, while never caching checkout/order writes.
6. Add a small backend smoke test that lists categories and performs a harmless product search.

### Phase 3: Build Agent Orchestration

1. Define the system prompt and shopping policies.
2. Add conversation/session state: user messages, assistant messages, cart, selected city, delivery date, and checkout readiness.
3. Implement tool-routing between the AI model and Kapruka MCP tools.
4. Add deterministic guardrails for checkout:
   - cart must not be empty;
   - recipient details must be present;
   - sender details must be present;
   - delivery city/date must be validated;
   - user must explicitly confirm order creation.
5. Return structured UI blocks from the backend, not only plain text. Example block types: `message`, `product_grid`, `product_detail`, `cart`, `delivery_check`, `checkout_link`, `order_status`.

### Phase 4: Build React Chat Experience

1. Scaffold the React app in `frontend/`.
2. Create a full-screen responsive layout.
3. Implement chat timeline, composer, loading states, and error states.
4. Add product cards and product detail cards.
5. Add cart state UI and quantity controls.
6. Add delivery city/date inputs and checkout confirmation flow.
7. Add order tracking UI.
8. Connect the frontend to backend APIs.

### Phase 5: Checkout Flow

1. Convert cart UI state into the exact `kapruka_create_order` payload shape.
2. Validate recipient, delivery, sender, gift message, and currency.
3. Run `kapruka_check_delivery` for each relevant product/date/city combination before checkout.
4. Show all warnings before order creation.
5. Call `kapruka_create_order` only after explicit confirmation.
6. Display the returned click-to-pay URL clearly and explain the 60-minute price lock.
7. Save enough local session context to show the order number or checkout state after creation.

### Phase 6: Quality, Testing, And Polish

1. Add backend tests for MCP wrapper argument construction and checkout guardrails.
2. Add frontend component tests for product cards, cart controls, and checkout readiness.
3. Add Playwright end-to-end tests for:
   - search product;
   - view product details;
   - add to cart;
   - check delivery;
   - prepare checkout;
   - track order.
4. Test mobile, tablet, and desktop layouts.
5. Verify loading, empty, error, unavailable, and rate-limited states.
6. Add logging around MCP calls without logging secrets or private customer details.

## Immediate Next Tasks

Start here when continuing development:

1. Update `README.md` with setup/run instructions.
2. Add `.env.example`.
3. Turn `backend/app.py` into a FastAPI app with `/health`.
4. Create `backend/kapruka_mcp.py` and move the MCP connection logic out of `test_mcp.py`.
5. Add a backend endpoint that can call `kapruka_list_categories` or `kapruka_search_products`.
6. Scaffold the Vite React frontend in `frontend/`.
7. Build the full-screen chat shell and connect it to a temporary `/api/chat` response.
8. Replace the temporary chat response with the real agent and MCP tool-calling flow.

## Definition Of Done For MVP

The MVP is complete when a customer can:

1. Open the React app and immediately see a full-screen shopping chat.
2. Ask for a Sri Lankan gift, cake, flowers, grocery item, or other Kapruka product.
3. See live product suggestions with prices and images.
4. Open product details.
5. Add products to a cart.
6. Provide delivery city and date.
7. Receive a live delivery quote and warning if applicable.
8. Confirm recipient/sender/gift details.
9. Create a guest checkout link through Kapruka.
10. Track an order by order number.

## Key Risks

- MCP connectivity needs timeout and retry handling; the current probe can hang long enough to block development.
- Checkout creation is rate-limited and should be protected by explicit confirmation.
- Product and delivery data must always come from Kapruka MCP, not model guesses.
- The frontend should render structured backend responses so product cards and checkout links are reliable.
- Customer personal information must not be logged unnecessarily.

## Suggested Final Folder Shape

```text
kapruka-agent/
  README.md
  CONTINUATION_PLAN.md
  .env.example
  backend/
    app.py
    agent.py
    config.py
    kapruka_mcp.py
    models.py
    session_store.py
    requirements.txt
    tests/
  frontend/
    package.json
    vite.config.ts
    src/
      App.tsx
      main.tsx
      api/
      components/
      styles/
```

