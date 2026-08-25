"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import StrengthMeter from "../StrengthMeter";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");

  const showMatch = confirm.length > 0;
  const matches = password === confirm;
  const canSubmit = !showMatch || matches;

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    router.push("/signin");
  }

  return (
    <section>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Choose a new password</h1>
      <p className="lede">Your new password must be different from your previous password.</p>

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="rp-pass">
          New password
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="password"
          id="rp-pass"
          name="password"
          placeholder="At least 8 characters"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <StrengthMeter password={password} />

        <label className="field-label" htmlFor="rp-confirm">
          Confirm new password
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="password"
          id="rp-confirm"
          name="confirm"
          placeholder="Re-enter your password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        <div
          className={`a-matchmsg ${showMatch ? "show" : ""} ${matches ? "ok" : "err"}`}
          style={{ marginTop: -10 }}
        >
          <span>{matches ? "✓" : "✕"}</span>
          <span>
            {matches ? "Passwords match." : "Passwords don't match. Re-check the confirm field."}
          </span>
        </div>

        <div style={{ height: 6 }} />
        <button
          className="btn"
          style={{ width: "100%", textAlign: "center", display: "block" }}
          type="submit"
          disabled={!canSubmit}
        >
          Reset password
        </button>
      </form>
    </section>
  );
}
