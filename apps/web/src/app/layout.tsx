import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PoE Build Advisor",
  description: "Analyza Path of Building buildu nad realnym PoB enginem.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#111", color: "#eee" }}>
        {children}
      </body>
    </html>
  );
}
