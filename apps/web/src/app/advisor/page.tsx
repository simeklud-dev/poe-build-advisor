"use client";

import { useState } from "react";

type AnalyzeResponse = {
  meta: Record<string, unknown>;
  summary: Record<string, unknown>;
  commentary: string | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function AdvisorPage() {
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  async function handleAnalyze() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(`${API_URL}/advisor/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail ?? "Analyza selhala.");
      }
      setResult(data as AnalyzeResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 720, margin: "40px auto", padding: "0 16px" }}>
      <h1>Analyza buildu</h1>
      <p style={{ opacity: 0.7 }}>
        Vloz PoB export kod (Path of Building &rarr; Export Build &rarr; Generate code) -- ne odkaz na
        pobb.in/pastebin, ten se automaticky nestahuje.
      </p>
      <textarea
        value={code}
        onChange={(e) => setCode(e.target.value)}
        rows={8}
        style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace" }}
        placeholder="eNrtXVtv...="
      />
      <div style={{ marginTop: 12 }}>
        <button onClick={handleAnalyze} disabled={loading || !code.trim()}>
          {loading ? "Pocitam..." : "Analyzovat"}
        </button>
      </div>

      {error && (
        <p style={{ color: "#ff8080", marginTop: 16 }}>
          Chyba: {error}
        </p>
      )}

      {result && (
        <div style={{ marginTop: 24 }}>
          {result.commentary && (
            <p style={{ background: "#1c1c1c", padding: 12, borderRadius: 6 }}>{result.commentary}</p>
          )}
          <h2>Staty (z realneho PoB enginu)</h2>
          <pre style={{ whiteSpace: "pre-wrap", background: "#1c1c1c", padding: 12, borderRadius: 6, overflowX: "auto" }}>
            {JSON.stringify(result.summary, null, 2)}
          </pre>
        </div>
      )}
    </main>
  );
}
