# PageQuay

Enterprise-grade document service built with FastAPI, PostgreSQL, Redis, and ARQ.
Supports OCR, document storage, bulk uploading, compression, full-text search, versioning,
and audit logging.

## Features

- **Document ingestion**: single & bulk upload with SHA-256 deduplication
- **Compression**: gzip/zlib + pikepdf (qpdf) structural PDF optimization
- **OCR**: Tesseract-powered OCR via ARQ background workers for PDFs and raster images
- **Content extraction**: save and extract text from supported files, or extract without saving
- **Full-text search**: PostgreSQL `tsvector` + GIN index across filename + OCR content
- **Versioning**: per-document version history with change notes
- **Audit logging**: immutable action log for compliance
- **Storage**: pluggable backend (local filesystem default, S3/MinIO swap-ready)
- **Soft delete**: recoverable document removal

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI (Python 3.13) |
| Database | PostgreSQL 15 + SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Cache/Queue | Redis 7 + ARQ |
| OCR | Tesseract + pytesseract + pdf2image + Pillow |
| PDF Optimization | pikepdf (qpdf) |
| Validation | Pydantic v2 |
| Testing | pytest + httpx |
| Lint/Type | ruff + mypy |

## Quick Start

### Prerequisites

- Python 3.13+
- Docker & Docker Compose (recommended)
- Tesseract OCR binary (for local dev without Docker)

### Using Docker Compose (recommended)

```bash
# Clone and enter the project
cd DocumentService

# Copy environment config
cp .env.example .env
# Set unique API_KEY, API_SECRET, and UI_PASSWORD values in .env
# Generate a secret with: python -c 'import secrets; print(secrets.token_urlsafe(32))'

# Start infrastructure, API, worker, and web console
docker compose up --build

# The API is available at http://localhost:8000
# Interactive docs: http://localhost:8000/docs
# Browser console: http://localhost:3000
```

### Local Development

```bash
# Install system dependencies (Fedora)
sudo dnf install -y tesseract poppler-utils

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Copy environment config
cp .env.example .env
# Set API_KEY and API_SECRET; point DATABASE_URL at your PostgreSQL instance
# Docker Compose exposes PostgreSQL on host port 5433

# Run database migrations
alembic upgrade head

# Start the API
uvicorn app.main:application --reload --port 8000

# Start the ARQ worker (in a separate terminal)
arq app.worker.settings.WorkerSettings
```

## PageQuay Browser Console

Open `http://localhost:3000` and sign in with `UI_USERNAME` and `UI_PASSWORD` from
`.env`. The TanStack Start console supports saved file extraction, bulk ingestion,
document review, and REST/MCP customer provisioning. Its server routes forward API
requests with credentials kept on the server. A distinct `UI_SESSION_SECRET` is recommended;
when omitted, sessions use `API_SECRET`. Serve the console over HTTPS outside local development. For local frontend development,
run `pnpm install` and `pnpm dev` in `web/` with the API running on port 8000.

## API Endpoints

### Customer OCR API (initial SaaS offering)

Apply migrations with `alembic upgrade head`, then provision each customer through the
administrator API. These administrator routes use the existing `API_KEY` and
`API_SECRET` HTTP Basic credentials. The issued customer token is displayed only in
the creation response; store it securely.

```bash
curl -u "$API_KEY:$API_SECRET" -H 'Content-Type: application/json' \
  -d '{"name":"Acme","email":"ocr@acme.example","monthly_request_limit":1000}' \
  http://localhost:8000/api/v1/ocr/admin/customers

# Replace CUSTOMER_ID with the ID returned above.
curl -u "$API_KEY:$API_SECRET" -H 'Content-Type: application/json' \
  -d '{"name":"production"}' \
  http://localhost:8000/api/v1/ocr/admin/customers/CUSTOMER_ID/keys

# Replace CUSTOMER_TOKEN with the one-time token returned above.
curl -H "Authorization: Bearer $CUSTOMER_TOKEN" -F "file=@scan.png" \
  http://localhost:8000/api/v1/ocr/extract
curl -H "Authorization: Bearer $CUSTOMER_TOKEN" \
  -F "files=@scan.png" -F "files=@contract.docx" \
  http://localhost:8000/api/v1/ocr/bulk
curl -H "Authorization: Bearer $CUSTOMER_TOKEN" \
  http://localhost:8000/api/v1/ocr/usage
curl -H "Authorization: Bearer $CUSTOMER_TOKEN" \
  http://localhost:8000/api/v1/ocr/capabilities
```

Customer keys can be revoked with `DELETE
/api/v1/ocr/admin/customers/{customer_id}/keys/{key_id}`. Usage resets each UTC
calendar month and counts successful extraction requests; invalid files and engine
failures return the reserved request to the customer's allowance. A request over
the limit returns HTTP 429. The offering uses request based quotas, including for
multi-page PDFs. Set limits and prices accordingly. Serve these endpoints over
HTTPS in production. Administrators can change a customer's limit or deactivate
an account with `PATCH /api/v1/ocr/admin/customers/{customer_id}`.

The hosted MCP Streamable HTTP endpoint is `/mcp/`. Connect with
`Authorization: Bearer <customer token>` and configure `MCP_ALLOWED_HOSTS` and
`MCP_ALLOWED_ORIGINS` for your public hostname. It offers `extract_text`,
`extract_bulk`, and `get_ocr_usage`. Files are passed as base64 and the hosted MCP
transport limits each file to `MAX_MCP_FILE_SIZE_BYTES` (8 MiB by default).
The `get_capabilities` tool lists supported extraction formats and limits.
The local stdio bridge (`python -m app.mcp_server`) offers the same tools with
`OCR_API_BASE_URL` and `OCR_API_TOKEN` in its environment. Both MCP transports
call the metered customer REST API.

The document storage API accepts any file type up to `MAX_FILE_SIZE_BYTES`.
Text extraction supports PDFs, common raster images including multi-frame TIFF
and GIF, UTF-8/UTF-16 text and code files, CSV, JSON, XML, HTML, Markdown,
DOCX, XLSX, PPTX, ODF, EPUB, and EML. Unsupported proprietary or binary formats
can still be stored and searched by filename; extraction returns HTTP 415 until
an extractor or converter for that format is installed. OCR work is capped at
`MAX_OCR_PAGES` pages or image frames per file. Bulk endpoints accept at most
`MAX_OCR_BATCH_FILES` files per request. Customer bulk extraction is synchronous;
stored document bulk ingestion queues OCR in the background.

Checkout, recurring billing, and invoices are not yet connected.

All `/api/v1/documents` routes require HTTP Basic authentication: use `API_KEY` as
the username and `API_SECRET` as the password. Health endpoints remain public.
For example, `curl -u "$API_KEY:$API_SECRET" http://localhost:8000/api/v1/documents/`.
Use HTTPS when accessing the API outside your local machine.

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/upload` | Save a file; OCR is queued for PDFs/images and embedded text is saved as a result |
| `POST` | `/api/v1/documents/ocr/upload` | Extract text from a supported file immediately, without storing a document |
| `POST` | `/api/v1/documents/bulk-upload` | Bulk upload multiple files |
| `POST` | `/api/v1/documents/{document_id}/extract` | Extract from an existing saved file or queue OCR |
| `GET` | `/api/v1/documents/` | List documents (with full-text search via `?search=`) |
| `GET` | `/api/v1/documents/{id}` | Get document metadata |
| `GET` | `/api/v1/documents/{id}/download` | Download the document file |
| `PUT` | `/api/v1/documents/{id}` | Update document metadata |
| `DELETE` | `/api/v1/documents/{id}` | Soft-delete a document |
| `GET` | `/api/v1/documents/{id}/versions` | List document versions |
| `POST` | `/api/v1/documents/{id}/versions` | Upload a new version |
| `POST` | `/api/v1/documents/{id}/ocr` | Trigger OCR processing |
| `GET` | `/api/v1/documents/{id}/ocr` | Get OCR result |

For immediate extraction, send multipart form data with a `file` field:

```bash
curl -u "$API_KEY:$API_SECRET" -F "file=@scan.png" \
  http://localhost:8000/api/v1/documents/ocr/upload
```

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/documents/admin/audit-logs` | List audit log entries (compliance) |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Overall health |
| `GET` | `/api/v1/health/ready` | Readiness (DB + Redis) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEY` | (none) | HTTP Basic username for document routes |
| `API_SECRET` | (none) | HTTP Basic password; keep private |
| `UI_USERNAME` | (none) | Browser console username |
| `UI_PASSWORD` | (none) | Browser console password |
| `UI_SESSION_SECRET` | (none) | HMAC secret for signed console sessions |
| `DATABASE_URL` | `postgresql+asyncpg://docuser:docpass@localhost:5432/docservice` | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string (ARQ) |
| `STORAGE_BACKEND` | `local` | `local` or `s3` |
| `STORAGE_ROOT` | `/app/data/storage` | Local storage directory |
| `STORAGE_BUCKET` | (none) | S3 bucket name (when backend=s3) |
| `MAX_FILE_SIZE_BYTES` | `104857600` (100 MB) | Max upload size |
| `OCR_LANGUAGE` | `eng` | Tesseract language |
| `MAX_OCR_PAGES` | `50` | Maximum PDF pages or image frames per OCR file |
| `MAX_OCR_BATCH_FILES` | `20` | Maximum files in one bulk request |
| `MAX_MCP_FILE_SIZE_BYTES` | `8388608` | Maximum decoded file size through MCP |
| `MCP_ALLOWED_HOSTS` | local hosts | Allowed HTTP Host values for hosted MCP |
| `MCP_ALLOWED_ORIGINS` | local origins | Allowed browser origins for hosted MCP |
| `ENABLE_PDF_OPTIMIZE` | `true` | Enable pikepdf PDF structural optimization |
| `DEFAULT_COMPRESSION_LEVEL` | `6` | gzip compression level (0-9) |

## Running Tests

```bash
pip install -e '.[dev]'
# Set DATABASE_URL to a disposable PostgreSQL database ending in _test
DATABASE_URL='postgresql+asyncpg://docuser:docpass@localhost:5432/docservice_test' python -m pytest tests/ -v
```

The integration fixture drops and rebuilds the test database's `public` schema.

## Code Quality

```bash
ruff check app/ tests/
mypy app/
```

## Project Structure

```
DocumentService/
├── app/
│   ├── api/v1/documents.py   # Document + audit-log routes
│   ├── api/v1/health.py      # Health endpoints
│   ├── api/v1/api.py         # Router aggregation
│   ├── api/deps.py           # DB session dependency
│   ├── core/config.py        # Pydantic Settings
│   ├── core/security.py      # Filename sanitization
│   ├── db/base.py            # SQLAlchemy Base
│   ├── db/env.py             # Alembic env (async)
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Pydantic schemas
│   ├── services/             # Business logic (storage, compression, document)
│   ├── worker/               # ARQ worker (OCR, thumbnails)
│   └── main.py               # FastAPI app factory
├── web/                       # TanStack Start console and server-side API proxy
├── tests/
│   ├── conftest.py           # Test fixtures
│   ├── test_documents.py     # CRUD tests
│   ├── test_compression.py   # Compression tests
│   └── test_search.py        # Full-text search tests
├── docker-compose.yml        # Postgres + Redis + API + Worker + Web
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── .env.example
├── alembic.ini
└── README.md
```

## License

Internal use.
