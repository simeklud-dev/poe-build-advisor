import Link from "next/link";

export default function Home() {
  return (
    <main style={{ maxWidth: 640, margin: "80px auto", padding: "0 16px" }}>
      <h1>PoE Build Advisor</h1>
      <p>AI bot nad skutecnym Path of Building enginem -- vloz export kod a dostanes rozbor buildu.</p>
      <p>
        <Link href="/advisor" style={{ color: "#8ab4ff" }}>
          Otevrit analyzu buildu &rarr;
        </Link>
      </p>
      <p style={{ opacity: 0.6, fontSize: 14 }}>
        Tento web neni pridruzeny ke Grinding Gear Games ani jimi podporovan.
      </p>
    </main>
  );
}
