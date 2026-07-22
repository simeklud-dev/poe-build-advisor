"use client";

import Link from "next/link";
import { useState } from "react";

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

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleStartFreeChat() {
    setSessionLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/advisor/freechat`, { method: "POST" });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const data = await response.json();
      setSessionId(data.session_id);
      setMessages([]);
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
      const response = await fetch(`${API_URL}/advisor/freechat/${sessionId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userText }),
      });
      if (!response.ok) {
        throw new Error(await readErrorDetail(response));
      }
      const data = await response.json();
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setChatLoading(false);
    }
  }

  function handleResetFreeChat() {
    if (sessionId) {
      fetch(`${API_URL}/advisor/freechat/${sessionId}`, { method: "DELETE" }).catch(() => {});
    }
    setSessionId(null);
    setMessages([]);
  }

  return (
    <main style={{ maxWidth: 720, margin: "40px auto 80px", padding: "0 16px" }}>
      <h1>PoE Build Advisor</h1>
      <p>AI bot nad skutecnym Path of Building enginem -- vloz export kod a dostanes rozbor buildu.</p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 16,
          marginTop: 24,
        }}
      >
        <div style={{ background: "rgba(28,28,28,0.85)", border: "1px solid #333", borderRadius: 8, padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Mám PoB build</h3>
          <p style={{ opacity: 0.7, fontSize: 14 }}>
            Vloz export kod a dostanes rozbor nad realnym PoB enginem, nebo rovnou spust chat s AI poradcem, ktery
            si nad tvym buildem overuje upravy.
          </p>
          <Link href="/advisor" style={{ color: "#8ab4ff" }}>
            Otevrit analyzu buildu &rarr;
          </Link>
        </div>

        <div style={{ background: "rgba(28,28,28,0.85)", border: "1px solid #333", borderRadius: 8, padding: 16 }}>
          <h3 style={{ marginTop: 0 }}>Jeste nemam build</h3>
          <p style={{ opacity: 0.7, fontSize: 14 }}>
            Rekni, jaky skill chces hrat a co od buildu cekas ("chci Elemental Hit, hodne damage, rychly clear,
            defenziva me nezajima") -- AI ti navrhne koncept i bez nahraneho buildu.
          </p>
          {!sessionId && (
            <button onClick={handleStartFreeChat} disabled={sessionLoading}>
              {sessionLoading ? "Zakladam..." : "Zacit chat bez buildu"}
            </button>
          )}
        </div>
      </div>

      {error && <p style={{ color: "#ff8080", marginTop: 16 }}>Chyba: {error}</p>}

      {sessionId && (
        <div style={{ marginTop: 24 }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={handleResetFreeChat}>Zavrit chat</button>
          </div>
          <div
            style={{
              marginTop: 12,
              border: "1px solid #333",
              borderRadius: 6,
              padding: 12,
              minHeight: 200,
              background: "rgba(17,17,17,0.85)",
            }}
          >
            {messages.length === 0 && (
              <p style={{ opacity: 0.5 }}>Napis napr. &quot;chci hrat Elemental Hit, hodne damage a rychly clear&quot;.</p>
            )}
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 10 }}>
                <strong>{m.role === "user" ? "Ty" : "AI"}:</strong>{" "}
                <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
              </div>
            ))}
            {chatLoading && <p style={{ opacity: 0.5 }}>AI premysli...</p>}
          </div>

          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
              style={{ flex: 1 }}
              placeholder="Napr. chci hrat skill Elemental Hit, navrhni mi build..."
              disabled={chatLoading}
            />
            <button onClick={handleSendChat} disabled={chatLoading || !chatInput.trim()}>
              Poslat
            </button>
          </div>
        </div>
      )}

      <p style={{ opacity: 0.6, fontSize: 14, marginTop: 32 }}>
        Tento web neni pridruzeny ke Grinding Gear Games ani jimi podporovan.
      </p>
    </main>
  );
}
