"use client";

import { ChangeEvent, FormEvent, ReactNode, useCallback, useEffect, useState } from "react";
import AssessmentPanel from "./assessment-panel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? "10");

type Document = {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number | null;
  status: "queued" | "processing" | "ready" | "failed";
  error_message: string | null;
  embedding_status: "pending" | "processing" | "ready" | "unavailable";
  embedding_error: string | null;
  created_at: string;
};

type Page = {
  page_number: number;
  text: string;
  char_count: number;
  ocr_required: boolean;
  extraction_method: "embedded" | "ocr";
  ocr_confidence: number | null;
};

type SearchResult = {
  document_id: string;
  filename: string;
  page_number: number;
  snippet: string;
  rank: number;
  extraction_method: "embedded" | "ocr";
  ocr_confidence: number | null;
  retrieval_method: "keyword" | "semantic" | "hybrid";
  semantic_similarity: number | null;
};

type AnalysisFinding = {
  label: string;
  detail: string;
  page_numbers: number[];
};

type AnalysisContent = {
  overview: AnalysisFinding;
  important_dates: AnalysisFinding[];
  eligibility: AnalysisFinding[];
  mandatory_requirements: AnalysisFinding[];
  required_documents: AnalysisFinding[];
  financial_conditions: AnalysisFinding[];
  deliverables: AnalysisFinding[];
  risks: AnalysisFinding[];
};

type DocumentAnalysis = {
  document_id: string;
  status: "not_started" | "queued" | "processing" | "ready" | "failed";
  error_message: string | null;
  model: string | null;
  content: AnalysisContent | null;
};

function highlightedSnippet(snippet: string): ReactNode[] {
  return snippet.split(/(\[\[\[.*?\]\]\])/g).map((part, index) =>
    part.startsWith("[[[") && part.endsWith("]]]") ? (
      <mark key={index}>{part.slice(3, -3)}</mark>
    ) : (
      <span key={index}>{part}</span>
    ),
  );
}

export default function Home() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const [accessCode, setAccessCode] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [analysis, setAnalysis] = useState<DocumentAnalysis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const selectedDocument = documents.find((document) => document.id === selectedId);

  useEffect(() => {
    setAccessCode(window.sessionStorage.getItem("tenderlens-access-code") ?? "");
  }, []);

  function protectedHeaders(): HeadersInit {
    return accessCode ? { "X-Demo-Access-Code": accessCode } : {};
  }

  const loadDocuments = useCallback(async () => {
    const response = await fetch(`${API_URL}/documents`, { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load documents");
    setDocuments(await response.json());
  }, []);

  useEffect(() => {
    loadDocuments().catch((reason) => setError(reason.message));
  }, [loadDocuments]);

  useEffect(() => {
    if (
      !documents.some(
        (document) =>
          document.status === "queued" ||
          document.status === "processing" ||
          document.embedding_status === "processing",
      )
    )
      return;
    const timer = window.setTimeout(() => loadDocuments().catch(() => undefined), 2500);
    return () => window.clearTimeout(timer);
  }, [documents, loadDocuments]);

  useEffect(() => {
    if (!selectedId) return;
    fetch(`${API_URL}/documents/${selectedId}/pages`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("Could not load extracted pages");
        return response.json();
      })
      .then(setPages)
      .catch((reason) => setError(reason.message));
  }, [selectedId, documents]);

  const loadAnalysis = useCallback(async (documentId: string) => {
    const response = await fetch(`${API_URL}/documents/${documentId}/analysis`, { cache: "no-store" });
    if (!response.ok) throw new Error("Could not load tender analysis");
    setAnalysis(await response.json());
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setAnalysis(null);
      return;
    }
    setAnalysis(null);
    loadAnalysis(selectedId).catch((reason) => setError(reason.message));
  }, [selectedId, loadAnalysis]);

  useEffect(() => {
    if (!selectedId || !analysis || !["queued", "processing"].includes(analysis.status)) return;
    const timer = window.setTimeout(
      () => loadAnalysis(selectedId).catch((reason) => setError(reason.message)),
      2500,
    );
    return () => window.clearTimeout(timer);
  }, [analysis, selectedId, loadAnalysis]);

  useEffect(() => {
    if (targetPage === null || pages.length === 0) return;
    document.getElementById(`page-${targetPage}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setTargetPage(null);
  }, [pages, targetPage]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`PDF exceeds the ${MAX_UPLOAD_MB} MB demo limit`);
      return;
    }
    setUploading(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    try {
      window.sessionStorage.setItem("tenderlens-access-code", accessCode);
      const response = await fetch(`${API_URL}/documents`, {
        method: "POST",
        headers: protectedHeaders(),
        body: form,
      });
      const body = await response.json();
      if (!response.ok) {
        const detail = typeof body.detail === "string" ? body.detail : body.detail?.message;
        throw new Error(detail ?? "Upload failed");
      }
      setSelectedId(body.id);
      setFile(null);
      await loadDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  async function search(event: FormEvent) {
    event.preventDefault();
    const cleaned = query.trim();
    if (cleaned.length < 2) return;
    setSearching(true);
    setError(null);
    setHasSearched(true);
    try {
      const response = await fetch(`${API_URL}/search?q=${encodeURIComponent(cleaned)}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Search failed");
      setSearchResults(await response.json());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function openCitation(result: SearchResult) {
    setTargetPage(result.page_number);
    setSelectedId(result.document_id);
  }

  async function reprocessSelected() {
    if (!selectedId) return;
    setError(null);
    try {
      const response = await fetch(`${API_URL}/documents/${selectedId}/reprocess`, {
        method: "POST",
        headers: protectedHeaders(),
      });
      if (!response.ok) throw new Error("Could not reprocess the document");
      setAnalysis(null);
      await loadDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reprocess the document");
    }
  }

  async function analyzeSelected() {
    if (!selectedId) return;
    setAnalyzing(true);
    setError(null);
    try {
      window.sessionStorage.setItem("tenderlens-access-code", accessCode);
      const response = await fetch(`${API_URL}/documents/${selectedId}/analysis`, {
        method: "POST",
        headers: protectedHeaders(),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Could not analyze this tender");
      setAnalysis(body);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not analyze this tender");
    } finally {
      setAnalyzing(false);
    }
  }

  async function deleteSelected() {
    if (!selectedId || !selectedDocument) return;
    const confirmed = window.confirm(
      `Delete "${selectedDocument.filename}" and all of its extracted pages? This cannot be undone.`,
    );
    if (!confirmed) return;

    setDeleting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/documents/${selectedId}`, {
        method: "DELETE",
        headers: protectedHeaders(),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "Could not delete the document");
      }
      setSearchResults((results) => results.filter((result) => result.document_id !== selectedId));
      setSelectedId(null);
      setPages([]);
      setAnalysis(null);
      await loadDocuments();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete the document");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <main>
      <header>
        <div className="brand-mark">TL</div>
        <div>
          <p className="eyebrow">RFP intelligence workspace</p>
          <h1>TenderLens</h1>
        </div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">Ingestion milestone</p>
          <h2>Turn dense tender packs into page-level evidence.</h2>
          <p className="muted">
            Upload a PDF to extract its text, preserve page references, and identify pages that need OCR.
          </p>
        </div>
        <form onSubmit={upload} className="upload-card">
          <div className="demo-notice">Free demo API may need up to a minute to wake up.</div>
          <label htmlFor="pdf">Tender PDF</label>
          <input id="pdf" type="file" accept="application/pdf,.pdf" onChange={chooseFile} />
          <label htmlFor="access-code">Demo access code</label>
          <input
            id="access-code"
            onChange={(event) => setAccessCode(event.target.value)}
            placeholder="Required on public demo"
            type="password"
            value={accessCode}
          />
          <button disabled={!file || uploading}>{uploading ? "Uploading…" : "Process PDF"}</button>
          <small>
            {file
              ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB`
              : `Maximum ${MAX_UPLOAD_MB} MB · 50 pages`}
          </small>
        </form>
      </section>

      {error && <div className="error">{error}</div>}

      <section className="search-section">
        <form className="search-bar" onSubmit={search}>
          <input
            aria-label="Search tender pages"
            onChange={(event) => setQuery(event.target.value)}
            placeholder='Search evidence, e.g. "mandatory insurance"'
            type="search"
            value={query}
          />
          <button disabled={query.trim().length < 2 || searching}>
            {searching ? "Searching…" : "Search pages"}
          </button>
        </form>
        {hasSearched && (
          <div className="search-results">
            <div className="search-summary">
              <strong>{searchResults.length} evidence matches</strong>
              <span>Keyword + semantic retrieval with reciprocal-rank fusion</span>
            </div>
            {searchResults.length === 0 && <p className="empty">No matching page evidence found.</p>}
            {searchResults.map((result) => (
              <button
                className="search-result"
                key={`${result.document_id}-${result.page_number}`}
                onClick={() => openCitation(result)}
              >
                <span className="result-source">
                  {result.filename} · Page {result.page_number}
                </span>
                <span className="result-snippet">{highlightedSnippet(result.snippet)}</span>
                <span className="result-meta">
                  {result.retrieval_method}
                  {result.semantic_similarity !== null
                    ? ` · ${(result.semantic_similarity * 100).toFixed(0)}% semantic similarity`
                    : ""}
                  {" · "}
                  {result.extraction_method === "ocr"
                    ? `OCR ${result.ocr_confidence?.toFixed(0) ?? "—"}%`
                    : "Embedded text"}
                  {" · Click to open citation"}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="workspace">
        <aside>
          <div className="section-title">
            <h3>Documents</h3>
            <span>{documents.length}</span>
          </div>
          <div className="document-list">
            {documents.length === 0 && <p className="empty">No tenders uploaded yet.</p>}
            {documents.map((document) => (
              <button
                className={`document-row ${selectedId === document.id ? "selected" : ""}`}
                key={document.id}
                onClick={() => setSelectedId(document.id)}
              >
                <span className="filename">{document.filename}</span>
                <span className={`status ${document.status}`}>{document.status}</span>
                <small>
                  {document.page_count ? `${document.page_count} pages` : `${(document.size_bytes / 1024).toFixed(0)} KB`}
                  {document.embedding_status === "ready" && " · Semantic index ready"}
                  {document.embedding_status === "processing" && " · Building semantic index"}
                  {document.embedding_status === "unavailable" && " · Keyword search only"}
                </small>
              </button>
            ))}
          </div>
        </aside>

        <section className="pages-panel">
          <div className="section-title">
            <h3>Extracted pages</h3>
            <div className="section-actions">
              {selectedId && (
                <>
                  <button
                    className="analysis-button"
                    disabled={
                      analyzing ||
                      selectedDocument?.status !== "ready" ||
                      analysis?.status === "queued" ||
                      analysis?.status === "processing"
                    }
                    onClick={analyzeSelected}
                    type="button"
                  >
                    {analysis?.status === "queued" || analysis?.status === "processing"
                      ? "Analyzing…"
                      : analysis?.status === "ready"
                        ? "Analyze again"
                        : "Analyze tender"}
                  </button>
                  <button
                    className="danger-button"
                    disabled={deleting || selectedDocument?.status === "queued" || selectedDocument?.status === "processing"}
                    onClick={deleteSelected}
                    type="button"
                  >
                    {deleting ? "Deleting…" : "Delete PDF"}
                  </button>
                  <button className="secondary-button" onClick={reprocessSelected} type="button">
                    Reprocess
                  </button>
                </>
              )}
              <span>{pages.length}</span>
            </div>
          </div>
          {!selectedId && <p className="empty centered">Select a document to inspect its page text.</p>}
          {selectedId && pages.length === 0 && (
            <p className="empty centered">Processing the document or no extractable pages found yet.</p>
          )}
          {selectedId && analysis?.status === "not_started" && selectedDocument?.status === "ready" && (
            <div className="analysis-empty">
              <span className="eyebrow">Tender intelligence</span>
              <strong>Turn extracted pages into an evidence-backed procurement brief.</strong>
              <p>Analyze dates, eligibility, mandatory requirements, documents, financial terms, deliverables, and risks.</p>
            </div>
          )}
          {analysis && ["queued", "processing"].includes(analysis.status) && (
            <div className="analysis-progress">
              <span className="analysis-pulse" />
              <div>
                <strong>Gemini is analyzing this tender</strong>
                <p>Reviewing extracted evidence and validating page citations. Free-tier processing may take a minute.</p>
              </div>
            </div>
          )}
          {analysis?.status === "failed" && (
            <div className="analysis-failed">
              <strong>Analysis needs another attempt</strong>
              <p>{analysis.error_message ?? "The analysis job did not complete."}</p>
            </div>
          )}
          {analysis?.status === "ready" && analysis.content && (
            <section className="analysis-panel">
              <div className="analysis-heading">
                <div>
                  <span className="eyebrow">Tender intelligence</span>
                  <h3>{analysis.content.overview.label}</h3>
                  <p>{analysis.content.overview.detail}</p>
                </div>
                <div className="citation-list">
                  {analysis.content.overview.page_numbers.map((pageNumber) => (
                    <button key={pageNumber} onClick={() => setTargetPage(pageNumber)} type="button">
                      Page {pageNumber}
                    </button>
                  ))}
                </div>
              </div>
              {(
                [
                  ["Important dates", analysis.content.important_dates],
                  ["Eligibility", analysis.content.eligibility],
                  ["Mandatory requirements", analysis.content.mandatory_requirements],
                  ["Required documents", analysis.content.required_documents],
                  ["Financial conditions", analysis.content.financial_conditions],
                  ["Deliverables", analysis.content.deliverables],
                  ["Risks and red flags", analysis.content.risks],
                ] as [string, AnalysisFinding[]][]
              ).map(([title, findings]) => (
                <div className="analysis-section" key={title}>
                  <div className="analysis-section-title">
                    <h4>{title}</h4>
                    <span>{findings.length}</span>
                  </div>
                  {findings.length === 0 && <p className="analysis-none">No supported findings.</p>}
                  <div className="finding-grid">
                    {findings.map((finding, index) => (
                      <article className="finding" key={`${title}-${index}`}>
                        <strong>{finding.label}</strong>
                        <p>{finding.detail}</p>
                        <div className="citation-list">
                          {finding.page_numbers.map((pageNumber) => (
                            <button key={pageNumber} onClick={() => setTargetPage(pageNumber)} type="button">
                              Page {pageNumber}
                            </button>
                          ))}
                        </div>
                      </article>
                    ))}
                  </div>
                </div>
              ))}
            </section>
          )}
          {selectedId && (
            <AssessmentPanel key={selectedId} apiUrl={API_URL} documentId={selectedId}
              accessCode={accessCode} analysisReady={analysis?.document_id === selectedId && analysis.status === "ready"}
              onCitation={setTargetPage} />
          )}
          <div className="pages">
            {pages.map((page) => (
              <article className="page" id={`page-${page.page_number}`} key={page.page_number}>
                <div className="page-header">
                  <strong>Page {page.page_number}</strong>
                  <span className={page.ocr_required ? "ocr needed" : "ocr"}>
                    {page.ocr_required
                      ? "Manual review required"
                      : page.extraction_method === "ocr"
                        ? `OCR · ${page.ocr_confidence?.toFixed(0) ?? "—"}% confidence`
                        : `${page.char_count} characters · embedded text`}
                  </span>
                </div>
                <pre>{page.text || "No embedded text detected."}</pre>
              </article>
            ))}
          </div>
        </section>
      </section>
    </main>
  );
}

