# TenderLens

TenderLens is an evidence-first RFP intelligence workspace. It turns tender PDFs into searchable, page-level evidence while preserving citations and identifying OCR/manual-review pages.

## What works today

- PDF upload with SHA-256 duplicate detection
- Embedded-text extraction with page references
- Tesseract OCR fallback and confidence reporting
- PostgreSQL full-text search and pgvector semantic retrieval
- Reciprocal-rank fusion for hybrid results
- Clickable citations back to the extracted page
- One-click Gemini tender analysis with evidence-backed page citations
- Structured dates, eligibility, requirements, documents, financial terms, deliverables, and risks
- Company profile form with optional browser saving
- Bid / No Bid / Review Required assessment, requirement matches, evidence coverage, and citations
- Per-requirement required vs submitted information, explicit gaps, and truthful answer templates
- Local Ollama or hosted Gemini embeddings
- Local filesystem or persistent Supabase Storage
- Optional access-code protection for public demo uploads
- 10 MB / 50-page portfolio-demo limits

## Architecture

| Layer | Local development | Free portfolio deployment |
|---|---|---|
| Web | Next.js in Docker | Vercel Hobby |
| API/OCR | FastAPI + Tesseract in Docker | Render Docker web service |
| Database | PostgreSQL 16 + pgvector | Supabase Postgres + pgvector |
| PDF storage | Mounted local directory | Private Supabase Storage bucket |
| Embeddings | Ollama `nomic-embed-text` | Gemini `gemini-embedding-2` at 768 dimensions |

The API is provider-driven through environment variables. No cloud credentials are required for local Docker development.
Tender analysis uses Gemini generation in both environments; add `GEMINI_API_KEY` locally only when testing the Analyze Tender feature.

## Run locally

Requirements: Docker Desktop and Ollama.

```powershell
Set-Location D:\TenderLens
Copy-Item .env.example .env
ollama pull nomic-embed-text
docker compose up --build
```

Open:

- App: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Deployment readiness: <http://localhost:8000/ready>

Stop without deleting database data:

```powershell
docker compose down
```

## Production deployment

### 1. Supabase

1. Create a free project.
2. In the SQL editor run `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;`.
3. Create a **private** Storage bucket named `tender-pdfs`.
4. Copy the session-pooler connection string, project URL and service-role key.
5. Keep the service-role key server-side; never add it to Vercel or a `NEXT_PUBLIC_*` variable.

The API creates its tables and indexes on first boot. Gemini and Ollama both use 768-dimensional vectors, so the database schema remains portable between environments.

### 2. Render API

Connect the Git repository and use the root [`render.yaml`](./render.yaml) Blueprint, or create a Docker web service with `apps/api` as its root directory. Add the secret values shown in [`.env.production.example`](./.env.production.example).

Required secrets:

- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `GEMINI_API_KEY`
- `DEMO_ACCESS_CODE`
- `ALLOWED_ORIGINS` (the final Vercel URL)

Keep `DB_DISABLE_PREPARED_STATEMENTS=false` with the recommended session pooler. Set it to `true` only if using Supabase transaction mode (port 6543).

Each completed semantic index records its embedding provider, model and dimensions. Search ignores vectors produced by a different provider/model; reprocess documents after switching between Ollama and Gemini.

After deployment, confirm `/health`, then `/ready`.

### 3. Vercel web

Import the same repository and set **Root Directory** to `apps/web`. Add:

```text
NEXT_PUBLIC_API_URL=https://YOUR-API.onrender.com
NEXT_PUBLIC_MAX_UPLOAD_MB=10
```

Redeploy the Render API once `ALLOWED_ORIGINS` contains the exact Vercel origin. Multiple origins can be comma-separated.

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Lightweight liveness check |
| `GET` | `/ready` | Database and provider configuration check |
| `POST` | `/documents` | Upload and process a PDF; access code protected when configured |
| `GET` | `/documents` | List documents |
| `GET` | `/documents/{id}` | Read processing state |
| `DELETE` | `/documents/{id}` | Delete the PDF and all derived evidence; access code protected when configured |
| `POST` | `/documents/{id}/reprocess` | Retry extraction; access code protected when configured |
| `GET` | `/documents/{id}/pages` | Read page-level evidence |
| `POST` | `/documents/{id}/analysis` | Start or rerun structured tender analysis; access code protected |
| `GET` | `/documents/{id}/analysis` | Read analysis state and evidence-backed findings |
| `POST` | `/documents/{id}/assessment` | Compare a company profile to completed analysis; access code protected |
| `GET` | `/documents/{id}/assessment` | Read saved assessment and submitted profile; access code protected |
| `POST` | `/documents/{id}/questions` | Ask a document-scoped question with quote-checked citations; access code protected |
| `GET` | `/documents/{id}/report?include_company=true` | Download saved analysis and optional company assessment as PDF; access code protected |
| `GET` | `/search?q=insurance` | Hybrid evidence search |
| `GET` | `/embeddings/health` | Check the configured embedding provider |

For protected operations send `X-Demo-Access-Code`. Public reads remain available so reviewers can inspect preloaded sample tenders without a code.

## Bid assessment

Each comparison shows the tender condition, exact submitted values from the relevant company fields, what is missing or different, and a suggested answer template. Templates ask for truthful details with placeholders; they are not generated company credentials. **Update company details** opens and focuses the relevant profile field. Guidance is included in the same Gemini comparison call. Old assessments remain readable; reassess once to generate tender-specific templates. Company values always come from the saved assessment snapshot rather than the current edited draft.

Select a processed document, complete **Analyze Tender**, then fill the company profile and run **Assess Bid / No Bid**. Save Profile keeps a reusable draft in this browser; running an assessment sends the profile to Gemini and persists a snapshot with the latest assessment for that document. Assessment reads require the demo code because they contain company information. This is a shared demo workspace, not separate user accounts. Do not submit confidential company information to a shared showcase.

Gemini classifies each analyzed requirement as met, unmet, or unknown. Positive and negative matches must include a verbatim company-profile excerpt; missing evidence remains unknown. Requirement text and page citations come from the existing analysis. The server computes the score as met / total and evidence coverage as (met + unmet) / total. Eligibility, mandatory requirements, required documents and financial conditions are treated conservatively as required conditions. A confirmed required-condition gap yields No Bid. Unknown required conditions, coverage below 80%, or fewer than 75% matches yield Review Required. Otherwise the result is Bid. This is a provisional fit check based on analyzed clauses, not full compliance verification or a probability of winning; review original clauses, submission deadlines, and commercial risks separately.

Reanalyzing or reprocessing invalidates the previous assessment. Concurrent analysis/reprocessing is blocked while an assessment runs. Interrupted assessment jobs become retryable on API restart. No new provider or environment variable is needed: the same `GEMINI_API_KEY` and `ANALYSIS_MODEL` are reused.

## Evidence-based Q&A

Select a processed PDF and use **Ask this tender**. Send `{"question":"What are the staffing requirements?"}` to the questions endpoint with the demo code. Questions are limited to 200 characters. Hybrid retrieval selects up to six pages from that document only; natural-language keyword fallback remains available when embeddings fail or time out. Up to 8,000 characters per selected page are sent to the existing Gemini analysis model. No new environment variables, tables or providers are required.

Answers contain concise points and clickable page citations with source quotes. The server rejects any point whose citations are outside the retrieved pages or whose quotes do not occur in the text sent to the model. This checks quote provenance, not semantic entailment: users must still review whether the quote fully supports the answer. Unsupported responses become `not_found`; partially supported responses become `partial`. No evidence found means retrieval did not support the question, not that a condition is absent from the complete tender.

If a completed company assessment exists, its saved profile and result are included as self-reported context; unsaved form changes are not used. Do not submit confidential details to the shared demo. Answers are temporary and not persisted. Provider calls are access-code protected when configured, with at most two simultaneous Q&A requests per API process. This is not a daily quota or a production rate limiter. Free-tier provider quotas still apply.

Smoke test: ask a staffing question, open a citation, ask an unrelated question, then switch PDFs and confirm the answer resets. For company gaps, run an assessment first. Reprocessing clears the visible answer. Closing the page cancels the browser request but may not stop an already-started provider call.

## Report export and interface

The earthy-pastel workspace separates upload, tender analysis, company fit, Q&A, report export and source text with explicit section headings and tinted panels. The hero uses a locally hosted Unsplash architecture photograph; source and license are recorded in `apps/web/public/IMAGE_CREDITS.md` and attribution appears in the interface. No third-party image request is needed to render the page.

After analysis completes, **Download PDF report** exports the saved analysis, source PDF page references, recommendation, match/coverage figures, requirement gaps, answer templates and submitted company snapshot. Untick **Include saved company assessment** for a tender-only brief. If no completed assessment exists, the report explicitly says none was included. An in-progress assessment blocks company export but not tender-only export. Q&A history and unsaved form edits are not exported.

ReportLab renders the PDF locally without calling Gemini or adding a paid service. No database migration or new environment variables are needed; rebuild the API image to install the new Python dependency. Reports are access-code protected when configured, are returned with `Cache-Control: no-store`, and are not saved on the server. Exported company information is self-reported and sensitive: keep reports private. The PDF includes limitations and distinguishes source PDF page numbers from report page numbers. The bundled font covers Latin-script report content; full multilingual/RTL typography is not yet supported.

## Tests

```powershell
Set-Location D:\TenderLens\apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

Frontend production check:

```powershell
Set-Location D:\TenderLens\apps\web
npm ci
npm run build
```

## Free-tier behavior

Render may sleep while inactive, so the first API request can be slow. PDFs remain in Supabase Storage and extracted evidence remains in Supabase Postgres across restarts. Interrupted jobs are marked retryable on the next API start instead of remaining stuck forever.
