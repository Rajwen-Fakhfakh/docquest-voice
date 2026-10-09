"use server";

import { MAX_HISTORY, type ChatResponse, type ChatTurn } from "./chat";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

export async function callLlm(messages: ChatTurn[]): Promise<string> {
  const res = await fetch(new URL("/chat", API_URL), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: messages.slice(-MAX_HISTORY) }),
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`LLM request failed with status ${res.status}`);
  }

  const data = (await res.json()) as ChatResponse;
  return data.answer;
}
