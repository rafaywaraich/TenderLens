"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type Profile = {
  name: string;
  capabilities: string;
  registrations: string;
  experience: string;
  financial_capacity: string;
  available_documents: string;
  constraints: string;
};

type Comparison = {
  requirement_id: string;
  category: string;
  label: string;
  requirement: string;
  mandatory: boolean;
  status: "met" | "unmet" | "unknown";
  reason: string;
  profile_evidence: string;
  page_numbers: number[];
};

type Assessment = {
  document_id: string;
  status: "not_started" | "queued" | "processing" | "ready" | "failed";
  error_message: string | null;
  profile: Profile | null;
  content: {
    company_name: string;
    recommendation: "bid" | "no_bid" | "review_required";
    score: number;
    coverage: number;
    summary: string;
    comparisons: Comparison[];
    evaluated_on: string;
  } | null;
};

const EMPTY_PROFILE: Profile = {
  name: "", capabilities: "", registrations: "", experience: "",
  financial_capacity: "", available_documents: "", constraints: "",
};
const FIELDS: { key: keyof Profile; label: string; placeholder: string; max: number }[] = [
  { key: "name", label: "Company name", placeholder: "Your business name", max: 200 },
  { key: "capabilities", label: "Services and delivery capabilities", placeholder: "Services, team, equipment, locations, and delivery capacity", max: 6000 },
  { key: "registrations", label: "Registrations and compliance", placeholder: "Business registration, PEC category/codes, tax status, certifications; state any gaps", max: 4000 },
  { key: "experience", label: "Relevant experience", placeholder: "Years in business, similar completed projects, dates and contract values", max: 4000 },
  { key: "financial_capacity", label: "Financial capacity", placeholder: "Turnover, available funds, guarantees and security capacity; include currency and period", max: 4000 },
  { key: "available_documents", label: "Available bid documents", placeholder: "Certificates, tax returns, references, audited accounts, and other available documents", max: 4000 },
  { key: "constraints", label: "Constraints and known gaps", placeholder: "Unavailable registrations, staffing limits, capacity, geographic restrictions, or unacceptable terms", max: 4000 },
];
const PROFILE_KEY = "tenderlens-company-profile";

export default function AssessmentPanel({ apiUrl, documentId, accessCode, analysisReady, onCitation }: {
  apiUrl: string;
  documentId: string;
  accessCode: string;
  analysisReady: boolean;
  onCitation: (page: number) => void;
}) {
  const [profile, setProfile] = useState<Profile>(EMPTY_PROFILE);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [authRequired, setAuthRequired] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState(false);
  const active = useRef(true);

  useEffect(() => {
    active.current = true;
    try {
      const stored = JSON.parse(window.localStorage.getItem(PROFILE_KEY) ?? "null");
      if (stored && typeof stored === "object") {
        setProfile(Object.fromEntries(FIELDS.map(({ key, max }) => [key,
          typeof stored[key] === "string" ? stored[key].slice(0, max) : "",
        ])) as Profile);
      }
    } catch { /* A blocked browser store should not prevent assessment. */ }
    return () => { active.current = false; };
  }, []);

  const loadAssessment = useCallback(async (signal: AbortSignal) => {
    const response = await fetch(`${apiUrl}/documents/${documentId}/assessment`, {
      cache: "no-store", signal,
      headers: accessCode ? { "X-Demo-Access-Code": accessCode } : {},
    });
    if (response.status === 401) {
      if (!signal.aborted) { setAuthRequired(true); setAssessment(null); }
      return;
    }
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Could not load assessment");
    if (!signal.aborted) {
      setAuthRequired(false);
      setAssessment(body);
      if (body.profile) setProfile((current) => current.name || current.capabilities ? current : body.profile);
    }
  }, [apiUrl, documentId, accessCode]);

  useEffect(() => {
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      loadAssessment(controller.signal).catch((reason) => {
        if (!controller.signal.aborted) setError(reason.message);
      });
    }, 400);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [loadAssessment, analysisReady]);

  const running = assessment?.status === "queued" || assessment?.status === "processing";
  useEffect(() => {
    if (!running) return;
    const controller = new AbortController();
    let inFlight = false;
    const timer = window.setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        await loadAssessment(controller.signal);
        if (!controller.signal.aborted) setError(null);
      } catch (reason) {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Could not check assessment");
      } finally { inFlight = false; }
    }, 4000);
    return () => { window.clearInterval(timer); controller.abort(); };
  }, [running, loadAssessment]);

  function saveProfile() {
    try {
      window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
      setSaved(true);
    } catch { setError("Browser storage is unavailable. You can still run an assessment."); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${apiUrl}/documents/${documentId}/assessment`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(accessCode ? { "X-Demo-Access-Code": accessCode } : {}) },
        body: JSON.stringify(profile),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Check company name and capabilities, then retry");
      if (active.current) { setAssessment(body); setAuthRequired(false); }
    } catch (reason) {
      if (active.current) setError(reason instanceof Error ? reason.message : "Assessment failed");
    } finally { if (active.current) setSubmitting(false); }
  }

  const result = analysisReady && assessment?.status === "ready" ? assessment.content : null;
  const draftChanged = !!result && JSON.stringify(profile) !== JSON.stringify(assessment?.profile);

  return (
    <section className="bid-panel">
      <div className="bid-title">
        <span className="eyebrow">Bid decision copilot</span>
        <h3>Does this tender fit your company?</h3>
        <p>Compare the analyzed requirements with your company profile. Missing information stays unverified.</p>
      </div>
      <details className="profile-editor" open={!result}>
        <summary>Company profile {result ? "· edit and reassess" : "· add your details"}</summary>
        <form onSubmit={submit}>
          <div className="profile-grid">
            {FIELDS.map(({ key, label, placeholder, max }) => (
              <label key={key} htmlFor={`profile-${key}`}>
                <span>{label}{["name", "capabilities"].includes(key) ? " *" : ""}</span>
                {key === "name" ? (
                  <input id={`profile-${key}`} value={profile[key]} maxLength={max} required placeholder={placeholder}
                    onChange={(e) => { setProfile({ ...profile, [key]: e.target.value }); setSaved(false); }} />
                ) : (
                  <textarea id={`profile-${key}`} value={profile[key]} maxLength={max} rows={3}
                    required={key === "capabilities"} placeholder={placeholder}
                    onChange={(e) => { setProfile({ ...profile, [key]: e.target.value }); setSaved(false); }} />
                )}
              </label>
            ))}
          </div>
          <p className="profile-note">Save keeps this profile in your browser. Running an assessment sends it to Gemini and stores the profile snapshot with the result in this shared demo workspace. Saved assessments require the demo access code.</p>
          <div className="profile-actions">
            <button className="secondary-button" type="button" onClick={saveProfile}>{saved ? "Saved in this browser" : "Save profile"}</button>
            <button className="analysis-button" disabled={!analysisReady || running || submitting}>
              {running || submitting ? "Assessing…" : result ? "Reassess company fit" : "Assess Bid / No Bid"}
            </button>
          </div>
        </form>
      </details>
      {!analysisReady && <p className="bid-notice">Complete Analyze Tender first to enable assessment.</p>}
      {authRequired && <p className="bid-notice">Enter the demo access code above to load or run a saved assessment.</p>}
      {error && <div className="analysis-failed" role="alert">{error}</div>}
      {running && <div className="analysis-progress" role="status"><span className="analysis-pulse" /><div><strong>Comparing company capabilities</strong><p>Checking requirements, evidence, and mandatory gaps.</p></div></div>}
      {assessment?.status === "failed" && <div className="analysis-failed"><strong>Assessment needs another attempt</strong><p>{assessment.error_message}</p></div>}
      {result && (
        <div className="assessment-result">
          <div className={`decision ${result.recommendation}`}>
            <span className="eyebrow">{result.company_name} · {result.evaluated_on}</span>
            <h3>{result.recommendation === "bid" ? "Bid" : result.recommendation === "no_bid" ? "No Bid" : "Review Required"}</h3>
            <p>{result.summary}</p>
            <div className="decision-metrics"><strong>{result.score}%<small>Requirements matched</small></strong><strong>{result.coverage}%<small>Evidence coverage</small></strong></div>
          </div>
          {draftChanged && <p className="bid-notice">This result uses the submitted profile snapshot. Reassess to apply your current profile.</p>}
          <details className="profile-snapshot"><summary>View profile used for this result</summary>{FIELDS.map(({ key, label }) => <p key={key}><strong>{label}: </strong>{assessment?.profile?.[key] || "Not provided"}</p>)}</details>
          <p className="profile-note">Match score = met requirements ÷ all assessed requirements. Coverage = met or unmet ÷ all requirements. Required-condition gaps block a Bid; unknown required conditions need review. These are provisional matches to the analysis, not a probability of winning. Review original clauses, deadlines, and commercial risks.</p>
          <div className="comparison-list">
            {result.comparisons.map((item) => (
              <article className="comparison" key={item.requirement_id}>
                <div className="comparison-heading"><strong>{item.label}</strong><span className={`match-status ${item.status}`}>{item.status === "unknown" ? "Unverified" : item.status === "met" ? "Matched" : "Gap"}</span></div>
                <small>{item.category.replaceAll("_", " ")}{item.mandatory ? " · Required condition" : ""}</small>
                <p>{item.requirement}</p><p className="comparison-reason">{item.reason}</p>
                {item.profile_evidence && <blockquote>Company evidence: {item.profile_evidence}</blockquote>}
                <div className="citation-list">{item.page_numbers.map((page) => <button key={page} type="button" onClick={() => onCitation(page)}>Page {page}</button>)}</div>
              </article>
            ))}
            {!result.comparisons.length && <p className="bid-notice">No assessable requirements were found. Review the original tender.</p>}
          </div>
        </div>
      )}
    </section>
  );
}
