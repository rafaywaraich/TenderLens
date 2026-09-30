import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "TenderLens",
  description: "Evidence-backed RFP intelligence",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

