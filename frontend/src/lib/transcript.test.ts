import { describe, expect, it } from "vitest";
import { applyVoiceMessage, type TranscriptEntry } from "./transcript";

let n = 0;
const make = (role: TranscriptEntry["role"], content: string): TranscriptEntry => ({
  id: `m${n++}`,
  role,
  content,
});

const say = (role: "user" | "assistant", text: string) =>
  ({ type: "transcript", role, text }) as const;

describe("applyVoiceMessage", () => {
  it("concatène les morceaux d'un même tour dans une seule bulle", () => {
    let list: TranscriptEntry[] = [];
    list = applyVoiceMessage(list, say("user", "Bon"), make);
    list = applyVoiceMessage(list, say("user", "jour"), make);
    expect(list).toHaveLength(1);
    expect(list[0].content).toBe("Bonjour");
  });

  it("ouvre une bulle assistant et clôt celle de l'utilisateur", () => {
    let list: TranscriptEntry[] = [];
    list = applyVoiceMessage(list, say("user", "Salut"), make);
    list = applyVoiceMessage(list, say("assistant", "Hello"), make);
    expect(list.map((m) => [m.role, m.open])).toEqual([
      ["user", false],
      ["assistant", true],
    ]);
  });

  it("démarre une nouvelle bulle après turn_complete", () => {
    let list: TranscriptEntry[] = [];
    list = applyVoiceMessage(list, say("user", "Q1"), make);
    list = applyVoiceMessage(list, { type: "turn_complete" }, make);
    list = applyVoiceMessage(list, say("user", "Q2"), make);
    expect(list.map((m) => m.content)).toEqual(["Q1", "Q2"]);
  });

  it("clôt la réponse en cours quand elle est interrompue", () => {
    let list: TranscriptEntry[] = [];
    list = applyVoiceMessage(list, say("assistant", "Réponse co"), make);
    list = applyVoiceMessage(list, { type: "interrupted" }, make);
    list = applyVoiceMessage(list, say("user", "Stop"), make);
    expect(list.map((m) => m.role)).toEqual(["assistant", "user"]);
  });

  it("ignore les messages d'erreur", () => {
    const list = [make("user", "x")];
    expect(applyVoiceMessage(list, { type: "error", message: "boom" }, make)).toBe(list);
  });
});
