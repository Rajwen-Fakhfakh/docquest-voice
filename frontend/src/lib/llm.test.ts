import { afterEach, describe, expect, it, vi } from "vitest";
import { callLlm } from "./llm";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

afterEach(() => {
  vi.clearAllMocks();
});

describe("callLlm", () => {
  it("envoie l'historique en JSON à POST /chat et renvoie la réponse", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "Bonjour !" }),
    });

    const answer = await callLlm([
      { role: "user", content: "Salut" },
      { role: "assistant", content: "Hello" },
      { role: "user", content: "Qui es-tu ?" },
    ]);

    expect(answer).toBe("Bonjour !");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toBe("http://localhost:8000/chat");
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
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ answer: "ok" }),
    });
    const many = Array.from({ length: 60 }, (_, i) => ({
      role: i % 2 === 0 ? ("user" as const) : ("assistant" as const),
      content: `m${i}`,
    }));
    // 60 messages : le dernier (index 59) est « assistant », on termine par un user.
    many.push({ role: "user", content: "fin" });

    await callLlm(many);

    const sent = JSON.parse(fetchMock.mock.calls[0][1].body).messages;
    expect(sent).toHaveLength(50);
    expect(sent[49]).toEqual({ role: "user", content: "fin" });
  });

  it("lève une erreur quand le backend répond en erreur", async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 502 });

    await expect(
      callLlm([{ role: "user", content: "hi" }])
    ).rejects.toThrow("502");
  });
});
