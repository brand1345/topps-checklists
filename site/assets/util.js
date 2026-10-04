// Small shared helpers. No dependencies.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

/** Escape text for safe interpolation into HTML (text and attribute values). */
export function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ESC[c]);
}

/** Lowercase, strip accents/diacritics and punctuation noise — used for search matching. */
export function fold(value) {
  return String(value == null ? "" : value)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[’']/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function fmtInt(n) {
  return Number(n).toLocaleString("en-US");
}

/** Pretty number for "≈ N" phrases: 1 decimal under 10, otherwise rounded with separators. */
export function fmtApprox(x) {
  if (!isFinite(x)) return "?";
  if (x >= 9.95) return fmtInt(Math.round(x));
  const r = Math.round(x * 10) / 10;
  return String(r).replace(/\.0$/, "");
}

export function plural(n, one, many) {
  return n === 1 ? one : many || one + "s";
}

/** localStorage that never throws (private mode, blocked storage, previews). */
export const store = {
  get(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  },
  set(key, value) {
    try {
      if (value == null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, value);
    } catch (e) {
      /* ignore */
    }
  },
};

/** Highlight every occurrence of each token (already folded) inside `text`, returning escaped HTML. */
export function highlight(text, tokens) {
  const src = String(text == null ? "" : text);
  if (!tokens || !tokens.length || !src) return esc(src);
  const folded = fold(src);
  // fold() can change length only via stripped marks/apostrophes; map positions conservatively
  if (folded.length !== src.length) {
    // fall back to simple case-insensitive matching on the raw text
    const lower = src.toLowerCase();
    return markRanges(src, rangesFor(lower, tokens));
  }
  return markRanges(src, rangesFor(folded, tokens));
}

function rangesFor(hay, tokens) {
  const ranges = [];
  for (const t of tokens) {
    if (!t) continue;
    let i = hay.indexOf(t);
    while (i !== -1) {
      ranges.push([i, i + t.length]);
      i = hay.indexOf(t, i + t.length);
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
    else merged.push(r.slice());
  }
  return merged;
}

function markRanges(src, ranges) {
  if (!ranges.length) return esc(src);
  let out = "";
  let pos = 0;
  for (const [a, b] of ranges) {
    out += esc(src.slice(pos, a)) + "<mark>" + esc(src.slice(a, b)) + "</mark>";
    pos = b;
  }
  return out + esc(src.slice(pos));
}

export function debounce(fn, ms) {
  let t = 0;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

/** Stable small hash for picking deterministic variety (e.g. printing-plate colour). */
export function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
