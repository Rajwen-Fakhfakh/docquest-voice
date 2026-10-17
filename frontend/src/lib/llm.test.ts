import { afterEach, describe, expect, it, vi } from "vitest";
import { RateLimitedError, streamLlm } from "./llm";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

afterEach(() => {
  vi.clearAllMocks();
});

function streamOf(...parts: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part));
      controller.close();
    },
  });
}

describe("streamLlm", () => {
  it("envoie l'historique en JSON à /api/chat et relaie chaque morceau", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      body: streamOf("Bon", "jour", " !"),
    });
    const onChunk = vi.fn();

    const answer = await streamLlm(
      [
        { role: "user", content: "Salut" },
        { role: "assistant", content: "Hello" },
        { role: "user", content: "Qui es-tu ?" },
      ],
      onChunk
    );

    expect(answer).toBe("Bonjour !");
    expect(onChunk.mock.calls.map(([t]) => t)).toEqual(["Bon", "jour", " !"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      messages: [
        { role: "user", content: "Salut" },
        { role: "assistant", content: "Hello" },
        { role: "user", content: "Qui es-tu ?" },
      ],
    });
  });

  it("ne garde que les 50 derniers messages (limite du backend)", async () => {
    fetchMock.mockResolvedValue({ ok: true, body: streamOf("ok") });
    const many = Array.from({ length: 60 }, (_, i) => ({
      role: i % 2 === 0 ? ("user" as const) : ("assistant" as const),
      content: `m${i}`,
    }));
    many.push({ role: "user", content: "fin" });

    await streamLlm(many, () => {});

    const sent = JSON.parse(fetchMock.mock.calls[0][1].body).messages;
    expect(sent).toHaveLength(50);
    expect(sent[49]).toEqual({ role: "user", content: "fin" });
  });

  it("lève une erreur quand le backend répond en erreur", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502, body: null });

    await expect(
      streamLlm([{ role: "user", content: "hi" }], () => {})
    ).rejects.toThrow("502");
  });

  it("lève RateLimitedError quand le backend répond 429", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 429, body: null });

    await expect(
      streamLlm([{ role: "user", content: "hi" }], () => {})
    ).rejects.toBeInstanceOf(RateLimitedError);
  });
});
