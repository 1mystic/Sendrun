"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import StrengthMeter from "../StrengthMeter";
import { signUp } from "@/lib/api";

const GoogleIcon = () => (
  <svg viewBox="0 0 48 48" aria-hidden="true">
    <path fill="#EA4335" d="M24 9.5c3.4 0 6.4 1.2 8.8 3.5l6.6-6.6C35.3 2.5 30.1 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.7 6C12.1 13.1 17.5 9.5 24 9.5z" />
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.6c-.5 3-2.2 5.5-4.7 7.2l7.3 5.7c4.3-4 6.8-9.8 6.8-17.4z" />
    <path fill="#FBBC05" d="M10.3 19.2a14.6 14.6 0 0 0 0 9.6l-7.7 6a24 24 0 0 1 0-21.6z" />
    <path fill="#34A853" d="M24 48c6.1 0 11.3-2 15-5.5l-7.3-5.7c-2 1.4-4.7 2.2-7.7 2.2-6.5 0-12-4.4-13.9-10.3l-7.7 6C6.5 42.6 14.6 48 24 48z" />
  </svg>
);

export default function SignUpPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const name = String(form.get("name") ?? "");
    const email = String(form.get("email") ?? "");

    setSubmitting(true);
    try {
      await signUp(name, email, password);
      router.push("/create-org");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign up failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Create your account</h1>
      <p className="lede">Set up in under a minute. No credit card required to start.</p>

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="su-name">
          Full name
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="text"
          id="su-name"
          name="name"
          placeholder="Ada Lovelace"
          autoComplete="name"
          required
        />

        <label className="field-label" htmlFor="su-email">
          Work email
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="email"
          id="su-email"
          name="email"
          placeholder="you@company.com"
          autoComplete="email"
          required
        />

        <label className="field-label" htmlFor="su-pass">
          Password
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="password"
          id="su-pass"
          name="password"
          placeholder="At least 8 characters"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <StrengthMeter password={password} />

        <label className="a-checkline" htmlFor="su-terms" style={{ marginBottom: 20 }}>
          <input type="checkbox" id="su-terms" name="terms" required />
          I agree to the{" "}
          <a href="#" onClick={(e) => e.stopPropagation()}>
            Terms of Service
          </a>{" "}
          and{" "}
          <a href="#" onClick={(e) => e.stopPropagation()}>
            Privacy Policy
          </a>
        </label>

        {error && (
          <p className="a-footline" style={{ color: "var(--crit, #E4491F)", marginBottom: 12 }}>
            {error}
          </p>
        )}

        <button
          className="btn"
          style={{ width: "100%", textAlign: "center", display: "block" }}
          type="submit"
          disabled={submitting}
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>

        <div className="a-divider">Or</div>

        <button className="btn btn-ghost a-btn-google" style={{ width: "100%" }} type="button">
          <GoogleIcon />
          Continue with Google
        </button>
      </form>

      <p className="a-footline">
        Already have an account? <Link href="/signin">Sign in</Link>
      </p>
    </section>
  );
}
