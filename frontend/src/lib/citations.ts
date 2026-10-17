export type Segment =
  | { kind: "text"; text: string }
  | { kind: "page"; page: number };

// Le backend demande au modèle de citer « (p. 12, 40) ». Les numéros sont ceux des pages du PDF.
const CITATION = /\(pp?\.\s*(\d+(?:\s*(?:,|;|et|-|–)\s*\d+)*)\s*\)/g;

/** Découpe un texte en morceaux de texte et en pages citées (pour en faire des liens vers le PDF). */
export function splitCitations(content: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;

  for (const match of content.matchAll(CITATION)) {
    const start = match.index;
    const prefix = content.slice(last, start) + match[0].slice(0, match[0].indexOf(match[1]));
    segments.push({ kind: "text", text: prefix });

    // On garde les séparateurs entre les numéros pour que le texte reste identique à l'original.
    const parts = match[1].split(/(\d+)/);
    for (const part of parts) {
      if (/^\d+$/.test(part)) segments.push({ kind: "page", page: Number(part) });
      else if (part) segments.push({ kind: "text", text: part });
    }
    segments.push({ kind: "text", text: match[0].slice(match[0].indexOf(match[1]) + match[1].length) });
    last = start + match[0].length;
  }

  segments.push({ kind: "text", text: content.slice(last) });
  return segments.filter((s) => s.kind === "page" || s.text !== "");
}

export function pageUrl(docUrl: string, page: number): string {
  return `${docUrl}#page=${page}`;
}
