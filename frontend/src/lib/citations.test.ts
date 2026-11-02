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

describe("splitCitations : nombres en toutes lettres", () => {
  const pagesOf = (text: string) =>
    splitCitations(text).flatMap((s) => (s.kind === "page" ? [s.page] : []));

  it("reconnaît la liste dite par Gemini Live", () => {
    const text =
      "Page dix-sept, cent soixante-quatorze, cent soixante-quinze, trois cent deux et trois cent quatre.";
    expect(pagesOf(text)).toEqual([17, 174, 175, 302, 304]);
    expect(splitCitations(text).at(-1)).toEqual({ kind: "text", text: "." });
  });

  it("garde le texte autour et les séparateurs inchangés", () => {
    const text = "Voir page dix-sept, cent soixante-quatorze et trois cent deux pour le détail.";
    expect(splitCitations(text)).toEqual([
      { kind: "text", text: "Voir page " },
      { kind: "page", page: 17 },
      { kind: "text", text: ", " },
      { kind: "page", page: 174 },
      { kind: "text", text: " et " },
      { kind: "page", page: 302 },
      { kind: "text", text: " pour le détail." },
    ]);
  });

  it("distingue « et » interne (vingt et un) et « et » de liste", () => {
    expect(pagesOf("page quatre-vingt-dix-sept et page soixante et onze")).toEqual([97, 71]);
    expect(pagesOf("page vingt et un et trente et une")).toEqual([21, 31]);
    expect(pagesOf("pages douze et quinze")).toEqual([12, 15]);
  });

  it("lit les centaines et les milliers", () => {
    expect(pagesOf("page quatre cent vingt")).toEqual([420]);
    expect(pagesOf("page deux cents")).toEqual([200]);
    expect(pagesOf("page cent")).toEqual([100]);
    expect(pagesOf("page quatre-vingts")).toEqual([80]);
    expect(pagesOf("page mille deux cent trente-quatre")).toEqual([1234]);
    expect(pagesOf("page deux mille")).toEqual([2000]);
  });

  it("accepte les accents, la casse et les séparateurs variés", () => {
    expect(pagesOf("Page ZÉRO")).toEqual([0]);
    expect(pagesOf("pages douze-quinze")).toEqual([12, 15]);
    expect(pagesOf("pages douze – quinze ; vingt")).toEqual([12, 15, 20]);
    expect(pagesOf("page 12 et page quarante")).toEqual([12, 40]);
    expect(pagesOf("page quarante et page 12")).toEqual([40, 12]);
  });

  it("n'invente pas de lien sans nombre valide", () => {
    for (const text of [
      "Une page de garde.",
      "La page suivante est vide.",
      "Une page blanche",
      "page six mois",
      "Une page un peu longue",
      "page",
    ]) {
      expect(splitCitations(text)).toEqual([{ kind: "text", text }]);
    }
  });

  it("s'arrête au premier mot qui n'est pas un nombre", () => {
    expect(splitCitations("page vingt-trois de garde")).toEqual([
      { kind: "text", text: "page " },
      { kind: "page", page: 23 },
      { kind: "text", text: " de garde" },
    ]);
  });
});

describe("pageUrl", () => {
  it("ouvre le PDF à la page demandée", () => {
    expect(pageUrl("/deu2025.pdf", 12)).toBe("/deu2025.pdf#page=12");
  });
});
