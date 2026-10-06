import { ReactNode } from "react";

export default function WarningNotice({ title, children }: { title: string; children: ReactNode }) {
  return <div className="warning-notice" role="status">
    <svg className="warning-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 3 2 21h20L12 3Z" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M12 9v5m0 3v.1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
    <div><strong className="warning-title">{title}</strong><div className="warning-message">{children}</div></div>
  </div>;
}
