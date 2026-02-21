## Backend – FastAPI Service

FastAPI backend for the Vertex COA & Quotation Generator. Handles:

- Excel/CSV upload and parsing
- Per-row OpenAI calls to generate **Quotation + COA/CoC** in the exact Vertex formats
- MongoDB persistence of documents (HTML + metadata)
- Download endpoints for **.docx** and **.pdf** (server-generated files)

### 1. Prerequisites

- Python 3.10+
- **OpenAI API key** (from `https://platform.openai.com`)
- **MongoDB Atlas** free cluster (connection string)

### 2. Install dependencies

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS / Linux

pip install -r requirements.txt
```

### 3. Environment variables (`backend/.env`)

Create a `.env` file in the `backend/` folder with:

```bash
OPENAI_API_KEY=sk-...                # From OpenAI dashboard
OPENAI_MODEL=gpt-4.1-mini            # Or another chat model that supports long prompts

MONGODB_URI=mongodb+srv://...        # From MongoDB Atlas --> "Connect" --> "Connect your application"
MONGODB_DB_NAME=vertex_ai            # Any DB name; must match what you want to use

ALLOWED_ORIGINS=http://localhost:5173  # Comma-separated list of frontend origins
```

**Where to get these values:**

- **OPENAI_API_KEY**:  
  - Sign up / log in at `https://platform.openai.com`
  - Go to **API keys** and create a new secret key
  - Paste it as `OPENAI_API_KEY`
- **MONGODB_URI**:  
  - Create a free cluster at `https://cloud.mongodb.com`
  - In your cluster, click **Connect → Connect your application**
  - Copy the connection string and replace `<username>`, `<password>`, and `<cluster-url>` with your details
- **ALLOWED_ORIGINS**:  
  - The URL where your frontend runs (local: `http://localhost:5173`; on Render: your frontend domain)

### 4. Run the backend locally

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The main API base URL is:

```text
http://localhost:8000/api
```

Key endpoints:

- `POST /api/upload-preview` – upload Excel/CSV and get clean row previews
- `POST /api/generate-row` – OpenAI generation for **one** row (returns Quotation + COA/CoC)
- `GET /api/documents` – list all documents (with filters)
- `GET /api/documents/{id}` – get full document content
- `PUT /api/documents/{id}` – update edited HTML content
- `GET /api/documents/{id}/download.docx` – download a single `.docx` file
- `GET /api/documents/{id}/download.pdf` – download a single PDF file (generated server-side)

**Document export (production):** TipTap HTML is the single source of truth. Both DOCX and PDF are generated **independently** from the same HTML (no DOCX→PDF). Uses `app/services/export`: HTML → DOCX via html2docx; HTML → PDF via WeasyPrint (best quality) with xhtml2pdf fallback. Print CSS in `export/print_css.py` keeps tables stable (table-layout: fixed, borders, page-breaks). Works on Render free tier with pip-only deps; WeasyPrint is optional (fallback to xhtml2pdf if system libs unavailable).

### 5. Troubleshooting and debugging MongoDB

**Check if your URI is correct**

1. **From the app:** On the Dashboard, when you see "Database unavailable", click **"Check connection (debug MongoDB)"**. The result will show a short error (e.g. SSL, timeout, auth) to help you fix `MONGODB_URI`.
2. **From the API:** With the backend running, open:
   - `http://localhost:8000/api/health/db`
   - You should get `{"ok": true, "message": "MongoDB connection OK"}` or `{"ok": false, "error": "..."}` with a hint.

**Common errors**

- **SSL handshake failed** (often on Windows): Update certifi and Python:
  - `pip install -U certifi`
  - Use Python 3.10+ if possible.
- **Connection timed out**: In Atlas → **Network Access**, add your current IP (or `0.0.0.0/0` for testing).
- **Authentication failed**: In Atlas → **Database Access**, check the user’s username/password. In the URI, special characters in the password must be URL-encoded (e.g. `@` → `%40`).

**URI format**

- From Atlas: **Connect** → **Connect your application** → copy the URI.
- Replace `<password>` with your actual password (URL-encode if it has `@`, `#`, etc.).
- Example: `mongodb+srv://myuser:mypass%40word@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`

### 6. Deployment notes (Render)

On Render free tier (no LibreOffice, no system binaries): export uses **pure Python** libraries only. DOCX: html2docx. PDF: WeasyPrint when it installs (best quality); if `pip install weasyprint` fails (e.g. missing cairo/pango), remove `weasyprint` from `requirements.txt` and the app will use the xhtml2pdf fallback automatically.

- Build command:

```bash
pip install -r backend/requirements.txt
```

- Start command:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Environment variables: same as `.env` above (set them in Render dashboard). No external document APIs or paid services except OpenAI.

