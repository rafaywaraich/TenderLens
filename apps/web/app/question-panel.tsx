"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import WarningNotice from "./warning-notice";

type Answer = {
  status: "answered" | "partial" | "not_found";
  question: string;
  points: { text: string; citations: { page_number: number; quote: string }[] }[];
  searched_pages: number[];
  retrieval_method: string;
  used_company_assessment: boolean;
};

export default function QuestionPanel({ apiUrl, documentId, accessCode, ready, onCitation }: {
  apiUrl: string; documentId: string; accessCode: string; ready: boolean;
  onCitation: (page: number) => void;
}) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  // Reprocessing invalidates the current answer and cancels in-flight work.
  useEffect(() => {
    if (!ready) {
      controller.current?.abort();
      setAnswer(null);
      setBusy(false);
    }
  }, [ready]);

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!ready || busy || question.trim().length < 3) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError(null);
    setAnswer(null);
    const timeout = window.setTimeout(() => abort.abort(), 150000);
    try {
      const response = await fetch(`${apiUrl}/documents/${documentId}/questions`, {
        method: "POST", signal: abort.signal,
        headers: { "Content-Type": "application/json", ...(accessCode ? { "X-Demo-Access-Code": accessCode } : {}) },
        body: JSON.stringify({ question: question.trim() }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof body?.detail === "string" ? body.detail : "Could not answer this question.");
      if (!abort.signal.aborted) setAnswer(body);
    } catch (reason) {
      if (controller.current === abort) setError(abort.signal.aborted
        ? "Request cancelled or timed out. Please retry when the API is awake."
        : reason instanceof Error ? reason.message : "Question failed.");
    } finally {
      window.clearTimeout(timeout);
      if (controller.current === abort) setBusy(false);
    }
  }

  return <section className="qa-panel" aria-labelledby="qa-title">
    <span className="eyebrow">04 / A conversation with the evidence</span>
    <h3 id="qa-title">Ask this tender</h3>
    <p className="muted">Answers use only this PDF. Company comparisons use your last saved assessment, not unsaved form edits.</p>
    <form onSubmit={ask}>
      <label htmlFor="tender-question">Your question</label>
      <textarea id="tender-question" value={question} maxLength={200} rows={3}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder="What qualifications must the maintenance team have?" disabled={!ready || busy} />
      <div className="qa-examples">
        {["What documents are required?", "What are the staffing requirements?", "What company gaps remain?"].map((example) =>
          <button type="button" className="secondary-button" key={example} disabled={!ready || busy}
            onClick={() => setQuestion(example)}>{example}</button>)}
      </div>
      <button disabled={!ready || busy || question.trim().length < 3}>{busy ? "Reviewing evidence…" : "Ask tender"}</button>
    </form>
    {!ready && <WarningNotice title="Questions are not available yet">Complete PDF processing before asking a question.</WarningNotice>}
    {busy && <p role="status" className="muted">Retrieving pages and checking source quotes. Free-tier requests may take a minute.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {answer && <div className="qa-answer" aria-live="polite">
      <h4>{answer.question}</h4>
      {answer.status === "not_found" && <WarningNotice title="No supported answer found">Try rephrasing or inspect the original PDF. This does not prove the information is absent from the whole tender.</WarningNotice>}
      {answer.status === "partial" && <WarningNotice title="Partial answer — review the evidence">Some requested information could not be supported.</WarningNotice>}
      {answer.points.map((point, index) => <article className="finding" key={index}>
        <p>{point.text}</p>
        {point.citations.map((citation, n) => <div key={n}>
          <div className="citation-list"><button type="button" onClick={() => onCitation(citation.page_number)}>Page {citation.page_number}</button></div>
          <blockquote>{citation.quote}</blockquote>
        </div>)}
      </article>)}
      <small>Retrieved pages: {answer.searched_pages.join(", ") || "none"} · {answer.retrieval_method}
        {answer.used_company_assessment ? " · Saved company assessment included (self-reported)" : " · No saved company assessment"}
        . Quotes are checked against extracted text; review whether they fully support the answer. Answers are not saved.</small>
    </div>}
  </section>;
}
