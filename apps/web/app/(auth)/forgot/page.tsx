"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    router.push(`/check-email?email=${encodeURIComponent(email)}`);
  }

  return (
    <section>
      <Link className="a-backlink" href="/signin">
        &larr; Back to sign in
      </Link>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Reset your password</h1>
      <p className="lede">
        Enter the email address on your account and we&apos;ll send you a link to
        reset your password. The link expires in 30 minutes.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="fp-email">
          Email
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="email"
          id="fp-email"
          name="email"
          placeholder="you@company.com"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <button className="btn" style={{ width: "100%", textAlign: "center", display: "block" }} type="submit">
          Send reset link
        </button>
      </form>

      <p className="a-footline">
        <Link href="/signin">Remembered your password? Sign in</Link>
      </p>
    </section>
  );
}
