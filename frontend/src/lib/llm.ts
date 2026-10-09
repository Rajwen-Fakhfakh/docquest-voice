import { MAX_HISTORY, type ChatTurn } from "./chat";

// Appelle le proxy Next /api/chat et transmet chaque morceau de texte à `onChunk`
// dès qu'il arrive. Renvoie la réponse complète.
export async function streamLlm(
  messages: ChatTurn[],
  onChunk: (text: string) => void
): Promise<string> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: messages.slice(-MAX_HISTORY) }),
  });

  if (!res.ok || !res.body) {
    throw new Error(`LLM request failed with status ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let answer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value, { stream: true });
    if (text) {
      answer += text;
      onChunk(text);
    }
  }
  return answer;
}
