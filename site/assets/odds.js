// Odds formatting, pack/box/case math, rarity tiers and format availability.
import { esc, fmtApprox, fmtInt } from "./util.js";

export const TIERS = [
  { id: "common", label: "Common", short: "Common" },
  // id stays "short-print" for schema stability; the label is a neutral rarity word because
  // collectors read "SP" as a deliberately short-printed card, which most of these sections aren't.
  { id: "short-print", label: "Uncommon", short: "Unc." },
  { id: "case-hit", label: "Case Hit", short: "Case hit" },
  { id: "ultra", label: "Ultra", short: "Ultra" },
];
export const TIER_BY_ID = Object.fromEntries(TIERS.map((t) => [t.id, t]));

/** Plain-language meaning of each tier, using the primary format's box/case config. */
export function tierMeaning(tierId, set) {
  const f = primaryFormat(set);
  const P = (f && f.packsPerBox) || 20;
  const C = P * ((f && f.boxesPerCase) || 12);
  const unit = (f && f.label) || "Hobby";
  switch (tierId) {
    case "common":
      return { plain: "≈1 per box or better", rule: `1:${fmtInt(P)} or better in ${unit}` };
    case "short-print":
      return { plain: "less than 1 per box, at least 1 per case", rule: `1:${fmtInt(P + 1)} – 1:${fmtInt(C)}` };
    case "case-hit":
      return { plain: "≈1 per case or rarer", rule: `1:${fmtInt(C + 1)} – 1:${fmtInt(C * 10)}` };
    case "ultra":
      return { plain: "rarer than 1 per 10 cases", rule: `beyond 1:${fmtInt(C * 10)}` };
    default:
      return { plain: "no odds listed", rule: "" };
  }
}

export function primaryFormat(set) {
  return (set.formats || []).find((f) => f.primary) || (set.formats || [])[0] || null;
}

export function formatById(set, id) {
  return (set.formats || []).find((f) => f.id === id) || null;
}

/** Odds value for format id from an odds map (may be undefined/null). */
export function val(odds, fid) {
  if (!odds) return null;
  const v = odds[fid];
  return v || null;
}

/** Usable packs-per-hit number, or null. Values flagged with `error` still count when n parsed. */
export function nOf(v) {
  return v && typeof v.n === "number" && v.n > 0 ? v.n : null;
}

/** HTML for an odds value. */
export function oddsHTML(v, fmt) {
  if (!v) {
    const label = fmt ? fmt.label : "this format";
    return `<span class="odds odds--none" title="Not in ${esc(label)}" aria-label="Not in ${esc(label)}">—</span>`;
  }
  if (v.error) {
    return `<span class="odds odds--error" title="${esc(v.error)} (shown exactly as printed by Topps)"><span class="warn-mark" aria-hidden="true">!</span>${esc(v.raw)}</span>`;
  }
  return `<span class="odds">${esc(v.raw)}</span>`;
}

/** "≈1 per 17 boxes" / "≈1 per 1.4 cases" / "≈6.7 per box" — or "" when the format's packs are unknown. */
export function rateText(n, fmt) {
  if (!n || !fmt || !fmt.packsPerBox) return "";
  const P = fmt.packsPerBox;
  if (n <= P) {
    const per = P / n;
    return `≈${fmtApprox(per)} per box`;
  }
  const boxes = n / P;
  if (fmt.boxesPerCase && boxes >= fmt.boxesPerCase) {
    const cases = boxes / fmt.boxesPerCase;
    if (cases < 1.05) return "≈1 per case";
    return `≈1 per ${fmtApprox(cases)} cases`;
  }
  if (boxes < 1.05) return "≈1 per box";
  return `≈1 per ${fmtApprox(boxes)} boxes`;
}

/** Format ids where a section (base version or any parallel) has odds. */
export function sectionFormats(section, set) {
  const has = new Set();
  for (const f of set.formats) {
    if (val(section.odds, f.id)) has.add(f.id);
    for (const p of section.parallels || []) if (val(p.odds, f.id)) has.add(f.id);
  }
  return set.formats.filter((f) => has.has(f.id));
}

/** Neutral wording for the formats a thing is limited to, e.g. "Only in Hobby, Jumbo & Breaker's Delight". */
export function exclusiveLabel(formats, set) {
  if (!formats.length) return "";
  if (formats.length === set.formats.length) return "";
  if (formats.length === 1) return `${formats[0].label} exclusive`;
  const missing = set.formats.filter((f) => !formats.includes(f));
  if (missing.length <= 2 && missing.length < formats.length) {
    return `Every format except ${joinAnd(missing.map((f) => f.label))}`;
  }
  return `Only in ${joinAnd(formats.map((f) => f.label))}`;
}

/** "A", "A & B", "A, B & C". */
export function joinAnd(list) {
  if (list.length < 2) return list.join("");
  return list.slice(0, -1).join(", ") + " & " + list[list.length - 1];
}

/** Formats where a single odds map has values. */
export function availableFormats(odds, set) {
  return set.formats.filter((f) => val(odds, f.id));
}

/** Most common usable n (smallest) across a section's base + parallels in format `fid`. */
export function sectionBestN(section, fid) {
  let best = nOf(val(section.odds, fid));
  for (const p of section.parallels || []) {
    const n = nOf(val(p.odds, fid));
    if (n && (!best || n < best)) best = n;
  }
  return best;
}
