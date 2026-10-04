// Keyword -> visual style mapping for parallel "swatches" (chips) and generated card mocks.
//
// To support a new parallel name, add a row to COLORS (tints) or PATTERNS (finishes) below.
// Rules are tested in order against the lowercased parallel name (plus the section name for
// a section's base version); the FIRST matching colour wins, and the FIRST matching pattern wins.
// Effects (FX) are additive flags. The CSS for each pattern lives in styles.css under
// `[data-pattern="<id>"]` and every effect under `[data-fx~="<id>"]`.

/**
 * Colours: c1 = mid tone, c2 = highlight, c3 = shadow, ink = readable text colour on c1.
 * `pattern` optionally implies a finish (e.g. sapphire is faceted).
 */
export const COLORS = [
  { id: "padparadscha", match: /padp[a-z]*ch?a/, c1: "#f08a6c", c2: "#ffd0b8", c3: "#b2465a", ink: "#2a0d0d", pattern: "faceted" },
  { id: "rose-gold", match: /rose gold/, c1: "#d99a8a", c2: "#f8d6ca", c3: "#93574a", ink: "#2b1410" },
  { id: "red-white-blue", match: /red,? white,? (and|&) blue|\brwb\b/, c1: "#c8102e", c2: "#ffffff", c3: "#0a3161", ink: "#ffffff", pattern: "rwb" },
  { id: "tie-dye", match: /tie[- ]?dye/, c1: "#e94e9b", c2: "#ffe14d", c3: "#3b7bff", ink: "#1a1a1a", pattern: "tiedye" },
  { id: "printing-plate", match: /printing plate|\bplates?\b/, c1: "#aeb5bf", c2: "#eef1f5", c3: "#6c737e", ink: "#111", pattern: "plate" },
  { id: "superfractor", match: /superfractor|super fractor/, c1: "#d4a62a", c2: "#ffeaa0", c3: "#6e4e08", ink: "#241a02", pattern: "swirl", fx: ["oneofone"] },
  { id: "frozen", match: /frozen ?fractor|frozen|ice\b|icy/, c1: "#a9dcff", c2: "#ffffff", c3: "#4d8fc4", ink: "#0b2238", pattern: "frozen" },
  { id: "black-sapphire", match: /black sapphire/, c1: "#1b1d26", c2: "#5a6075", c3: "#030308", ink: "#ffffff", pattern: "faceted" },
  { id: "gold", match: /\bgold(en)?\b/, c1: "#d4a62a", c2: "#f8e294", c3: "#7a5a12", ink: "#241a02" },
  { id: "orange", match: /\borange\b/, c1: "#f07c1b", c2: "#ffc27e", c3: "#963a06", ink: "#2a1002" },
  { id: "black", match: /\bblack\b/, c1: "#202329", c2: "#62687a", c3: "#050608", ink: "#ffffff" },
  { id: "red", match: /\bred\b|\bruby\b/, c1: "#d42a2a", c2: "#ff8f86", c3: "#760b0b", ink: "#ffffff" },
  { id: "sapphire", match: /sapphire/, c1: "#1f4fb8", c2: "#7aa8ff", c3: "#0a1c57", ink: "#ffffff", pattern: "faceted" },
  { id: "aqua", match: /\baqua\b|\bcyan\b/, c1: "#19c3d6", c2: "#a8f5ff", c3: "#09707b", ink: "#03272b" },
  { id: "teal", match: /\bteal\b/, c1: "#129a8f", c2: "#82e6db", c3: "#074e48", ink: "#ffffff" },
  { id: "sky-blue", match: /sky blue|\bsky\b|light blue/, c1: "#5fb4f2", c2: "#c8e8ff", c3: "#2468a6", ink: "#08243d" },
  { id: "navy", match: /\bnavy\b/, c1: "#1f3a6b", c2: "#5f7fbf", c3: "#0a1630", ink: "#ffffff" },
  { id: "blue", match: /\bblue\b/, c1: "#2f6fe0", c2: "#9fc4ff", c3: "#123a8a", ink: "#ffffff" },
  { id: "lime", match: /\blime\b|neon green/, c1: "#8fd62a", c2: "#dcff9a", c3: "#4b7a0a", ink: "#142202" },
  { id: "emerald", match: /\bemerald\b/, c1: "#0f8a5f", c2: "#6fe0b4", c3: "#04432d", ink: "#ffffff" },
  { id: "green", match: /\bgreen\b/, c1: "#23a455", c2: "#92f0b4", c3: "#0b5a2b", ink: "#ffffff" },
  { id: "purple", match: /\bpurple\b|\bviolet\b|ultraviolet/, c1: "#7d3cd8", c2: "#cba9ff", c3: "#3b1478", ink: "#ffffff" },
  { id: "magenta", match: /\bmagenta\b|\bfuchsia\b/, c1: "#d6248f", c2: "#ff98d2", c3: "#7c0d50", ink: "#ffffff" },
  { id: "pink", match: /\bpink\b/, c1: "#ea5fa6", c2: "#ffc4e2", c3: "#a3245f", ink: "#2c0618" },
  { id: "yellow", match: /\byellow\b/, c1: "#f2d21b", c2: "#fff7a8", c3: "#9a8106", ink: "#2a2302" },
  { id: "bronze", match: /\bbronze\b/, c1: "#b06a35", c2: "#e9b487", c3: "#5f3412", ink: "#ffffff" },
  { id: "copper", match: /\bcopper\b/, c1: "#c46a3c", c2: "#f1b08a", c3: "#6e3014", ink: "#ffffff" },
  { id: "platinum", match: /\bplatinum\b/, c1: "#d7dbe0", c2: "#ffffff", c3: "#8d949e", ink: "#15181c" },
  { id: "white", match: /\bwhite\b|\bpearl\b/, c1: "#eceff3", c2: "#ffffff", c3: "#aeb4be", ink: "#15181c" },
  { id: "silver", match: /\bsilver\b|\bchrome\b/, c1: "#bcc2cb", c2: "#f3f5f8", c3: "#6f7681", ink: "#15181c" },
  { id: "sepia", match: /\bsepia\b/, c1: "#a8875a", c2: "#e6d2ad", c3: "#5c4320", ink: "#1f1407", fx: ["sepia"] },
];

/** Default when no colour keyword matches: classic chrome. */
export const CHROME = { id: "chrome", c1: "#bfc5ce", c2: "#f5f7fa", c3: "#717884", ink: "#15181c" };

/** Finishes / patterns. One wins (first match). */
export const PATTERNS = [
  { id: "rwb", match: /red,? white,? (and|&) blue/ },
  { id: "tiedye", match: /tie[- ]?dye/ },
  { id: "plate", match: /printing plate|\bplates?\b/ },
  { id: "swirl", match: /superfractor/ },
  { id: "frozen", match: /frozen/ },
  { id: "seams", match: /seams?|stitch/ },
  { id: "raywave", match: /ray ?wave/ },
  { id: "wave", match: /\bwave\b|\bwaves\b/ },
  { id: "xfractor", match: /x-?fractor/ },
  { id: "geometric", match: /geometric|\bgeo\b/ },
  { id: "prism", match: /\bprism|prizm/ },
  { id: "faceted", match: /sapphire|padp[a-z]*ch?a|diamond|mini-?diamond/ },
  { id: "crackedice", match: /cracked ice/ },
  { id: "lava", match: /\blava\b/ },
  { id: "speckle", match: /speckle|sparkle|glitter/ },
  { id: "mojo", match: /\bmojo\b/ },
  { id: "atomic", match: /atomic/ },
  { id: "shimmer", match: /shimmer/ },
  { id: "anniversary", match: /anniversary|\b75th\b/ },
  { id: "lightboard", match: /lightboard|light board/ },
  { id: "logo", match: /logofractor|topps refractor|\blogo\b/ },
];

/** Additive effects. */
export const FX = [
  { id: "refractor", match: /fractor|refractor|prism|wave|geometric|sapphire|padp/ },
  { id: "negative", match: /negative/ },
  { id: "variation", match: /variation|image var|\bvariant\b|super short print|\bssp\b/ },
  { id: "oneofone", match: /superfractor|1\/1|one of one|printing plate/ },
  { id: "mono", match: /black (and|&) white|\bb&w\b|grayscale|greyscale/ },
];

const PLATE_INKS = [
  { id: "cyan", c: "#00a3e0" },
  { id: "magenta", c: "#e0007a" },
  { id: "yellow", c: "#ffd200" },
  { id: "black", c: "#1a1a1a" },
];

/**
 * Describe the look of a parallel.
 * @param {string} name   parallel display name ("" / "Base" for a section's base version)
 * @param {object} [ctx]  { section: section display name, seed: string for deterministic picks }
 */
export function swatchFor(name, ctx) {
  ctx = ctx || {};
  const own = " " + String(name || "").toLowerCase() + " ";
  const sec = " " + String(ctx.section || "").toLowerCase() + " ";
  const isBase = !name || /^\s*base\s*$/i.test(name);
  // A section's base version may borrow colour/finish from the section name (e.g. "Gold Logoman").
  const text = isBase ? sec : own;

  let color = COLORS.find((c) => c.match.test(text));
  // "Gold Sapphire": gold tint wins over generic sapphire (sapphire only gives the faceted finish)
  let pattern = (PATTERNS.find((p) => p.match.test(text)) || {}).id || (color && color.pattern) || "none";
  if (color && color.id === "frozen" && pattern === "none") pattern = "frozen";
  const fx = new Set(FX.filter((f) => f.match.test(text)).map((f) => f.id));
  if (color && color.fx) color.fx.forEach((f) => fx.add(f));
  // Section-level traits apply to all of a section's parallels (image variations, lightboard, …)
  FX.filter((f) => f.id === "variation" && f.match.test(sec)).forEach((f) => fx.add(f.id));
  if (pattern === "none") {
    const secPat = PATTERNS.find((p) => (p.id === "lightboard" || p.id === "anniversary") && p.match.test(sec));
    if (secPat) pattern = secPat.id;
  }
  if (!color) color = CHROME;
  if (pattern === "plate") {
    const ink = PLATE_INKS[hash(String(ctx.seed || name)) % PLATE_INKS.length];
    color = Object.assign({}, color, { plateInk: ink.c, plateId: ink.id });
  }
  // Classic chrome (no colour, no finish) still gets a gentle sheen.
  if (fx.size === 0 && pattern === "none" && color === CHROME && !isBase) fx.add("refractor");
  return {
    color: color.id,
    c1: color.c1,
    c2: color.c2,
    c3: color.c3,
    ink: color.ink,
    plate: color.plateInk || null,
    plateId: color.plateId || null,
    pattern,
    fx: Array.from(fx),
  };
}

/** Attribute string for any element that should carry a swatch's look (chips, dots, mocks). */
export function swatchAttrs(sw) {
  const vars = `--c1:${sw.c1};--c2:${sw.c2};--c3:${sw.c3};--ink:${sw.ink}` + (sw.plate ? `;--plate:${sw.plate}` : "");
  return `style="${vars}" data-color="${sw.color}" data-pattern="${sw.pattern}" data-fx="${sw.fx.join(" ")}"`;
}

/** Human description of the finish, used in the preview caption. */
export function describe(sw) {
  const bits = [];
  if (sw.color !== "chrome" && !["printing-plate", "superfractor", "frozen", "red-white-blue", "tie-dye"].includes(sw.color)) {
    bits.push(sw.color.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase()));
  }
  const P = {
    rwb: "red, white & blue", tiedye: "tie-dye", plate: `${sw.plateId || ""} printing plate (1/1)`, swirl: "gold swirl (1/1)",
    frozen: "frozen ice", seams: "baseball seams", raywave: "RayWave", wave: "wave", xfractor: "X-Fractor grid",
    geometric: "geometric", prism: "prism", faceted: "faceted gem", crackedice: "cracked ice", lava: "lava",
    speckle: "speckle", mojo: "mojo", atomic: "atomic", shimmer: "shimmer", anniversary: "75th anniversary foil",
    lightboard: "lightboard", logo: "Topps logo pattern",
  };
  if (sw.pattern !== "none" && P[sw.pattern]) bits.push(P[sw.pattern]);
  if (sw.fx.includes("negative")) bits.push("negative image");
  if (sw.fx.includes("refractor") && bits.length < 2 && sw.pattern === "none") bits.push("refractor sheen");
  if (sw.fx.includes("variation")) bits.push("image variation");
  return bits.join(" · ");
}

function hash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}
