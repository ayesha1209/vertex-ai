## Frontend – React/Vite App

React + Vite + Tailwind frontend for the Vertex COA & Quotation Generator. Handles:

- **Upload & preview** of Excel/CSV files
- Per-row batch generation UI (progress + live results)
- **Documents dashboard** (grouped by Buyer / Product, search, actions)
- Full-page **TipTap editor** with Word-like experience
- **Download** one document at a time or **Download All** as sequential `.docx` downloads (no ZIP)

### 1. Prerequisites

- Node.js 18+ and npm
- Backend service running (locally or on Render)

### 2. Install dependencies

```bash
cd frontend
npm install
```

### 3. Environment variables (`frontend/.env`)

Create a `.env` file in the `frontend/` folder with:

```bash
VITE_API_BASE_URL=http://localhost:8000/api
```

- For production (e.g. Render), set this to your backend URL, e.g.:

```bash
VITE_API_BASE_URL=https://your-backend-service.onrender.com/api
```

> This must point to the same origin your backend is exposed on, and that origin must be listed in the backend's `ALLOWED_ORIGINS`.

### 4. Run the frontend locally

```bash
npm run dev
```

Open `http://localhost:5173` in your browser.

### 5. Key screens and flow

- **Upload & Generate** (`/`):
  - Drag-and-drop Excel/CSV
  - Preview/edit rows
  - Click **Generate All Documents** to batch-call OpenAI via the backend
  - See live-generated documents while the rest are still processing
- **Documents Dashboard** (`/documents`):
  - Grouped by Buyer/Product
  - Search and refresh
  - Per-document:
    - **Download .docx** (single file)
    - **View as PDF** (opens HTML so you can use browser "Print to PDF")
    - **Edit** in full-page editor
  - **Download All** triggers **sequential individual `.docx` downloads** in the browser
- **Editor** (`/documents/:id`):
  - TipTap editor with:
    - Bold/Italic/Underline
    - Bulleted & numbered lists
    - Alignment (left/center/right)
    - Tables (insert, add/delete rows & columns, merge/split cells)
    - Undo/redo
  - **Save** persists changes back to MongoDB via backend

### 6. Deployment notes (Render)

On Render, create a **Static Site**:

- Build command:

```bash
cd frontend && npm install && npm run build
```

- Publish directory:

```bash
frontend/dist
```

Environment variable:

- `VITE_API_BASE_URL=https://your-backend-service.onrender.com/api`

