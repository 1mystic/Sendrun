"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ClipboardEvent, type FormEvent, type KeyboardEvent } from "react";

const DIGIT_COUNT = 6;

export default function TwoFactorPage() {
  const router = useRouter();
  const [digits, setDigits] = useState<string[]>(Array(DIGIT_COUNT).fill(""));
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    const t = setTimeout(() => inputRefs.current[0]?.focus(), 30);
    return () => clearTimeout(t);
  }, []);

  function setDigitAt(idx: number, value: string) {
    setDigits((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  }

  function handleChange(idx: number, raw: string) {
    const clean = raw.replace(/[^0-9]/g, "").slice(0, 1);
    setDigitAt(idx, clean);
    if (clean && idx < DIGIT_COUNT - 1) {
      inputRefs.current[idx + 1]?.focus();
    }
  }

  function handleKeyDown(idx: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !digits[idx] && idx > 0) {
      inputRefs.current[idx - 1]?.focus();
    }
  }

  function handlePaste(idx: number, e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData("text");
    const digitsPasted = (text || "").replace(/[^0-9]/g, "").slice(0, DIGIT_COUNT);
    if (digitsPasted.length > 1) {
      e.preventDefault();
      setDigits((prev) => {
        const next = [...prev];
        digitsPasted.split("").forEach((d, i) => {
          if (i < DIGIT_COUNT) next[i] = d;
        });
        return next;
      });
      const nextIdx = digitsPasted.length < DIGIT_COUNT ? digitsPasted.length : DIGIT_COUNT - 1;
      inputRefs.current[nextIdx]?.focus();
    }
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    router.push("/app");
  }

  return (
    <section>
      <Link className="a-backlink" href="/signin">
        &larr; Back to sign in
      </Link>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Enter verification code</h1>
      <p className="lede">
        We sent a 6-digit code to your authenticator app. Enter it below to
        finish signing in.
      </p>

      <form onSubmit={handleSubmit}>
        <fieldset style={{ border: 0, padding: 0, margin: "0 0 6px" }}>
          <legend
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: ".61rem",
              letterSpacing: ".12em",
              textTransform: "uppercase",
              color: "var(--muted)",
              marginBottom: 6,
              padding: 0,
            }}
          >
            6-digit code
          </legend>
          <div className="a-otp-row">
            {digits.map((digit, idx) => (
              <input
                key={idx}
                ref={(el) => {
                  inputRefs.current[idx] = el;
                }}
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={1}
                aria-label={`Digit ${idx + 1} of ${DIGIT_COUNT}`}
                value={digit}
                onChange={(e) => handleChange(idx, e.target.value)}
                onKeyDown={(e) => handleKeyDown(idx, e)}
                onPaste={(e) => handlePaste(idx, e)}
              />
            ))}
          </div>
        </fieldset>

        <button className="btn" style={{ width: "100%", textAlign: "center", display: "block", marginTop: 6 }} type="submit">
          Verify and continue
        </button>
      </form>

      <p className="a-footline">
        <a href="#">Use a recovery code instead</a>
      </p>
    </section>
  );
}
