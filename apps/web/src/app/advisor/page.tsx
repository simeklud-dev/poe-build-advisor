"use client";

import { useState } from "react";

type AnalyzeResponse = {
  meta: Record<string, unknown>;
  summary: Record<string, unknown>;
  commentary: string | null;
};

type SessionResponse = {
  session_id: string;
  meta: Record<string, unknown>;
  summary: Record<string, unknown>;
};

type ChatMessage = { role: "user" | "assistant"; text: string };

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail ?? `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}

export default function AdvisorPage() {
  const [code, setCode] = useState("");
  const [analyzeLoading, setAnalyzeLoading] = useState(false);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [exportedCode, setExportedCode] = useState<string | null>(null);

  async function handleAnalyze() {
    setAnalyzeLoading(true);
    setError(null);
    setResult(null);
    try {
      const response = await fetch(`${API_URL}/advisor/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      setResult((await response.json()) as AnalyzeResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAnalyzeLoading(false);
    }
  }

  async function handleStartChat() {
    setSessionLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/advisor/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const data = (await response.json()) as SessionResponse;
      setSessionId(data.session_id);
      setSummary(data.summary);
      setMessages([]);
      setExportedCode(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSessionLoading(false);
    }
  }

  async function handleSendChat() {
    if (!sessionId || !chatInput.trim()) return;
    const userText = chatInput.trim();
    setMessages((prev) => [...prev, { role: "user", text: userText }]);
    setChatInput("");
    setChatLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/advisor/session/${sessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const data = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply }]);
      setSummary(data.summary);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChatLoading(false);
    }
  }

  async function handleExport() {
    if (!sessionId) return;
    setError(null);
    try {
      const response = await fetch(`${API_URL}/advisor/session/${sessionId}/export`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const data = await response.json();
      setExportedCode(data.code);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function handleReset() {
    if (sessionId) {
      fetch(`${API_URL}/advisor/session/${sessionId}`, { method: "DELETE" }).catch(() => {});
    }
    setSessionId(null);
    setSummary(null);
    setMessages([]);
    setExportedCode(null);
    setResult(null);
  }

  return (
    <main style={{ maxWidth: 760, margin: "40px auto", padding: "0 16px" }}>
      <h1>Analyza buildu</h1>
      <p style={{ opacity: 0.7 }}>
        Vloz PoB export kod (Path of Building &rarr; Export Build &rarr; Generate code) -- ne odkaz na
        pobb.in/pastebin, ten se automaticky nestahuje.
      </p>

      {!sessionId && (
        <>
          <textarea
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={8}
            style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace" }}
            placeholder="eNrtXVtv...="
          />
          <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
            <button onClick={handleAnalyze} disabled={analyzeLoading || sessionLoading || !code.trim()}>
              {analyzeLoading ? "Pocitam..." : "Rychla analyza"}
            </button>
            <button onClick={handleStartChat} disabled={analyzeLoading || sessionLoading || !code.trim()}>
              {sessionLoading ? "Zakladam..." : "Spustit chat s AI poradcem"}
            </button>
          </div>
        </>
      )}

      {error && <p style={{ color: "#ff8080", marginTop: 16 }}>Chyba: {error}</p>}

      {result && !sessionId && (
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

      {sessionId && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ opacity: 0.7, fontSize: 14 }}>
              TotalDPS: {String(summary?.TotalDPS ?? "?")} &middot; Life: {String(summary?.Life ?? "?")} &middot;
              EnergyShield: {String(summary?.EnergyShield ?? "?")}
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={handleExport}>Stahnout upraveny kod</button>
              <button onClick={handleReset}>Novy build</button>
            </div>
          </div>

          <div style={{ marginTop: 16, border: "1px solid #333", borderRadius: 6, padding: 12, minHeight: 200 }}>
            {messages.length === 0 && (
              <p style={{ opacity: 0.5 }}>Napis napr. &quot;chci vic DPS, ale nechci ztratit resisty&quot;.</p>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <strong>{m.role === "user" ? "Ty" : "AI"}:</strong>{" "}
                <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
              </div>
            ))}
            {chatLoading && <p style={{ opacity: 0.5 }}>AI zkousi varianty na realnem enginu...</p>}
          </div>

          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
              style={{ flex: 1 }}
              placeholder="Zeptej se na cokoliv o buildu..."
              disabled={chatLoading}
            />
            <button onClick={handleSendChat} disabled={chatLoading || !chatInput.trim()}>
              Poslat
            </button>
          </div>

          {exportedCode && (
            <div style={{ marginTop: 16 }}>
              <h3>Novy PoB kod</h3>
              <textarea
                readOnly
                value={exportedCode}
                rows={6}
                style={{ width: "100%", boxSizing: "border-box", fontFamily: "monospace" }}
              />
            </div>
          )}
        </div>
      )}
    </main>
  );
}
