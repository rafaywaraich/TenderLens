"use client";
import { useEffect, useRef, useState } from "react";

export default function ReportPanel({ apiUrl, documentId, accessCode, analysisReady }: {
  apiUrl: string; documentId: string; accessCode: string; analysisReady: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [includeCompany, setIncludeCompany] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function download() {
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError(null);
    try {
      const response = await fetch(`${apiUrl}/documents/${documentId}/report?include_company=${includeCompany}`, {
        signal: abort.signal, cache: "no-store",
        headers: accessCode ? { "X-Demo-Access-Code": accessCode } : {},
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        if (response.status === 401) throw new Error("Enter a valid demo access code in the upload card at the top, then retry the download.");
        throw new Error(typeof body?.detail === "string" ? body.detail : "Could not download the report.");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url; link.download = "tenderlens-report.pdf";
      document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) {
      if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "Download failed.");
    } finally { if (!abort.signal.aborted) setBusy(false); }
  }
  return <section className="report-panel" id="report" aria-labelledby="report-title">
    <div className="section-intro"><span className="step-number" aria-hidden="true">↓</span><div>
      <span className="eyebrow">Take it with you</span><h3 id="report-title">Your decision, documented.</h3>
      <p>Download a clean PDF brief with saved findings, source page references and company-fit guidance.</p>
    </div></div>
    <div className="report-body">
      <div className="report-preview" aria-hidden="true"><span>TL / REPORT</span><i /><i /><i /><div>Evidence → Clarity</div></div>
      <div><h4>A shareable procurement brief</h4>
        <p className="muted">Overview · deadlines · requirements · risks · fit score · gaps · profile snapshot</p>
        <label className="report-option"><input type="checkbox" checked={includeCompany}
          onChange={event => setIncludeCompany(event.target.checked)} disabled={busy} /> Include saved company assessment, if available</label>
        <p className="profile-note">Exports the saved snapshot, not unsaved edits. Company details are self-reported. Keep downloaded reports private. Q&A history is not included.</p>
        <button className="primary-button" disabled={!analysisReady || busy} onClick={download} type="button">
          {busy ? "Preparing PDF…" : "↓ Download PDF report"}</button>
        {!analysisReady && <p className="bid-notice">Complete Analyze tender to enable export.</p>}
        {error && <div className="error" role="alert"><p>{error}</p><a href="#access-code" onClick={() => document.getElementById("access-code")?.focus()}>Go to demo access code ↑</a></div>}
      </div>
    </div>
  </section>;
}
