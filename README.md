# Kapruka AI Shopping Agent

Sri Lankan AI shopping agent powered by Gemini 2.5 Flash and Kapruka MCP.

The backend is a FastAPI service that wraps live Kapruka MCP tools for product search, product details, delivery checks, guest checkout creation, and order tracking. The React frontend will consume these endpoints next.

## Backend Setup

From the repository root:

```powershell
python -m venv backend\venv
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
Copy-Item .env.example backend\.env
```

Edit `backend\.env` and set:

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
KAPRUKA_MCP_URL=https://mcp.kapruka.com/mcp
```

Run the backend:

```powershell
.\backend\venv\Scripts\python.exe -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

Open:

- API docs: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

## Backend Endpoints

- `GET /health`
- `GET /api/mcp/tools`
- `POST /api/chat`
- `GET /api/categories`
- `POST /api/products/search`
- `GET /api/products/{product_id}`
- `GET /api/delivery/cities`
- `POST /api/delivery/check`
- `POST /api/cart`
- `POST /api/checkout/prepare`
- `POST /api/checkout/create`
- `GET /api/orders/{order_number}`

`POST /api/checkout/create` requires `confirm: true`, a non-empty cart, recipient details, sender details, delivery details, and a live delivery preflight check before calling `kapruka_create_order`.

## Backend Checks

```powershell
.\backend\venv\Scripts\python.exe -m compileall backend -x "backend\\venv"
.\backend\venv\Scripts\python.exe -m unittest discover backend\tests
```

Optional live MCP probe:

```powershell
.\backend\venv\Scripts\python.exe -m backend.test_mcp
```

## Frontend

The frontend is a Vite React app connected to the FastAPI backend.

```powershell
cd frontend
npm install
npm run dev
```

By default it calls `http://127.0.0.1:8000`. To point it somewhere else:

```powershell
Copy-Item .env.example .env
```

Then edit `frontend\.env`:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Production build:

```powershell
cd frontend
npm run build
```
