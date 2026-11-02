export type Segment =
  | { kind: "text"; text: string }
  | { kind: "page"; page: number };

const SEPARATOR = String.raw`\s*(?:,|;|et|-|–)\s*`;

// Les numéros sont ceux des pages du PDF. Deux formes :
//  - écrite, demandée au modèle du chat : « (p. 12, 40) » ;
//  - orale, dite par le modèle vocal et reprise dans la transcription : « page 12 et page 40 ».
//    Gemini Live transcrit aussi les nombres en toutes lettres : « page dix-sept et trois cent deux ».
const WRITTEN = String.raw`\(pp?\.\s*(\d+(?:${SEPARATOR}\d+)*)\s*\)`;
const SPOKEN = String.raw`\bpages?\s+`;
const CITATION = new RegExp(`${WRITTEN}|${SPOKEN}`, "gi");

const LIST_SEPARATOR = /\s*(?:,|;|et\b|-|–)\s*(?:pages?\s+)?/iy;
const DIGITS = /\d+/y;
const WORD = /[a-zà-ÿ]+/iy;
const WORD_JOINER = /-|[ \t]+/y;
const NEXT_WORD = /\s+([a-zà-ÿ]+)/iy;

const UNITS = new Map([
  ["un", 1], ["une", 1], ["deux", 2], ["trois", 3], ["quatre", 4],
  ["cinq", 5], ["six", 6], ["sept", 7], ["huit", 8], ["neuf", 9],
]);
const TEENS = new Map([
  ["onze", 11], ["douze", 12], ["treize", 13], ["quatorze", 14], ["quinze", 15], ["seize", 16],
]);
const TENS = new Map([
  ["vingt", 20], ["vingts", 20], ["trente", 30], ["quarante", 40], ["cinquante", 50], ["soixante", 60],
]);

// « page six mois », « une page un peu longue » : un nombre suivi d'un de ces mots est une quantité, pas une page.
const QUANTITY_WORDS = new Set([
  "mois", "an", "ans", "annee", "annees", "jour", "jours", "semaine", "semaines", "fois",
  "euro", "euros", "dollar", "dollars", "million", "millions", "milliard", "milliards",
  "peu",
]);

type Parsed = { value: number; next: number };

const isCent = (word: string | undefined) => word === "cent" || word === "cents";

/** Ajoute l'éventuel complément d'une dizaine : « vingt et un », « soixante-quatorze », « quatre-vingt-dix-sept ». */
function parseTail(base: number, i: number, w: string[]): Parsed {
  const [a, b] = [w[i], w[i + 1]];
  if (base !== 80 && a === "et" && (b === "un" || b === "une")) return { value: base + 1, next: i + 2 };
  if (base === 60 && a === "et" && b === "onze") return { value: 71, next: i + 2 };
  if (base === 60 || base === 80) {
    if (a === "dix") {
      const unit = UNITS.get(b);
      return unit !== undefined && unit >= 7
        ? { value: base + 10 + unit, next: i + 2 }
        : { value: base + 10, next: i + 1 };
    }
    const teen = TEENS.get(a);
    if (teen !== undefined) return { value: base + teen, next: i + 1 };
  }
  const unit = UNITS.get(a);
  if (unit !== undefined) return { value: base + unit, next: i + 1 };
  return { value: base, next: i };
}

function parseUnder100(w: string[], i: number): Parsed | null {
  const word = w[i];
  if (word === undefined) return null;
  if (word === "zero") return { value: 0, next: i + 1 };
  if (word === "quatre" && /^vingts?$/.test(w[i + 1] ?? "")) return parseTail(80, i + 2, w);

  const unit = UNITS.get(word);
  if (unit !== undefined) return { value: unit, next: i + 1 };
  if (word === "dix") {
    const next = UNITS.get(w[i + 1]);
    return next !== undefined && next >= 7
      ? { value: 10 + next, next: i + 2 }
      : { value: 10, next: i + 1 };
  }
  const teen = TEENS.get(word);
  if (teen !== undefined) return { value: teen, next: i + 1 };
  const tens = TENS.get(word);
  if (tens !== undefined) return parseTail(tens, i + 1, w);
  return null;
}

function parseUnder1000(w: string[], i: number): Parsed | null {
  let hundreds = 0;
  let next = i;
  if (isCent(w[i])) {
    hundreds = 100;
    next = i + 1;
  } else if (isCent(w[i + 1])) {
    const unit = UNITS.get(w[i]);
    if (unit !== undefined && unit >= 2) {
      hundreds = unit * 100;
      next = i + 2;
    }
  }
  if (!hundreds) return parseUnder100(w, i);

  const rest = parseUnder100(w, next);
  return rest && rest.value > 0
    ? { value: hundreds + rest.value, next: rest.next }
    : { value: hundreds, next };
}

/** Lit le plus long nombre français en toutes lettres au début de `w` (à partir de l'indice `i`). */
function parseCardinal(w: string[], i: number): Parsed | null {
  const head = w[i] === "mille" ? { value: 1, next: i } : parseUnder1000(w, i);
  if (!head || head.value === 0 || w[head.next] !== "mille") return head;

  const rest = parseUnder1000(w, head.next + 1);
  return rest && rest.value > 0
    ? { value: head.value * 1000 + rest.value, next: rest.next }
    : { value: head.value * 1000, next: head.next + 1 };
}

const normalize = (word: string) =>
  word.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

type Item = { page: number; start: number; end: number };

function matchAt(re: RegExp, text: string, index: number): RegExpExecArray | null {
  re.lastIndex = index;
  return re.exec(text);
}

/** Lit un numéro de page à `index` : en chiffres, ou en toutes lettres (« soixante-quatorze », « trois cent deux »). */
function readNumber(text: string, index: number): Item | null {
  const digits = matchAt(DIGITS, text, index);
  if (digits) return { page: Number(digits[0]), start: index, end: index + digits[0].length };

  const words: { word: string; end: number }[] = [];
  let pos = index;
  while (words.length < 12) {
    const word = matchAt(WORD, text, pos);
    if (!word) break;
    pos += word[0].length;
    words.push({ word: normalize(word[0]), end: pos });
    const joiner = matchAt(WORD_JOINER, text, pos);
    if (!joiner) break;
    pos += joiner[0].length;
  }

  const parsed = parseCardinal(words.map((w) => w.word), 0);
  if (!parsed || parsed.next === 0) return null;
  const end = words[parsed.next - 1].end;

  const following = matchAt(NEXT_WORD, text, end);
  if (following && QUANTITY_WORDS.has(normalize(following[1]))) return null;
  return { page: parsed.value, start: index, end };
}

/** Lit une liste de pages (« 12, 40 et page 57 ») à partir de `index` ; vide si le premier numéro n'en est pas un. */
function readPageList(text: string, index: number): Item[] {
  const items: Item[] = [];
  let pos = index;
  for (;;) {
    const item = readNumber(text, pos);
    if (!item) break;
    items.push(item);
    const separator = matchAt(LIST_SEPARATOR, text, item.end);
    if (!separator) break;
    pos = item.end + separator[0].length;
  }
  return items;
}

/** Découpe un texte en morceaux de texte et en pages citées (pour en faire des liens vers le PDF). */
export function splitCitations(content: string): Segment[] {
  const segments: Segment[] = [];
  let last = 0;

  for (const match of content.matchAll(CITATION)) {
    // Une liste « page 12 et page 40 » a déjà consommé le second « page ».
    if (match.index < last) continue;

    let items: Item[];
    if (match[1] !== undefined) {
      const offset = match.index + match[0].indexOf(match[1]);
      items = Array.from(match[1].matchAll(/\d+/g), (d) => ({
        page: Number(d[0]),
        start: offset + d.index,
        end: offset + d.index + d[0].length,
      }));
    } else {
      items = readPageList(content, match.index + match[0].length);
    }
    if (items.length === 0) continue;

    // On garde les séparateurs entre les numéros pour que le texte reste identique à l'original.
    let cursor = last;
    for (const item of items) {
      segments.push({ kind: "text", text: content.slice(cursor, item.start) });
      segments.push({ kind: "page", page: item.page });
      cursor = item.end;
    }
    last = cursor;
  }

  segments.push({ kind: "text", text: content.slice(last) });
  return segments.filter((s) => s.kind === "page" || s.text !== "");
}

export function pageUrl(docUrl: string, page: number): string {
  return `${docUrl}#page=${page}`;
}
