# Autonomous Sourcing Copilot

## Overview

The Autonomous Sourcing Copilot is a FastAPI-based AI orchestration backend that takes a natural language part request from an engineer inside a CAD environment (FreeCAD or Onshape), parses it into structured engineering constraints using Claude Haiku, scrapes live supplier websites (McMaster-Carr, Misumi) using AgentQL to find and extract a matching part's pricing, lead time, and CAD file URL, logs the transaction to a Google Sheets BOM for the procurement team, and injects the STEP geometry directly back into the engineer's active workspace — falling back to a simulated Virtual OEM (Xometry) quote if no supplier can fulfil the request within the required lead time.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Create a `.env` file

Copy the template below into a file named `.env` in the `sourcing_copilot/` directory and fill in your values:

```env
# Required
ANTHROPIC_API_KEY=sk-ant-...
AGENTQL_API_KEY=...

# Optional — BOM logging is disabled if either value is missing
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json
BOM_SHEET_ID=your_google_sheet_id_here

# Optional — sourcing behaviour overrides
MAX_LEAD_TIME_DAYS=28
DEFAULT_SUPPLIER=mcmaster

# Optional — logging verbosity (DEBUG | INFO | WARNING | ERROR)
LOG_LEVEL=INFO
```

---

## Running

```bash
cd sourcing_copilot
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## Example Request

```bash
curl -X POST http://localhost:8000/source \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "ws-abc123",
    "natural_language_query": "NEMA 17 stepper motor, 24V, under $40, max 2 week lead time",
    "cad_platform": "freecad"
  }'
```

Example response:

```json
{
  "workspace_id": "ws-abc123",
  "constraints": {
    "part_type": "NEMA 17 stepper motor",
    "voltage_v": 24.0,
    "torque_nm": null,
    "max_price_usd": 40.0,
    "max_lead_time_days": 14,
    "additional": {}
  },
  "result": {
    "sku": "6627K51",
    "name": "NEMA 17 Stepper Motor 24V",
    "price_usd": 34.17,
    "lead_time_days": 1,
    "supplier": "McMaster-Carr",
    "step_file_url": "https://www.mcmaster.com/cad/...",
    "product_url": "https://www.mcmaster.com/6627K51",
    "source": "supplier"
  },
  "bom_row_appended": true,
  "geometry_injected": true
}
```

---

## Architecture Notes

| Module | Status | Notes |
|---|---|---|
| `llm_parser.py` | **Live** | Calls Claude claude-haiku-4-5 via Anthropic SDK |
| `agentql_scraper.py` | **Live** | Headless Playwright + AgentQL semantic selectors |
| `bom_logger.py` | **Live** | gspread + Google Service Account auth |
| `virtual_oem.py` | **Stub** | Returns randomised mock data; Xometry API pending |
| `geometry_injector.py` | **Stub** | Logs intended action; RPC/REST calls pending |
| `main.py` | **Live** | Full async FastAPI orchestration with timing logs |

---

## Next Steps to Productionise

### Xometry API (Virtual OEM)
- Obtain API credentials from [xometry.com/api](https://xometry.com)
- Replace stub in `virtual_oem.py` with authenticated `POST /v1/quotes`
- Populate `step_file_url` from the Xometry geometry endpoint response

### FreeCAD Geometry Injection
- Add a lightweight xmlrpc or TCP socket server to the FreeCAD startup macro
- Replace stub in `geometry_injector._inject_freecad()` with `xmlrpc.client.ServerProxy` call
- Macro on the FreeCAD side: `Part.insert(step_url, App.ActiveDocument.Name)`

### Onshape Geometry Injection
- Store `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` in `.env`
- Implement HMAC-signed request auth (date + nonce + method + path + content-type)
- Replace stub in `geometry_injector._inject_onshape()`:
  1. Upload STEP blob: `POST /api/blobelements/d/{did}/w/{wid}`
  2. Import feature: `POST /api/partstudios/d/{did}/w/{wid}/e/{eid}/features`

### BOM Retrieval
- Implement `GET /bom/{workspace_id}` to query and return all rows matching the workspace

### Production Hardening
- Add request authentication (API key header or OAuth2)
- Add a task queue (Celery + Redis) for long-running scrape jobs
- Containerise with Docker; deploy to AWS EC2 or Render
- Add Prometheus metrics middleware for per-step latency monitoring
# Sourcing_copilot
