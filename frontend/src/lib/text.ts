// Title Case for UI labels (headings, tabs, buttons, column headers, badges).
// Sentences and descriptions stay in sentence case and should not use this.
const SMALL = new Set(["a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor", "of", "on", "or", "per", "the", "to", "vs", "vs.", "via", "with"]);

/** "teaching history (7× taught)" → "Teaching History (7× Taught)"; keeps acronyms (ECON, UG, CSV) intact. */
export function titleCase(s: string): string {
  const parts = s.split(/(\s+)/);
  let wordIndex = 0;
  return parts.map((tok, i) => {
    if (/^\s+$/.test(tok) || tok === "") return tok;
    const lower = tok.toLowerCase();
    const prev = parts[i - 2] ?? "";
    const startsClause = wordIndex === 0 || /[:·—–(/]$/.test(prev) || /^[(\[]/.test(tok);
    const isLast = parts.slice(i + 1).every((p) => /^\s*$/.test(p));
    wordIndex++;
    if (!startsClause && !isLast && SMALL.has(lower)) return lower;
    return tok
      .replace(/^([("'“\[]*)(\p{Ll})/u, (_, p: string, c: string) => p + c.toUpperCase())
      .replace(/-(\p{Ll})/gu, (_, c: string) => "-" + c.toUpperCase());
  }).join("");
}
