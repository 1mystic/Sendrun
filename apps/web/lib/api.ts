/**
 * The API seam.
 *
 * Pages call these functions rather than `fetch` directly. Today they resolve from
 * the mock data in `mock.ts`; when the FastAPI backend lands, only the bodies here
 * change and no page is touched.
 *
 * `NEXT_PUBLIC_API_URL` decides which path is taken, so the switch is a deploy-time
 * env var rather than a code change.
 */

import { CAMPAIGNS, CONTACTS, PREFLIGHT } from "./mock";
import type { Campaign, Contact, PreflightReport, ProgressSnapshot } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const useMocks = API === "";

async function get<T>(path: string, fallback: T): Promise<T> {
  if (useMocks) return fallback;
  const res = await fetch(`${API}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

export async function listCampaigns(): Promise<Campaign[]> {
  return get("/api/campaigns", CAMPAIGNS);
}

export async function getCampaign(id: string): Promise<Campaign | undefined> {
  return get(`/api/campaigns/${id}`, CAMPAIGNS.find((c) => c.id === id));
}

export async function listContacts(): Promise<Contact[]> {
  return get("/api/contacts", CONTACTS);
}

export async function getContact(id: string): Promise<Contact | undefined> {
  return get(`/api/contacts/${id}`, CONTACTS.find((c) => c.id === id));
}

export async function getPreflight(): Promise<PreflightReport> {
  return get("/api/preflight", PREFLIGHT);
}

/**
 * Subscribe to live campaign progress.
 *
 * The real endpoint is an SSE stream over a 1s Postgres aggregate poll — not a
 * WebSocket. Progress is read from Postgres, never from the durable engine: the
 * engine holds only what to do next, Postgres holds what happened.
 *
 * Returns an unsubscribe function. In mock mode the caller drives its own
 * simulation instead, so this is a no-op.
 */
export function subscribeProgress(
  campaignId: string,
  onUpdate: (snapshot: ProgressSnapshot) => void,
): () => void {
  if (useMocks) return () => {};

  const source = new EventSource(`${API}/api/campaigns/${campaignId}/progress/stream`);
  source.onmessage = (event) => {
    try {
      onUpdate(JSON.parse(event.data) as ProgressSnapshot);
    } catch {
      // A malformed frame should not tear down the stream; the next tick recovers.
    }
  };
  return () => source.close();
}
