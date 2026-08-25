import Link from "next/link";

export default function NotFound() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 20,
        padding: "clamp(28px, 5vw, 64px)",
        textAlign: "center",
      }}
    >
      <div
        className="pill pill-crit"
        style={{ fontSize: ".68rem" }}
      >
        404
      </div>
      <h1
        style={{
          fontSize: "clamp(2rem, 5vw, 3.4rem)",
          fontWeight: 700,
          letterSpacing: "-.04em",
          lineHeight: 1.02,
          margin: 0,
        }}
      >
        This job was never claimed.
      </h1>
      <p
        className="text-muted"
        style={{ maxWidth: "48ch", fontSize: ".96rem", lineHeight: 1.6, margin: 0 }}
      >
        The page you&apos;re looking for doesn&apos;t exist, or its lease
        expired. Nothing was lost — there&apos;s just nothing here.
      </p>
      <Link href="/" className="btn" style={{ marginTop: 10 }}>
        Back to safety
      </Link>
    </div>
  );
}
