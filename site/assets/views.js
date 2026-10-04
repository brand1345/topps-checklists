// Pure HTML renderers for each view. They read from the prepared set + UI state and return strings.
import { esc, fmtInt, plural, highlight, fold } from "./util.js";
import {
  TIERS, TIER_BY_ID, tierMeaning, val, nOf, oddsHTML, rateText, sectionFormats, exclusiveLabel,
  availableFormats, sectionBestN, primaryFormat, formatById, joinAnd,
} from "./odds.js";
import { swatchFor } from "./swatch.js";
import { dotHTML, mockHTML } from "./preview.js";

export const CATEGORY_BLURB = {
  base: "The base set, its full refractor rainbow, and image / short-print variations.",
  inserts: "Insert sets you can expect to pull at least once a case.",
  "case-hits": "The chase: inserts that land about once a case — or far less often.",
  autographs: "On-card and sticker autographs, with every numbered parallel.",
  relics: "Memorabilia cards and autograph relics.",
};

const href = (set, ...parts) => "#/" + [set.slug].concat(parts.map(encodeURIComponent)).join("/");

/* ---------------------------------------------------------------- shared bits */

/** Label of the format a section's tier was measured in (tierBasis, else the primary format). */
export function tierBasisFormat(section, set) {
  const id = section && section.tierBasis && section.tierBasis.format;
  return (id && formatById(set, id)) || primaryFormat(set) || null;
}

/**
 * Rarity badge. `opts.section` gives the tier's basis format; `opts.fmt` (the selected odds format) adds a
 * small "· Hobby" suffix when it differs, so a Hobby-based tier isn't read as a Mega rarity.
 */
export function tierBadge(tierId, set, extra, opts) {
  if (!tierId) return `<span class="tier tier--none" title="No odds listed">No odds</span>`;
  opts = opts || {};
  const t = TIER_BY_ID[tierId] || { label: tierId };
  const m = tierMeaning(tierId, set);
  const basis = opts.section ? tierBasisFormat(opts.section, set) : primaryFormat(set);
  const basisLabel = basis ? basis.label : "";
  const suffix = opts.fmt && basis && opts.fmt.id !== basis.id ? `<span class="tier-fmt">· ${esc(basisLabel)}</span>` : "";
  const title = `${t.label}${basisLabel ? " (by " + basisLabel + " odds)" : ""}: ${m.plain}${extra ? " — " + extra : ""}`;
  return `<span class="tier tier--${esc(tierId)}" title="${esc(title)}">${esc(t.label)}${suffix}</span>`;
}

function rcBadge() {
  return `<abbr class="rc" title="Rookie card">RC</abbr>`;
}

function chipSw(section, parallel) {
  return swatchFor(parallel ? parallel.name : "", { section: section.name, seed: section.id + "/" + (parallel ? parallel.id : "") });
}

/** Sorted chip list for a section in the selected format. */
function chipItems(section, fid, sortMode) {
  const items = [];
  if (section.odds) items.push({ p: null, v: val(section.odds, fid), i: -1 });
  (section.parallels || []).forEach((p, i) => items.push({ p, v: val(p.odds, fid), i }));
  if (sortMode === "rarity") {
    const rank = (it) => (it.p === null ? -1 : nOf(it.v) ? 0 : it.v ? 1 : 2);
    items.sort((a, b) => rank(a) - rank(b) || (nOf(a.v) || 0) - (nOf(b.v) || 0) || a.i - b.i);
  }
  return items;
}

function chipHTML(section, it, fmt, tabbable) {
  const sw = chipSw(section, it.p);
  const name = it.p ? it.p.name : "Base";
  const na = !it.v;
  const odds = it.v ? (it.v.error ? `<span class="warn-mark" aria-hidden="true">!</span>${esc(it.v.raw)}` : esc(it.v.raw)) : "—";
  const label = `${name}${it.p ? "" : " version"}, ${it.v ? it.v.raw + " in " + fmt.label : "not in " + fmt.label}`;
  return `<button type="button" class="chip${na ? " is-na" : ""}${it.p ? "" : " chip--base"}${it.v && it.v.error ? " is-err" : ""}"
    data-preview data-rove data-sec="${esc(section.id)}" data-par="${it.p ? esc(it.p.id) : ""}" aria-label="${esc(label)}" tabindex="${tabbable ? 0 : -1}">
    ${dotHTML(sw)}<span class="chip-name">${esc(name)}</span><span class="chip-odds">${odds}</span></button>`;
}

function rainbowHTML(section, ctx) {
  const items = chipItems(section, ctx.fmt.id, ctx.state.chipSort);
  if (!items.length) return "";
  const shown = items.filter((it) => it.v);
  const hidden = items.filter((it) => !it.v);
  const showAll = ctx.state.showNA.has(section.id) || !shown.length;
  // one tab stop per rainbow; arrow keys move between chips (see app.js)
  let html = (showAll ? shown.concat(hidden) : shown).map((it, i) => chipHTML(section, it, ctx.fmt, i === 0)).join("");
  if (hidden.length && shown.length) {
    html += showAll
      ? `<button type="button" class="chip chip--more" data-action="more-chips" data-sec="${esc(section.id)}" aria-expanded="true">Hide ${hidden.length} not in ${esc(ctx.fmt.label)}</button>`
      : `<button type="button" class="chip chip--more" data-action="more-chips" data-sec="${esc(section.id)}" aria-expanded="false">+${hidden.length} not in ${esc(ctx.fmt.label)}</button>`;
  }
  return `<div class="rainbow" role="group" aria-label="${esc(section.name)} parallels (arrow keys move between them)">${html}</div>`;
}

/** Headline odds block for a section in the selected format. */
function headOdds(section, ctx) {
  const { set, fmt } = ctx;
  const v = val(section.odds, fmt.id);
  if (v) {
    const rate = rateText(nOf(v), fmt);
    return `<div class="sec-odds-main">${oddsHTML(v, fmt)}${rate ? `<span class="rate">${esc(rate)}</span>` : ""}</div>`;
  }
  const best = sectionBestN(section, fmt.id);
  if (best) {
    const rate = rateText(best, fmt);
    return `<div class="sec-odds-main"><span class="odds-from">parallels from</span> <span class="odds">1:${fmtInt(best)}</span>${rate ? `<span class="rate">${esc(rate)}</span>` : ""}</div>`;
  }
  const fmts = sectionFormats(section, set);
  if (!fmts.length) return `<div class="sec-odds-main is-muted">No odds listed</div>`;
  let excl = exclusiveLabel(fmts, set) || "Available in " + joinAnd(fmts.map((f) => f.label));
  // "Not in Fanatics" + "Every format except Fanatics" would repeat itself
  if (/^Every format except /.test(excl) && set.formats.length - fmts.length === 1) excl = "Available in every other format";
  return `<div class="sec-odds-main is-muted"><span title="Not in ${esc(fmt.label)}">Not in ${esc(fmt.label)}</span></div>
    <div class="sec-excl">${esc(excl)}</div>`;
}

function sectionMeta(section) {
  const bits = [`${fmtInt(section.cardCount)} ${plural(section.cardCount, "card")}`];
  if (section.rookieCount) bits.push(`${fmtInt(section.rookieCount)} RC`);
  const np = (section.parallels || []).length;
  if (np) bits.push(`${np} ${plural(np, "parallel")}`);
  if (section.redemption) bits.push(`<span class="pill pill--redemption" title="Packed as a redemption card">Redemption</span>`);
  return bits.join('<span class="dot-sep" aria-hidden="true">·</span>');
}

/* ---------------------------------------------------------------- category view */

/** True when a section (base version or any parallel) has odds in format `fid`. */
export function inFormat(section, set, fid) {
  return sectionFormats(section, set).some((f) => f.id === fid);
}

export function categoryView(ctx) {
  const { set, state, route, fmt } = ctx;
  const cat = set.categories.find((c) => c.id === route.category);
  const all = set._byCategory[route.category] || [];
  let sections = all;
  if (state.sectionSort !== "checklist") {
    const fid = fmt.id;
    const easiest = state.sectionSort === "easiest";
    // sections without odds in this format always sink to the bottom
    sections = sections.slice().sort((a, b) => {
      const ka = sectionBestN(a, fid);
      const kb = sectionBestN(b, fid);
      if (!ka || !kb) return (ka ? 0 : 1) - (kb ? 0 : 1);
      return easiest ? ka - kb : kb - ka;
    });
  }
  const inFmt = all.filter((s) => inFormat(s, set, fmt.id)).length;
  const outFmt = all.length - inFmt;
  if (state.onlyInFmt && outFmt) sections = sections.filter((s) => inFormat(s, set, fmt.id));
  const cards = all.reduce((a, s) => a + s.cardCount, 0);
  const head = `<div class="view-head">
    <div>
      <h1 class="view-title" tabindex="-1">${esc(cat ? cat.label : route.category)}</h1>
      <p class="view-sub">${esc(CATEGORY_BLURB[route.category] || "")}</p>
    </div>
    <div class="view-stats"><span><b>${all.length}</b> ${plural(all.length, "section")}</span>${outFmt && all.length ? `<span><b>${inFmt}</b> in ${esc(fmt.label)}</span>` : ""}<span><b>${fmtInt(cards)}</b> cards</span></div>
  </div>`;
  if (!all.length) {
    return head + `<div class="empty"><div class="empty-art" aria-hidden="true"></div><p>No ${esc((cat ? cat.label : "").toLowerCase())} sections in this set.</p></div>`;
  }
  const toolbar = `<div class="toolbar" role="group" aria-label="Section display options">
    <div class="seg" role="group" aria-label="Order sections">
      <span class="seg-label" aria-hidden="true">Order</span>
      ${segBtn("section-sort", "checklist", "Checklist", state.sectionSort)}
      ${segBtn("section-sort", "easiest", "Easiest", state.sectionSort)}
      ${segBtn("section-sort", "rarest", "Rarest", state.sectionSort)}
    </div>
    <div class="seg" role="group" aria-label="Order parallels">
      <span class="seg-label" aria-hidden="true">Parallels</span>
      ${segBtn("chip-sort", "rarity", "By odds", state.chipSort)}
      ${segBtn("chip-sort", "pdf", "As listed", state.chipSort)}
    </div>
    ${outFmt ? `<label class="toggle"><input type="checkbox" data-action="only-in-fmt"${state.onlyInFmt ? " checked" : ""}><span>Only in ${esc(fmt.label)}</span></label>` : ""}
    <div class="toolbar-end">
      <button type="button" class="btn btn--ghost" data-action="expand-all">Expand all</button>
      <button type="button" class="btn btn--ghost" data-action="collapse-all">Collapse all</button>
    </div>
  </div>`;
  const hiddenNote = state.onlyInFmt && outFmt
    ? `<p class="muted fine-note">${outFmt} ${plural(outFmt, "section")} not in ${esc(fmt.label)} hidden.</p>`
    : "";
  const body = sections.length
    ? `<div class="sections">${sections.map((s) => sectionCard(s, ctx)).join("")}</div>`
    : `<div class="empty"><p>No ${esc((cat ? cat.label : "").toLowerCase())} sections in ${esc(fmt.label)}.</p></div>`;
  return head + toolbar + hiddenNote + body;
}

function segBtn(action, value, label, current) {
  const on = value === current;
  return `<button type="button" class="seg-btn${on ? " is-on" : ""}" data-action="${action}" data-value="${value}" aria-pressed="${on}">${label}</button>`;
}

export function sectionCard(section, ctx) {
  const open = ctx.state.expanded.has(section.id);
  const basis = tierBasisFormat(section, ctx.set);
  const prim = primaryFormat(ctx.set);
  const tierExtra = section.tierBasis && basis && prim && basis.id !== prim.id ? `not in ${prim.label}, so measured in ${basis.label}` : "";
  const out = !inFormat(section, ctx.set, ctx.fmt.id);
  return `<article class="sec${open ? " is-open" : ""}${out ? " is-out" : ""}" id="sec-${esc(section.id)}" data-sec="${esc(section.id)}" data-tier="${esc(section.tier || "none")}">
    <div class="sec-head">
      <button type="button" class="sec-toggle" data-action="toggle" aria-expanded="${open}" aria-controls="body-${esc(section.id)}">
        <span class="chev" aria-hidden="true"></span>
        <span class="sec-titles">
          <span class="sec-name">${esc(section.name)}</span>
          <span class="sec-meta">${sectionMeta(section)}</span>
        </span>
      </button>
      <div class="sec-side">
        ${tierBadge(section.tier, ctx.set, tierExtra, { section, fmt: ctx.fmt })}
        ${headOdds(section, ctx)}
      </div>
    </div>
    ${rainbowHTML(section, ctx)}
    <div class="sec-body" id="body-${esc(section.id)}"${open ? "" : " hidden"}>${open ? sectionBody(section, ctx) : ""}</div>
  </article>`;
}

/* ---------------------------------------------------------------- section body */

const COLLAPSE_FOOT_MIN = 30;

export function sectionBody(section, ctx) {
  const { state } = ctx;
  const tab = state.bodyTab[section.id] || "cards";
  const nOdds = (section.odds ? 1 : 0) + (section.parallels || []).length;
  // the pipeline already adds a short "Redemption card" note; replace it with the explanatory one
  const notes = (section.notes || []).filter((n) => !/^redemption cards?\.?$/i.test(String(n).trim()));
  if (section.redemption) notes.push("Packed as a redemption card — redeem it online.");
  const notesHTML = notes.length ? `<ul class="notes">${notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` : "";
  const id = esc(section.id);
  const tabBtn = (value, label, count) => {
    const on = tab === value;
    return `<button type="button" role="tab" class="subtab${on ? " is-on" : ""}" id="tab-${id}-${value}" aria-selected="${on}" aria-controls="panel-${id}" tabindex="${on ? 0 : -1}" data-action="body-tab" data-value="${value}">${label} <span class="count">${count}</span></button>`;
  };
  const content = tab === "odds" && nOdds ? oddsMatrix(section, ctx) : cardTable(section, ctx);
  const foot = section.cardCount > COLLAPSE_FOOT_MIN
    ? `<div class="sec-foot"><button type="button" class="btn btn--ghost" data-action="collapse-sec"><span class="sec-foot-arrow" aria-hidden="true">↑</span> Collapse ${esc(section.name)}</button></div>`
    : "";
  if (!nOdds) return notesHTML + content + foot;
  return notesHTML +
    `<div class="subtabs" role="tablist" aria-label="${esc(section.name)} details">
        ${tabBtn("cards", "Checklist", fmtInt(section.cardCount))}
        ${tabBtn("odds", "Odds by format", nOdds)}
      </div>
      <div class="subpanel" role="tabpanel" id="panel-${id}" aria-labelledby="tab-${id}-${tab === "odds" ? "odds" : "cards"}">${content}</div>` +
    foot;
}

function cardTable(section, ctx) {
  const f = ctx.state.filters[section.id] || { q: "", rc: false };
  if (!section.cards.length) return `<p class="muted pad">No cards listed for this section.</p>`;
  const rows = section.cards.map((c, i) => cardRow(c, i, section)).join("");
  const showRc = section.rookieCount > 0;
  // fixed column widths so the Team column doesn't shift while filtering
  const codeLen = section.cards.reduce((m, c) => Math.max(m, String(c.code || "").length), 2);
  const codeW = Math.round(Math.max(52, codeLen * 7.7 + 28));
  return `<div class="table-tools">
      <label class="filter">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.96 12.06l4.24 4.24-1.4 1.4-4.24-4.24A7.5 7.5 0 1 1 10.5 3Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Z"/></svg>
        <span class="sr-only">Filter ${esc(section.name)}</span>
        <input type="search" class="filter-input" data-action="filter" placeholder="Filter player, team or #" value="${esc(f.q)}" autocomplete="off" spellcheck="false">
      </label>
      ${showRc ? `<label class="toggle"><input type="checkbox" data-action="rc-only"${f.rc ? " checked" : ""}><span>Rookies only</span></label>` : ""}
      <span class="table-count" aria-live="polite"></span>
    </div>
    <div class="table-wrap"><table class="cards cards--fixed">
      <colgroup><col class="col-code" style="width:${codeW}px"><col><col class="col-team"></colgroup>
      <thead><tr><th scope="col" class="c-code">#</th><th scope="col">Player</th><th scope="col" class="c-team">Team</th></tr></thead>
      <tbody>${rows}</tbody>
    </table><p class="no-match" hidden>No cards match this filter.</p></div>`;
}

/** Inner HTML of the three cells of a card row; `tokens` (folded) are highlighted when given. */
export function cardCells(card, tokens) {
  const hl = (t) => highlight(t, tokens);
  const players = card.players.length ? card.players : [{ name: "", team: "", rookie: false }];
  const multi = players.length > 1;
  const names = players
    .map((p) => `<span class="pl">${p.name ? hl(p.name) : `<span class="muted">Team card</span>`}${p.rookie ? rcBadge() : ""}${p.name && p.team ? `<span class="pl-team">${hl(p.team)}</span>` : p.team ? `<span class="pl-team pl-team--only">${hl(p.team)}</span>` : ""}</span>`)
    .join("");
  const teams = players.map((p) => `<span class="pl">${hl(p.team) || '<span class="muted">—</span>'}</span>`).join("");
  return {
    code: card.code ? hl(card.code) : '<span class="muted" title="No card number">—</span>',
    player: names + (multi ? `<span class="multi-tag">${players.length}-player card</span>` : ""),
    team: teams,
  };
}

function cardRow(card, i, section) {
  const multi = card.players.length > 1;
  const c = cardCells(card, null);
  return `<tr data-i="${i}" data-rc="${card.rookie ? 1 : 0}"${multi ? ' class="is-multi"' : ""}>
    <td class="c-code">${c.code}</td>
    <td class="c-player">${c.player}</td>
    <td class="c-team">${c.team}</td></tr>`;
}

function oddsMatrix(section, ctx) {
  const { set, fmt } = ctx;
  const rows = [];
  if (section.odds) rows.push({ p: null, odds: section.odds });
  (section.parallels || []).forEach((p) => rows.push({ p, odds: p.odds }));
  const th = set.formats
    .map((f) => `<th scope="col" class="${f.id === fmt.id ? "is-active" : ""}">${esc(f.label)}</th>`)
    .join("");
  const body = rows
    .map((r) => {
      const sw = chipSw(section, r.p);
      const name = r.p ? r.p.name : "Base";
      const cells = set.formats
        .map((f) => {
          const v = val(r.odds, f.id);
          const rate = v ? rateText(nOf(v), f) : "";
          return `<td class="${f.id === fmt.id ? "is-active" : ""}"${rate ? ` title="${esc(rate)}"` : ""}>${oddsHTML(v, f)}</td>`;
        })
        .join("");
      return `<tr><th scope="row"><button type="button" class="pname" data-preview data-sec="${esc(section.id)}" data-par="${r.p ? esc(r.p.id) : ""}">${dotHTML(sw)}<span>${esc(name)}</span></button></th>${cells}</tr>`;
    })
    .join("");
  const basis = section.oddsName ? `<p class="fine">Base odds row: <code>${esc(section.oddsName)}</code></p>` : "";
  return `<div class="table-wrap"><table class="matrix"><thead><tr><th scope="col">Parallel</th>${th}</tr></thead><tbody>${body}</tbody></table></div>${basis}`;
}

/* ---------------------------------------------------------------- overview */

export function overviewView(ctx) {
  const { set, fmt } = ctx;
  const st = set.stats || {};
  const gen = set.generatedAt ? new Date(set.generatedAt) : null;
  const genText = gen && !isNaN(gen) ? gen.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" }) : "";
  const hero = `<section class="hero">
    <div class="hero-main">
    <div class="hero-text">
      <p class="kicker">${esc([set.brand, set.sport, set.year].filter(Boolean).join(" · "))}</p>
      <h1 class="hero-title" tabindex="-1">${esc(set.name)}</h1>
      <p class="hero-sub">${fmtInt(st.cards || 0)} cards across ${fmtInt(st.sections || 0)} sections, ${fmtInt(st.parallels || 0)} parallels and ${set.formats.length} box formats.${genText ? ` <span class="muted">Updated ${esc(genText)}.</span>` : ""}</p>
    </div>
    <div class="stats">
      ${stat(st.cards, "Cards")}${stat(st.sections, "Sections")}${stat(set._rookies.length, "Rookies")}${stat(st.parallels, "Parallels")}
    </div>
    </div>
    ${heroCards(set)}
  </section>`;

  const cats = `<section class="cat-grid" aria-label="Browse by category">${set.categories
    .map((c) => {
      const secs = set._byCategory[c.id] || [];
      const cards = secs.reduce((a, s) => a + s.cardCount, 0);
      const names = secs.slice(0, 4).map((s) => esc(s.name)).join(", ") + (secs.length > 4 ? `, +${secs.length - 4} more` : "");
      return `<a class="cat-tile cat-tile--${esc(c.id)}" href="${href(set, c.id)}">
        <span class="cat-tile-top"><span class="cat-tile-label">${esc(c.label)}</span><span class="cat-tile-count">${c.sectionCount}</span></span>
        <span class="cat-tile-cards">${fmtInt(cards)} cards</span>
        <span class="cat-tile-names">${names || '<span class="muted">None in this set</span>'}</span>
      </a>`;
    })
    .join("")}</section>`;

  const legend = `<section class="panel">
    <h2 class="panel-title">Rarity tiers</h2>
    <p class="panel-sub">Based on ${esc((primaryFormat(set) || {}).label || "primary")} odds per section.</p>
    <ul class="legend">${TIERS.map((t) => {
      const m = tierMeaning(t.id, set);
      const count = set._visible.filter((s) => s.tier === t.id).length;
      return `<li>${tierBadge(t.id, set)}<span class="legend-text"><b>${esc(m.plain)}</b><span class="muted">${esc(m.rule)}</span></span><span class="legend-count">${count}</span></li>`;
    }).join("")}</ul>
  </section>`;

  const rare = rarest(set, fmt.id, 10);
  const oneNote = rare.oneOfOnes.count
    ? `<p class="pulls-note">Not ranked: ${fmtInt(rare.oneOfOnes.count)} one-of-one ${plural(rare.oneOfOnes.count, "parallel")} (${esc(joinAnd(rare.oneOfOnes.kinds))}), each ${esc(rare.oneOfOnes.range)}.</p>`
    : "";
  const rarestHTML = `<section class="panel">
    <h2 class="panel-title">Rarest pulls <span class="in-fmt">in ${esc(fmt.label)}</span></h2>
    <p class="panel-sub">The toughest numbered card in each section. Select a row to open it.</p>
    ${rare.list.length ? `<ol class="pulls">${pullRows(rare.list, ctx)}</ol>` : `<p class="muted">No odds listed for ${esc(fmt.label)}.</p>`}
    ${oneNote}
  </section>`;

  const hits = easiestHits(set, fmt.id, 8);
  const hitsHTML = `<section class="panel">
    <h2 class="panel-title">Best shot at a hit <span class="in-fmt">in ${esc(fmt.label)}</span></h2>
    <p class="panel-sub">Autograph and relic sections, most common first.</p>
    ${hits.length ? `<ol class="pulls">${pullRows(hits, ctx)}</ol>` : `<p class="muted">No autograph or relic odds for ${esc(fmt.label)}.</p>`}
  </section>`;

  return hero + cats + `<div class="panels">${rarestHTML}${hitsHTML}${legend}</div>` + rookiesPanel(ctx) + dataNotes(set);
}

const ROOKIES_TOP = 24;

function rookieItem(set, r) {
  const s = fold([r.name, r.team, r.code].join(" "));
  return `<li data-s="${esc(s)}"><a href="${href(set, "search", r.name)}" class="rookie">
        <span class="rookie-code">${r.code ? esc(r.code) : "—"}</span>
        <span class="rookie-name">${esc(r.name)}</span>
        <span class="rookie-team">${esc(r.team)}</span>
        <span class="rookie-n">${r.cards} ${plural(r.cards, "card")}</span></a></li>`;
}

/** Rookies: the most-carded first, with "Show all" revealing the full list split into base-set / other. */
function rookiesPanel(ctx) {
  const { set, state } = ctx;
  const rk = set._rookies;
  if (!rk.length) return "";
  const all = !!state.rookiesAll;
  const top = rk
    .slice()
    .sort((a, b) => b.cards - a.cards || rookieOrder(a, b))
    .slice(0, ROOKIES_TOP);
  const base = rk.filter((r) => r.base);
  const other = rk.filter((r) => !r.base);
  const group = (title, list) =>
    list.length ? `<div class="rookie-group"><h3 class="rookie-group-title">${esc(title)} <span class="in-fmt">${list.length}</span></h3><ul class="rookies">${list.map((r) => rookieItem(set, r)).join("")}</ul></div>` : "";
  const more = rk.length > ROOKIES_TOP;
  return `<section class="panel panel--wide rookies-panel${all || !more ? " is-all" : ""}" data-rookies>
    <div class="panel-head"><div><h2 class="panel-title">Rookies <span class="in-fmt">${rk.length}</span></h2>
    <p class="panel-sub">Select a rookie to see all of their cards. The count is how many cards they have in this set.</p></div>
    ${rk.length > 8 ? `<label class="filter rookie-filter"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M10.5 3a7.5 7.5 0 0 1 5.96 12.06l4.24 4.24-1.4 1.4-4.24-4.24A7.5 7.5 0 1 1 10.5 3Zm0 2a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11Z"/></svg><span class="sr-only">Filter rookies</span><input type="search" class="filter-input" data-action="rookie-filter" placeholder="Filter rookies" autocomplete="off" spellcheck="false"></label>` : ""}</div>
    ${more ? `<div class="rookies-top"><p class="rookie-group-title">Most cards in the set</p><ul class="rookies">${top.map((r) => rookieItem(set, r)).join("")}</ul></div>` : ""}
    <div class="rookies-all">${group("In the base set", base)}${group(base.length ? "Autograph & insert only" : "All rookies", other)}</div>
    <p class="no-match rookies-none" hidden>No rookies match.</p>
    ${more ? `<button type="button" class="btn rookies-more" data-action="rookies-toggle" aria-expanded="${all}">${all ? "Show fewer" : `Show all ${rk.length} rookies`}</button>` : ""}
  </section>`;
}

/** Total order for rookies: base-set cards first, then by card number, then code, then name. */
export function rookieOrder(a, b) {
  if (a.base !== b.base) return a.base ? -1 : 1;
  const na = parseInt(a.code, 10);
  const nb = parseInt(b.code, 10);
  const ka = isNaN(na) ? Infinity : na;
  const kb = isNaN(nb) ? Infinity : nb;
  if (ka !== kb) return ka < kb ? -1 : 1;
  const c = String(a.code || "").localeCompare(String(b.code || ""));
  return c || a.name.localeCompare(b.name);
}

/** Three fanned example cards from the base set's rainbow (decorative, but hover/focus previews them). */
function heroCards(set) {
  const base = set._visible.find((s) => s.kind === "base" && s.parallels.length) || set._visible.find((s) => s.parallels.length);
  if (!base) return "";
  const ps = base.parallels;
  const pick = [
    ps.find((p) => /^refractor$/i.test(p.name)) || ps[0],
    ps.find((p) => /^gold refractor$/i.test(p.name)) || ps.find((p) => /gold/i.test(p.name)) || ps[Math.floor(ps.length / 2)],
    ps.find((p) => /superfractor/i.test(p.name)) || ps[ps.length - 1],
  ].filter((p, i, a) => p && a.indexOf(p) === i);
  const cards = base.cards.filter((c) => c.players.length && c.players[0].name);
  return `<div class="hero-cards">${pick
    .map((p, i) => {
      const c = cards[i] || cards[0] || { code: "", players: [{ name: "", team: "" }] };
      const sw = chipSw(base, p);
      const label = `${p.name} — ${base.name}`;
      return `<button type="button" class="hero-card" data-preview data-sec="${esc(base.id)}" data-par="${esc(p.id)}" aria-label="${esc(label)}">${mockHTML(sw, { player: c.players[0].name, team: c.players[0].team, code: c.code })}</button>`;
    })
    .join("")}</div>`;
}

function stat(n, label) {
  return `<div class="stat"><span class="stat-n">${fmtInt(n || 0)}</span><span class="stat-l">${esc(label)}</span></div>`;
}

function isOneOfOne(s, p) {
  return !!p && chipSw(s, p).fx.includes("oneofone");
}

function rarest(set, fid, limit) {
  const out = [];
  const ones = { count: 0, kinds: [], min: Infinity, max: 0 };
  for (const s of set._visible) {
    const v = val(s.odds, fid);
    if (nOf(v)) out.push({ s, p: null, v });
    for (const p of s.parallels || []) {
      const pv = val(p.odds, fid);
      if (!nOf(pv)) continue;
      // 1/1s (superfractors, printing plates) all tie at the very top and say little; summarise them instead
      if (isOneOfOne(s, p)) {
        ones.count += 1;
        ones.min = Math.min(ones.min, nOf(pv));
        ones.max = Math.max(ones.max, nOf(pv));
        const kind = /plate/i.test(p.name) ? "printing plates" : /superfractor/i.test(p.name) ? "Superfractors" : p.name;
        if (!ones.kinds.includes(kind)) ones.kinds.push(kind);
        continue;
      }
      out.push({ s, p, v: pv });
    }
  }
  out.sort((a, b) => nOf(b.v) - nOf(a.v));
  // one entry per section so the list isn't ten parallels from the same insert family
  const seen = new Set();
  const list = out.filter((r) => !seen.has(r.s.id) && seen.add(r.s.id)).slice(0, limit);
  const range = ones.count
    ? ones.min === ones.max ? `1:${fmtInt(ones.min)}` : `1:${fmtInt(ones.min)} – 1:${fmtInt(ones.max)}`
    : "";
  if (ones.kinds.length > 3) ones.kinds = ones.kinds.slice(0, 3).concat("others");
  return { list, oneOfOnes: { count: ones.count, kinds: ones.kinds, range } };
}

function easiestHits(set, fid, limit) {
  const out = [];
  for (const s of set._visible) {
    if (s.category !== "autographs" && s.category !== "relics") continue;
    const v = val(s.odds, fid);
    if (nOf(v)) out.push({ s, p: null, v });
    else {
      let best = null;
      for (const p of s.parallels || []) {
        const pv = val(p.odds, fid);
        if (nOf(pv) && (!best || nOf(pv) < nOf(best.v))) best = { s, p, v: pv };
      }
      if (best) out.push(best);
    }
  }
  out.sort((a, b) => nOf(a.v) - nOf(b.v));
  return out.slice(0, limit);
}

/** Rows with shared ranks for ties ("1, 2, 2, 4"). */
function pullRows(list, ctx) {
  let rank = 0;
  return list
    .map((r, i) => {
      if (i === 0 || nOf(r.v) !== nOf(list[i - 1].v)) rank = i + 1;
      const tied = (i > 0 && nOf(r.v) === nOf(list[i - 1].v)) || (i + 1 < list.length && nOf(r.v) === nOf(list[i + 1].v));
      return pullRow(r, rank, tied, ctx);
    })
    .join("");
}

function pullRow(r, rank, tied, ctx) {
  const { set, fmt } = ctx;
  const sw = chipSw(r.s, r.p);
  const rate = rateText(nOf(r.v), fmt);
  const name = r.p ? r.p.name : r.s.name;
  return `<li class="pull">
    <span class="pull-rank"${tied ? ` title="Tied for ${rank}"` : ""}>${rank}${tied ? '<span class="sr-only"> (tied)</span>' : ""}</span>
    <button type="button" class="pull-sw" data-preview data-sec="${esc(r.s.id)}" data-par="${r.p ? esc(r.p.id) : ""}" aria-label="Preview ${esc(name)}">${dotHTML(sw)}</button>
    <a class="pull-link" href="${href(set, r.s.category, r.s.id)}">
      <span class="pull-text"><span class="pull-name">${esc(name)}</span>
      <span class="pull-sec">${r.p ? esc(r.s.name) : "Base version"}</span></span>
      <span class="pull-odds">${oddsHTML(r.v, fmt)}${rate ? `<span class="rate">${esc(rate)}</span>` : ""}</span>
      <span class="pull-chev" aria-hidden="true"></span>
    </a>
  </li>`;
}

function dataNotes(set) {
  const w = set.warnings || [];
  const u = set.unmatchedOdds || [];
  const noOdds = set._visible.filter((s) => !s.odds && !(s.parallels || []).length);
  const disclaimer = set.disclaimer ? `<p class="disclaimer">${esc(set.disclaimer)}</p>` : "";
  if (!w.length && !u.length && !noOdds.length) return `<footer class="foot">${disclaimer}</footer>`;
  const fmts = set.formats;
  const uRows = u
    .map((r) => `<tr><th scope="row">${esc(r.rawName)}</th>${fmts.map((f) => `<td>${oddsHTML(val(r.odds, f.id), f)}</td>`).join("")}</tr>`)
    .join("");
  return `<details class="data-notes">
    <summary><span>Data notes</span><span class="muted">${u.length} unmatched odds ${plural(u.length, "row")} · ${noOdds.length} ${plural(noOdds.length, "section")} without odds · ${w.length} ${plural(w.length, "warning")}</span></summary>
    <div class="data-notes-body">
      ${u.length ? `<h3>Odds rows not matched to a checklist section</h3><div class="table-wrap"><table class="matrix"><thead><tr><th scope="col">Odds row</th>${fmts.map((f) => `<th scope="col">${esc(f.label)}</th>`).join("")}</tr></thead><tbody>${uRows}</tbody></table></div>` : ""}
      ${noOdds.length ? `<h3>Sections without odds</h3><p>${noOdds.map((s) => `<a href="${href(set, s.category, s.id)}">${esc(s.name)}</a>`).join(", ")}</p>` : ""}
      ${w.length ? `<h3>Parser warnings</h3><ul class="warnings">${w.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
    </div>
  </details><footer class="foot">${disclaimer}</footer>`;
}

/* ---------------------------------------------------------------- search */

const MAX_ROWS = 400;
const MAX_PARALLELS = 60;

const RC_WORDS = new Set(["rc", "rcs", "rookie", "rookies"]);
const TIER_WORDS = [
  { words: ["case", "hit"], tier: "case-hit" },
  { words: ["casehit"], tier: "case-hit" },
  { words: ["ultra"], tier: "ultra" },
  { words: ["uncommon"], tier: "short-print" },
];

/**
 * Split a search query into text tokens and filter words: "rc"/"rookie" (rookie cards), a box format
 * ("mega", "value box", "breaker's delight", …) and a rarity tier ("case hit", "ultra", "uncommon").
 * Each filter keeps the word indexes it consumed so a pill can remove it again.
 */
export function parseQuery(q, set) {
  const words = fold(q).split(" ").filter(Boolean);
  const out = { words, text: [], rc: null, fmt: null, tier: null };
  const clean = (w) => w.replace(/[^a-z0-9]/g, "");
  const norm = (w) => clean(w).replace(/s$/, "");
  const aliases = TIER_WORDS.slice();
  for (const f of set.formats) {
    const seen = new Set();
    const label = fold(f.label).split(" ").map(clean).filter(Boolean);
    for (const ws of [label, f.id.split("-").map(clean).filter(Boolean), label[0] && label[0].length >= 4 ? [label[0]] : null]) {
      if (!ws || !ws.length || seen.has(ws.join(" "))) continue;
      seen.add(ws.join(" "));
      aliases.push({ words: ws, fmt: f.id });
    }
  }
  aliases.sort((a, b) => b.words.length - a.words.length);
  let i = 0;
  outer: while (i < words.length) {
    const w = words[i];
    if (!out.rc && RC_WORDS.has(clean(w))) {
      out.rc = { idx: [i] };
      i += 1;
      continue;
    }
    for (const a of aliases) {
      const n = a.words.length;
      if (i + n > words.length || !a.words.every((x, k) => norm(x) === norm(words[i + k]))) continue;
      const idx = Array.from({ length: n }, (_, k) => i + k);
      if (a.tier && !out.tier) {
        out.tier = { id: a.tier, idx };
        i += n;
        continue outer;
      }
      if (a.fmt && !out.fmt) {
        out.fmt = { id: a.fmt, idx };
        i += n;
        continue outer;
      }
    }
    out.text.push(w);
    i += 1;
  }
  return out;
}

/** The query without one filter's words (for a pill's remove link). */
function queryWithout(pq, filter) {
  return pq.words.filter((w, i) => !filter.idx.includes(i)).join(" ");
}

export function searchView(ctx) {
  const { set, route, state } = ctx;
  const q = route.query || "";
  const pq = parseQuery(q, set);
  const T = pq.text;
  if (!pq.words.length) {
    return `<div class="view-head"><div><h1 class="view-title" tabindex="-1">Search</h1><p class="view-sub">Type a player, team, card number or section.</p></div></div>`;
  }
  const fmtF = pq.fmt ? formatById(set, pq.fmt.id) : null;
  const fmt = fmtF || ctx.fmt;
  const allIn = (hay) => T.every((t) => hay.indexOf(t) !== -1);
  const anyIn = (hay) => T.some((t) => hay.indexOf(t) !== -1);
  const secOk = (s) => (!fmtF || inFormat(s, set, fmtF.id)) && (!pq.tier || s.tier === pq.tier.id);
  const fullName = (s) => pq.words.every((t) => s._s.indexOf(t) !== -1);

  // sections: by name, or (with no text) every section passing the format / tier filters
  let secHits = [];
  if (T.length) secHits = set._visible.filter((s) => (secOk(s) && allIn(s._s) && (!pq.rc || s.rookieCount > 0)) || fullName(s));
  else if (fmtF || pq.tier) secHits = set._visible.filter((s) => secOk(s) && (!pq.rc || s.rookieCount > 0));
  secHits.sort((a, b) => (fullName(a) ? 0 : 1) - (fullName(b) ? 0 : 1));

  const parHits = [];
  if (T.length) {
    for (const s of set._visible) {
      if (!secOk(s) || (pq.rc && !s.rookieCount)) continue;
      for (const p of s.parallels || []) {
        if (allIn(p._s + " " + s._s) && anyIn(p._s) && (!fmtF || val(p.odds, fmtF.id))) parHits.push({ s, p });
      }
    }
  }
  if (state.chipSort === "rarity") {
    const key = (h) => nOf(val(h.p.odds, fmt.id)) || Infinity;
    parHits.sort((a, b) => (key(a) === key(b) ? 0 : key(a) < key(b) ? -1 : 1));
  }

  const groups = [];
  let total = 0;
  const players = new Map();
  if (T.length || pq.rc) {
    for (const s of set._visible) {
      if (!secOk(s)) continue;
      const hits = [];
      for (let i = 0; i < s.cards.length; i++) {
        const c = s.cards[i];
        const hay = c._s;
        // each token must match the card or the section name, and at least one must match the card itself
        if (!T.every((t) => hay.indexOf(t) !== -1 || s._s.indexOf(t) !== -1)) continue;
        if (T.length && !anyIn(hay) && !pq.rc) continue;
        if (pq.rc && !(c.rookie || c.players.some((p) => p.rookie))) continue;
        const exact = !!c.code && T.includes(fold(c.code));
        hits.push({ c, exact });
        for (const p of c.players) {
          if (p.name && T.length && allIn(fold(p.name) + " " + fold(p.team) + " " + s._s)) {
            const key = fold(p.name);
            const e = players.get(key) || { name: p.name, key, teams: new Set(), cards: 0, rcCards: 0, cats: {} };
            e.teams.add(p.team);
            e.cards += 1;
            if (p.rookie) e.rcCards += 1;
            e.cats[s.category] = (e.cats[s.category] || 0) + 1;
            players.set(key, e);
          }
        }
      }
      if (hits.length) {
        hits.sort((a, b) => (a.exact ? 0 : 1) - (b.exact ? 0 : 1));
        groups.push({ s, hits, exact: hits.some((h) => h.exact) });
        total += hits.length;
      }
    }
    // an exact card-number match ranks first
    groups.sort((a, b) => (a.exact ? 0 : 1) - (b.exact ? 0 : 1));
  }

  const pills = [];
  const pill = (filter, label) =>
    pills.push(`<a class="qpill" href="${href(set, "search", queryWithout(pq, filter))}" title="Remove this filter">${esc(label)}<span class="qpill-x" aria-hidden="true">×</span><span class="sr-only"> (remove filter)</span></a>`);
  if (pq.rc) pill(pq.rc, "Rookie cards");
  if (fmtF) pill(pq.fmt, "In " + fmtF.label);
  if (pq.tier) pill(pq.tier, (TIER_BY_ID[pq.tier.id] || { label: pq.tier.id }).label);

  let html = `<div class="view-head"><div><h1 class="view-title" tabindex="-1">Results for “${esc(q)}”</h1>
    <p class="view-sub">${[
      total ? `${fmtInt(total)} ${plural(total, "card")} in ${groups.length} ${plural(groups.length, "section")}` : "",
      parHits.length ? `${parHits.length} ${plural(parHits.length, "parallel")}` : "",
      secHits.length ? `${secHits.length} ${plural(secHits.length, "section")}${T.length ? " by name" : ""}` : "",
    ].filter(Boolean).join(" · ") || "No matches"}</p>
    ${pills.length ? `<div class="qpills"><span class="qpills-label">Filtered to</span>${pills.join("")}</div>` : ""}</div></div>`;

  const phrase = fold(T.join(" "));
  let one = null;
  if (players.size === 1) one = players.values().next().value;
  else if (players.size > 1 && players.has(phrase)) one = players.get(phrase);
  if (one) {
    const p = one;
    const catLabel = (id) => (set.categories.find((c) => c.id === id) || { label: id }).label;
    const info = set._players.get(p.key);
    const isRookie = !!(info && info.rookie);
    const rcNote = !isRookie && info && info.rcCards
      ? `<span class="rc-partial" title="Topps flags only some of this player's cards as rookie cards">RC on ${info.rcCards} of ${info.cards} cards</span>`
      : "";
    html += `<section class="player-card">
      <div class="player-avatar" aria-hidden="true">${esc(initials(p.name))}</div>
      <div><h2 class="player-name">${esc(p.name)}${isRookie ? rcBadge() : ""}</h2>
      <p class="muted">${esc(Array.from(p.teams).filter(Boolean).join(" / "))}${rcNote ? " · " + rcNote : ""}</p></div>
      <ul class="player-cats">${Object.keys(p.cats).map((k) => `<li><b>${p.cats[k]}</b> ${esc(catLabel(k))}</li>`).join("")}</ul>
    </section>`;
  } else if (players.size >= 2 && players.size <= 6) {
    const list = Array.from(players.values()).sort((a, b) => b.cards - a.cards || a.name.localeCompare(b.name));
    html += `<div class="player-pills" role="group" aria-label="Matching players"><span class="qpills-label">Players</span>${list
      .map((p) => `<a class="qpill qpill--player" href="${href(set, "search", p.name)}">${highlight(p.name, T)}<span class="qpill-n">${p.cards}</span></a>`)
      .join("")}</div>`;
  }

  if (secHits.length) {
    html += `<h2 class="group-title">Sections</h2><div class="sec-links">${secHits
      .map((s) => {
        const v = val(s.odds, fmt.id);
        const best = v ? null : sectionBestN(s, fmt.id);
        const odds = v ? oddsHTML(v, fmt) : best ? `<span class="odds">1:${fmtInt(best)}</span>` : "";
        return `<a class="sec-link" href="${href(set, s.category, s.id)}"><span>${highlight(s.name, T.length ? T : pq.words)}</span>${tierBadge(s.tier, set, "", { section: s, fmt })}${odds && fmtF ? `<span class="sec-link-odds">${odds}</span>` : ""}<span class="muted">${fmtInt(s.cardCount)} cards</span></a>`;
      })
      .join("")}</div>`;
  }
  if (parHits.length) {
    const showAll = !!state.searchAllParallels;
    const list = showAll ? parHits : parHits.slice(0, MAX_PARALLELS);
    html += `<h2 class="group-title">Parallels${fmtF || state.chipSort === "rarity" ? ` <span class="group-sub">${state.chipSort === "rarity" ? "most common first" : ""}${fmtF ? `${state.chipSort === "rarity" ? ", " : ""}odds in ${esc(fmt.label)}` : ""}</span>` : ""}</h2><div class="rainbow rainbow--search">${list
      .map(({ s, p }) => {
        const v = val(p.odds, fmt.id);
        return `<button type="button" class="chip chip--wide${v ? "" : " is-na"}" data-preview data-sec="${esc(s.id)}" data-par="${esc(p.id)}" title="${esc(p.name + " — " + s.name)}">${dotHTML(chipSw(s, p))}<span class="chip-name"><span>${highlight(p.name, T)}</span><span class="chip-sec">${esc(s.name)}</span></span><span class="chip-odds">${v ? esc(v.raw) : "—"}</span></button>`;
      })
      .join("")}</div>`;
    if (parHits.length > MAX_PARALLELS) {
      html += `<p class="more-note">${showAll ? `Showing all ${parHits.length} parallels.` : `Showing ${MAX_PARALLELS} of ${parHits.length} parallels — refine your search, or`} <button type="button" class="link-btn" data-action="search-parallels" aria-expanded="${showAll}">${showAll ? `Show the first ${MAX_PARALLELS}` : "show all"}</button></p>`;
    }
  }

  if (groups.length) {
    let budget = MAX_ROWS;
    const filterQ = T.join(" ");
    html += `<h2 class="group-title">Cards</h2>`;
    for (const g of groups) {
      if (budget <= 0) break;
      const shown = g.hits.slice(0, budget);
      budget -= shown.length;
      const v = val(g.s.odds, fmt.id);
      html += `<section class="result-group">
        <a class="result-head" href="${href(set, g.s.category, g.s.id)}" data-filter-sec="${esc(g.s.id)}" data-filter-q="${esc(filterQ)}" data-filter-rc="${pq.rc ? 1 : 0}" title="Open ${esc(g.s.name)} filtered to these cards">
          <span class="result-name">${esc(g.s.name)}</span>
          <span class="result-cat">${esc((set.categories.find((c) => c.id === g.s.category) || {}).label || "")}</span>
          ${tierBadge(g.s.tier, set, "", { section: g.s, fmt })}
          <span class="result-odds">${v ? oddsHTML(v, fmt) : ""}</span>
          <span class="result-count" title="${g.hits.length} matching ${plural(g.hits.length, "card")}">${g.hits.length}</span>
        </a>
        <div class="table-wrap"><table class="cards cards--compact"><tbody>${shown
          .map(({ c }) => {
            const multi = c.players.length > 1;
            const cells = cardCells(c, T);
            return `<tr${multi ? ' class="is-multi"' : ""}><td class="c-code">${cells.code}</td><td class="c-player">${cells.player}</td><td class="c-team">${cells.team}</td></tr>`;
          })
          .join("")}</tbody></table></div>
      </section>`;
    }
    if (total > MAX_ROWS) html += `<p class="muted pad">Showing the first ${MAX_ROWS} cards — refine your search to see more.</p>`;
  }
  if (!groups.length && !parHits.length && !secHits.length) {
    html += `<div class="empty"><div class="empty-art" aria-hidden="true"></div><p>Nothing matches “${esc(q)}”.</p><p class="muted">Try a last name, a team, a card number like <code>RA-</code>, a parallel like <code>gold</code>, or add <code>rc</code>, <code>mega</code> or <code>case hit</code> to filter.</p></div>`;
  }
  return html;
}

function initials(name) {
  return name
    .split(/\s+/)
    .filter((w) => /^[A-Za-zÀ-ÿ]/.test(w) && !/^(jr|sr|ii|iii)\.?$/i.test(w))
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

/* ---------------------------------------------------------------- preview context */

/** Data for the floating preview of a chip / parallel name. */
export function previewContext(set, fmt, secId, parId) {
  const s = set._sectionById[secId];
  if (!s) return null;
  const p = parId ? (s.parallels || []).find((x) => x.id === parId) : null;
  if (parId && !p) return null;
  const odds = p ? p.odds : s.odds;
  const first = s.cards.find((c) => c.players.some((pl) => pl.name)) || s.cards[0];
  const pl = first ? first.players.find((x) => x.name) || first.players[0] : null;
  const rows = set.formats.map((f) => {
    const v = val(odds, f.id);
    return { label: f.label, odds: oddsHTML(v, f), rate: v ? rateText(nOf(v), f) : "", active: f.id === fmt.id };
  });
  const avail = availableFormats(odds, set);
  const note = avail.length ? exclusiveLabel(avail, set) : "No odds listed";
  return {
    kicker: s.name,
    title: p ? p.name : "Base version",
    sw: swatchFor(p ? p.name : "", { section: s.name, seed: s.id + "/" + (p ? p.id : "") }),
    image: p ? p.image : s.image,
    info: { player: pl ? pl.name || pl.team : "", team: pl && pl.name ? pl.team : "", code: first ? first.code : "" },
    rows,
    note,
  };
}
