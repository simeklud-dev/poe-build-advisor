import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "PoE Build Advisor",
  description: "Analyza Path of Building buildu nad realnym PoB enginem.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body
        style={{
          fontFamily: "system-ui, sans-serif",
          margin: 0,
          minHeight: "100vh",
          color: "#eee",
          backgroundColor: "#0a0a0a",
          backgroundImage: "linear-gradient(rgba(8,8,10,0.72), rgba(8,8,10,0.82)), url(/background.png)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          backgroundAttachment: "fixed",
          backgroundRepeat: "no-repeat",
        }}
      >
        <header
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 8,
            padding: "24px 16px 0",
          }}
        >
          <Link href="/">
            <img src="/poe-logo.png" alt="Path of Exile" style={{ height: 72, width: "auto" }} />
          </Link>
          <a
            href="https://poe-builds-hub.up.railway.app"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "#8ab4ff", fontSize: 14 }}
          >
            Hledáš hotové buildy? Zkus poe-build-finder &rarr;
          </a>
        </header>
        {children}
      </body>
    </html>
  );
}
