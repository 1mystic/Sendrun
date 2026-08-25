"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

function deriveSlug(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function CreateOrgPage() {
  const router = useRouter();
  const [orgName, setOrgName] = useState("");
  const [slug, setSlug] = useState("");

  function handleNameChange(value: string) {
    setOrgName(value);
    setSlug(deriveSlug(value));
  }

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    router.push("/invite");
  }

  return (
    <section>
      <div className="a-brand-lockup">
        <span className="a-mark" /> Sendrun
      </div>
      <h1>Create your organization</h1>
      <p className="lede">
        This is the workspace your team will send from. You can invite people
        and change these details later.
      </p>

      <form onSubmit={handleSubmit}>
        <label className="field-label" htmlFor="co-name">
          Organization name
        </label>
        <input
          className="input"
          style={{ marginBottom: 16 }}
          type="text"
          id="co-name"
          name="orgname"
          placeholder="AI Research Club"
          required
          value={orgName}
          onChange={(e) => handleNameChange(e.target.value)}
        />

        <label className="field-label" htmlFor="co-slug">
          Workspace URL
        </label>
        <input
          className="input"
          type="text"
          id="co-slug"
          name="slug"
          placeholder="ai-research-club"
          required
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
        <div className="a-slug-preview" style={{ marginBottom: 16 }}>
          sendrun.app/<b>{slug || "your-org"}</b>
        </div>

        <label className="field-label" htmlFor="co-size">
          Team size
        </label>
        <select className="input" style={{ marginBottom: 16 }} id="co-size" name="size" required defaultValue="">
          <option value="" disabled>
            Select team size
          </option>
          <option value="1">Just me</option>
          <option value="2-10">2–10 people</option>
          <option value="11-50">11–50 people</option>
          <option value="51-200">51–200 people</option>
          <option value="200+">200+ people</option>
        </select>

        <label className="field-label" htmlFor="co-use">
          What will you use Sendrun for?
        </label>
        <select className="input" style={{ marginBottom: 16 }} id="co-use" name="use" required defaultValue="">
          <option value="" disabled>
            Select a use case
          </option>
          <option value="outreach">Event and speaker outreach</option>
          <option value="fundraising">Fundraising and donor communication</option>
          <option value="product">Product and customer updates</option>
          <option value="internal">Internal team announcements</option>
          <option value="other">Something else</option>
        </select>

        <button className="btn" style={{ width: "100%", textAlign: "center", display: "block" }} type="submit">
          Create organization
        </button>
      </form>
    </section>
  );
}
