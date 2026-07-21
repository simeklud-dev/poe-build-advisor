"use client";

import { useState } from "react";

type Summary = Record<string, unknown>;

function num(summary: Summary, key: string): number | undefined {
  const v = summary[key];
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function fmt(n: number | undefined, decimals = 0): string {
  if (n === undefined) return "?";
  return n.toLocaleString("cs-CZ", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtPercent(n: number | undefined, decimals = 0): string {
  if (n === undefined) return "?";
  return `${fmt(n, decimals)} %`;
}

function resistColor(v: number | undefined): string {
  if (v === undefined) return "#eee";
  if (v < 0) return "#ff6b6b";
  if (v < 75) return "#ffb86b";
  return "#8fd16a";
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "4px 0" }}>
      <span style={{ opacity: 0.65 }}>{label}</span>
      <span style={{ fontWeight: 600, color: color ?? "#eee" }}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#1c1c1c", padding: "12px 16px", borderRadius: 6 }}>
      <h3 style={{ margin: "0 0 8px", fontSize: 14, opacity: 0.8, textTransform: "uppercase", letterSpacing: 0.5 }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

// PoB's own output table (dumped raw by the bridge -- see pob-bridge.lua
// sanitize()) uses ~630 flat keys with PoB's internal naming, not a nested
// shape -- this picks out the handful a player actually reads at a glance
// (mirrors the desktop app's left-hand stat panel) instead of the full dump.
export function StatsPanel({ summary }: { summary: Summary }) {
  const [showRaw, setShowRaw] = useState(false);

  const life = num(summary, "Life");
  const lifeUnreserved = num(summary, "LifeUnreserved");
  const es = num(summary, "EnergyShield");
  const mana = num(summary, "Mana");
  const manaUnreserved = num(summary, "ManaUnreserved");

  const armour = num(summary, "Armour");
  const evasion = num(summary, "Evasion");
  const block = num(summary, "BlockChance");
  const spellBlock = num(summary, "SpellBlockChance");
  const moveSpeedMod = num(summary, "MovementSpeedMod");

  const fireRes = num(summary, "FireResist");
  const coldRes = num(summary, "ColdResist");
  const lightningRes = num(summary, "LightningResist");
  const chaosRes = num(summary, "ChaosResist");

  const dps = num(summary, "FullDPS") || num(summary, "CombinedDPS") || num(summary, "TotalDPS");
  const ehp = num(summary, "TotalEHP");
  const physMaxHit = num(summary, "PhysicalMaximumHitTaken");

  const strength = num(summary, "Strength");
  const dexterity = num(summary, "Dexterity");
  const intelligence = num(summary, "Intelligence");

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
      <Section title="Zivoty a mana">
        <Stat label="Life" value={life !== undefined ? `${fmt(life)}${lifeUnreserved !== undefined && lifeUnreserved !== life ? ` (${fmt(lifeUnreserved)} volnych)` : ""}` : "?"} />
        <Stat label="Energy Shield" value={fmt(es)} />
        <Stat label="Mana" value={mana !== undefined ? `${fmt(mana)}${manaUnreserved !== undefined && manaUnreserved !== mana ? ` (${fmt(manaUnreserved)} volnych)` : ""}` : "?"} />
        {ehp !== undefined && <Stat label="Total EHP" value={fmt(ehp)} />}
      </Section>

      <Section title="Obrana">
        <Stat label="Armour" value={fmt(armour)} />
        <Stat label="Evasion" value={fmt(evasion)} />
        <Stat label="Block Chance" value={fmtPercent(block)} />
        <Stat label="Spell Block" value={fmtPercent(spellBlock)} />
        {moveSpeedMod !== undefined && (
          <Stat label="Movement Speed" value={`${moveSpeedMod >= 1 ? "+" : ""}${fmt((moveSpeedMod - 1) * 100)} %`} />
        )}
      </Section>

      <Section title="Resistance">
        <Stat label="Fire" value={fmtPercent(fireRes)} color={resistColor(fireRes)} />
        <Stat label="Cold" value={fmtPercent(coldRes)} color={resistColor(coldRes)} />
        <Stat label="Lightning" value={fmtPercent(lightningRes)} color={resistColor(lightningRes)} />
        <Stat label="Chaos" value={fmtPercent(chaosRes)} color={resistColor(chaosRes)} />
      </Section>

      <Section title="Utok">
        <Stat label="DPS" value={fmt(dps, dps !== undefined && dps < 100 ? 1 : 0)} />
        {physMaxHit !== undefined && <Stat label="Max Hit (physical)" value={fmt(physMaxHit)} />}
        {(strength !== undefined || dexterity !== undefined || intelligence !== undefined) && (
          <Stat
            label="Atributy"
            value={`${fmt(strength)} / ${fmt(dexterity)} / ${fmt(intelligence)}`}
          />
        )}
      </Section>

      <div style={{ gridColumn: "1 / -1" }}>
        <button onClick={() => setShowRaw((v) => !v)} style={{ fontSize: 13, opacity: 0.7 }}>
          {showRaw ? "Skryt" : "Zobrazit"} vsechna surova data z PoB enginu ({Object.keys(summary).length} hodnot)
        </button>
        {showRaw && (
          <pre
            style={{
              whiteSpace: "pre-wrap",
              background: "#1c1c1c",
              padding: 12,
              borderRadius: 6,
              overflowX: "auto",
              marginTop: 8,
              maxHeight: 400,
              overflowY: "auto",
            }}
          >
            {JSON.stringify(summary, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}
