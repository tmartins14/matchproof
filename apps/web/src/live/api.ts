import type { MatchBrief } from "@/contracts/types";
import type { SourceRef } from "@/desk/deskData";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Why a call failed, in terms the desk has copy for. */
export type Failure = "rate_limit" | "busy" | "rejected" | "unreachable";

export type Result<T> = { ok: true; value: T } | { ok: false; reason: Failure };

export function failureOf(status: number): Failure {
  if (status === 429) return "rate_limit";
  if (status === 503) return "busy";
  if (status === 400 || status === 422) return "rejected";
  return "unreachable";
}

async function call<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<Result<T>> {
  try {
    const reply = await fetch(`${API_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!reply.ok) return { ok: false, reason: failureOf(reply.status) };
    return { ok: true, value: (await reply.json()) as T };
  } catch {
    return { ok: false, reason: "unreachable" };
  }
}

export interface Composed {
  brief: MatchBrief;
  brief_text: string;
  warnings: string[];
}

export const randomMatch = (): Promise<Result<{ match_id: string; brief: MatchBrief }>> => call("POST", "/matches/random", {});
export const composeBrief = (text: string): Promise<Result<Composed>> => call("POST", "/compose", { text });
export const createMatch = (brief: MatchBrief): Promise<Result<{ match_id: string }>> => call("POST", "/matches", brief);

export async function getSource(matchId: string, sourceId: string): Promise<SourceRef | undefined> {
  const result = await call<SourceRef>("GET", `/matches/${encodeURIComponent(matchId)}/sources/${encodeURIComponent(sourceId)}`);
  return result.ok ? result.value : undefined;
}

export const streamUrl = (matchId: string, speed: number): string => `${API_URL}/matches/${encodeURIComponent(matchId)}/stream?speed=${speed}`;
