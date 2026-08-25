"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

const RESEND_SECONDS = 45;

function ResendTimer() {
  const [seconds, setSeconds] = useState(RESEND_SECONDS);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setSeconds((s) => (s > 0 ? s - 1 : 0));
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const ready = seconds <= 0;

  function handleResend() {
    if (!ready) return;
    setSeconds(RESEND_SECONDS);
  }

  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  const label = `${m}:${s < 10 ? "0" : ""}${s}`;

  return (
    <div className="card" style={{ marginBottom: 20 }}>
      <div className="a-resend-row">
        <span>Didn&apos;t get it?</span>
        <button
          type="button"
          className={ready ? "ready" : undefined}
          disabled={!ready}
          onClick={handleResend}
        >
          {ready ? "Resend email" : (
            <>
              Resend in <span className="num">{label}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function CheckEmailContent() {
  const params = useSearchParams();
  const email = params.get("email") || "you@company.com";

  return (
    <section>
      <Link className="a-backlink" href="/forgot">
        &larr; Use a different email
      </Link>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Check your email</h1>
      <p className="lede">
        We sent a password reset link to{" "}
        <b style={{ color: "var(--color-paper)" }}>{email}</b>. Click the link
        in that email to choose a new password.
      </p>

      <ResendTimer />

      <p className="hint" style={{ fontSize: ".72rem", lineHeight: 1.6 }}>
        Also check your spam or promotions folder — the message is sent from
        notify@sendrun.app and can occasionally be filtered there.
      </p>

      <p className="a-footline">
        <Link href="/signin">Back to sign in</Link>
      </p>
    </section>
  );
}

export default function CheckEmailPage() {
  return (
    <Suspense fallback={null}>
      <CheckEmailContent />
    </Suspense>
  );
}
