import { describe, expect, it } from "vitest";
import { pageUrl, splitCitations } from "./citations";

describe("splitCitations", () => {
  it("transforme chaque page citée en segment", () => {
    expect(splitCitations("Dividende de 3,01 € (p. 12, 40)")).toEqual([
      { kind: "text", text: "Dividende de 3,01 € (p. " },
      { kind: "page", page: 12 },
      { kind: "text", text: ", " },
      { kind: "page", page: 40 },
      { kind: "text", text: ")" },
    ]);
  });

  it("reconstitue le texte d'origine", () => {
    const text = "A (p. 3) puis B (pp. 10 - 12 ) fin";
    const joined = splitCitations(text)
      .map((s) => (s.kind === "page" ? String(s.page) : s.text))
      .join("");
    expect(joined).toBe(text);
  });

  it("reconnaît les pages dites à l'oral dans la transcription vocale", () => {
    const text = "Le dividende est de 3,40 euros. Page 495, page 57 et page 425.";
    const segments = splitCitations(text);
    expect(segments.filter((s) => s.kind === "page")).toEqual([
      { kind: "page", page: 495 },
      { kind: "page", page: 57 },
      { kind: "page", page: 425 },
    ]);
    const joined = segments.map((s) => (s.kind === "page" ? String(s.page) : s.text)).join("");
    expect(joined).toBe(text);
  });

  it("reconnaît une page isolée en fin de phrase", () => {
    expect(splitCitations("Baisse de 4 912 millions. Page 52.")).toEqual([
      { kind: "text", text: "Baisse de 4 912 millions. Page " },
      { kind: "page", page: 52 },
      { kind: "text", text: "." },
    ]);
  });

  it("laisse intact un texte sans citation", () => {
    expect(splitCitations("Bonjour (voir ci-dessus)")).toEqual([
      { kind: "text", text: "Bonjour (voir ci-dessus)" },
    ]);
  });
});

describe("pageUrl", () => {
  it("ouvre le PDF à la page demandée", () => {
    expect(pageUrl("/deu2025.pdf", 12)).toBe("/deu2025.pdf#page=12");
  });
});
