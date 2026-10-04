// Topps Checklists — static site entry point. Routing, state, header controls, event wiring.
import { esc, fold, store, debounce, fmtInt } from "./util.js";
import { primaryFormat } from "./odds.js";
import { categoryView, overviewView, searchView, sectionCard, sectionBody, previewContext, cardCells, rookieOrder } from "./views.js";
import { initPreview } from "./preview.js";

const CATEGORY_IDS = ["base", "inserts", "case-hits", "autographs", "relics"];

const params = new URLSearchParams(location.search);
let DATA_ROOT = params.get("data") || "data/";
if (!DATA_ROOT.endsWith("/")) DATA_ROOT += "/";

const state = {
  index: null,
  cache: new Map(),
  set: null,
  route: null,
  format: null,
  expanded: new Set(),
  showNA: new Set(),
  filters: {},
  bodyTab: {},
  chipSort: store.get("tc.chipSort") === "pdf" ? "pdf" : "rarity",
  sectionSort: "checklist",
  onlyInFmt: false,
  rookiesAll: false,
  searchAllParallels: false,
  lastHash: "",
};

const $ = (sel) => document.querySelector(sel);
const main = $("#main");
const setSelect = $("#set-select");
const fmtSelect = $("#format-select");
const searchInput = $("#search");
const tabs = $("#tabs");

/* ---------------------------------------------------------------- data */

async function fetchJSON(url) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${url}`);
  return res.json();
}

/** Add derived lookups used by the views (prefixed with _ so they never collide with schema keys). */
function prepare(set) {
  set._sectionById = {};
  set._byCategory = {};
  set._visible = [];
  CATEGORY_IDS.forEach((c) => (set._byCategory[c] = []));
  // every named player: card counts, and whether Topps flags them as a rookie
  const people = new Map();
  for (const s of set.sections) {
    if (s.hidden) continue;
    set._visible.push(s);
    set._sectionById[s.id] = s;
    (set._byCategory[s.category] = set._byCategory[s.category] || []).push(s);
    s._s = fold(s.name + " " + s.rawName);
    s.parallels = s.parallels || [];
    s.cards = s.cards || [];
    for (const p of s.parallels) p._s = fold(p.name);
    for (const c of s.cards) {
      c.players = c.players || [];
      c._s = fold([c.code].concat(c.players.map((p) => p.name + " " + p.team)).join(" "));
      for (const p of c.players) {
        if (!p.name) continue;
        const key = fold(p.name);
        let e = people.get(key);
        if (!e) {
          e = { name: p.name, team: p.team, code: "", rcCode: "", cards: 0, rcCards: 0, sections: 0, _seen: new Set(), base: false, baseRookie: false };
          people.set(key, e);
        }
        e.cards += 1;
        if (p.rookie) {
          e.rcCards += 1;
          if (!e.rcCode) e.rcCode = c.code;
        }
        if (!e._seen.has(s.id)) {
          e._seen.add(s.id);
          e.sections += 1;
        }
        if (s.kind === "base") {
          // the base-set card decides rookie status and the card number shown
          if (!e.base) {
            e.base = true;
            e.code = c.code;
            e.team = p.team;
          }
          if (p.rookie) e.baseRookie = true;
        } else if (!e.code && !e.base) e.code = c.code;
      }
    }
  }
  for (const e of people.values()) {
    // a player with a base card is a rookie only if that card is flagged; otherwise any RC flag counts.
    // (Topps sometimes flags a single variation card, e.g. an award-winner variation, for a non-rookie.)
    e.rookie = e.base ? e.baseRookie : e.rcCards > 0;
    if (e.rookie && !e.base && e.rcCode) e.code = e.rcCode;
    delete e._seen;
  }
  set._players = people;
  set._rookies = Array.from(people.values()).filter((e) => e.rookie).sort(rookieOrder);
  for (const c of set.categories) c.sectionCount = (set._byCategory[c.id] || []).length;
  return set;
}

async function loadSet(slug) {
  if (state.cache.has(slug)) return state.cache.get(slug);
  const set = prepare(await fetchJSON(DATA_ROOT + encodeURIComponent(slug) + ".json"));
  state.cache.set(slug, set);
  return set;
}

/* ---------------------------------------------------------------- routing */

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const raw = h.split("/");
  const dec = (x) => {
    try {
      return decodeURIComponent(x || "");
    } catch (e) {
      return x || "";
    }
  };
  const slug = dec(raw[0]);
  if (raw[1] === "search") return { slug, view: "search", query: dec(raw.slice(2).join("/")) };
  if (raw[1] && CATEGORY_IDS.includes(raw[1])) {
    return { slug, view: "category", category: raw[1], sectionId: raw[2] ? dec(raw[2]) : null, bad: raw.length > 3 };
  }
  // an unrecognised category segment falls back to the overview (and the URL is corrected)
  return { slug, view: "overview", bad: raw.length > 1 && !!raw.slice(1).join("") };
}

function routeHash(r) {
  const base = "#/" + encodeURIComponent(r.slug);
  if (r.view === "search") return base + "/search/" + encodeURIComponent(r.query || "");
  if (r.view === "category") return base + "/" + r.category + (r.sectionId ? "/" + encodeURIComponent(r.sectionId) : "");
  return base;
}

/* History entries carry a small key so back/forward can restore where the reader was. */
if ("scrollRestoration" in history) history.scrollRestoration = "manual";
const SCROLL_KEY = "tc.scroll";
const scrollPos = new Map();
try {
  const savedPos = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "[]");
  if (Array.isArray(savedPos)) savedPos.slice(-60).forEach(([k, y]) => scrollPos.set(k, y));
} catch (e) {
  /* storage blocked: positions just won't survive a reload */
}
let entrySeq = 0;
const entryKey = () => (history.state && history.state.tcKey) || null;
function ensureEntryKey() {
  if (entryKey()) return entryKey();
  const k = Date.now().toString(36) + "-" + ++entrySeq;
  history.replaceState(Object.assign({}, history.state, { tcKey: k }), "", location.href);
  return k;
}
/** replaceState that keeps this entry's scroll key. */
function replaceHash(h) {
  history.replaceState(history.state, "", h);
}
let saveTimer = 0;
function rememberScroll() {
  const k = entryKey();
  if (!k || !state.route) return;
  scrollPos.set(k, window.scrollY);
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      sessionStorage.setItem(SCROLL_KEY, JSON.stringify(Array.from(scrollPos.entries()).slice(-60)));
    } catch (e) {
      /* ignore */
    }
  }, 250);
}
window.addEventListener("scroll", rememberScroll, { passive: true });

function currentFormat() {
  const set = state.set;
  return set.formats.find((f) => f.id === state.format) || primaryFormat(set) || { id: "_", label: "—" };
}

function ctx() {
  return { set: state.set, fmt: currentFormat(), state, route: state.route };
}

let routeSeq = 0;
// the history entry created by typing into the search box (so clearing it can step back instead of pushing)
let pendingSearchPush = false;
let searchEntryKey = null;
async function onRoute(opts) {
  opts = opts || {};
  const seq = ++routeSeq;
  const r = parseHash();
  // a known entry key with a saved position means back/forward (or reload): restore instead of jumping
  const restoreY = entryKey() && scrollPos.has(entryKey()) ? scrollPos.get(entryKey()) : null;
  const known = state.index.sets.some((s) => s.slug === r.slug);
  if (!known) {
    r.slug = state.index.sets[0].slug;
    if (r.view === "search") r.view = r.query ? "search" : "overview";
    r.bad = true;
  }
  const prev = state.route;
  if (!state.set || state.set.slug !== r.slug) {
    if (!state.cache.has(r.slug)) main.innerHTML = loadingHTML();
    try {
      const set = await loadSet(r.slug);
      if (seq !== routeSeq) return;
      state.set = set;
      state.expanded = new Set();
      state.showNA = new Set();
      state.filters = {};
      state.bodyTab = {};
      state.rookiesAll = false;
    } catch (err) {
      if (seq !== routeSeq) return;
      main.innerHTML = errorHTML(`Couldn't load this set.`, err);
      return;
    }
  }
  if (r.view === "category" && r.sectionId) {
    const s = state.set._sectionById[r.sectionId];
    if (s && s.category === r.category) state.expanded.add(r.sectionId);
    else if (s) {
      // section lives in another tab: fix the link
      r.category = s.category;
      r.bad = true;
      state.expanded.add(r.sectionId);
    } else {
      r.sectionId = null;
      r.bad = true;
    }
  }
  if (r.bad) replaceHash(routeHash(r));
  delete r.bad;
  if (r.view === "search" && (!prev || prev.view !== "search" || prev.query !== r.query)) state.searchAllParallels = false;
  state.route = r;
  if (state.format == null || !state.set.formats.some((f) => f.id === state.format)) {
    const saved = store.get("tc.format");
    state.format = state.set.formats.some((f) => f.id === saved) ? saved : (primaryFormat(state.set) || {}).id;
  }
  const hadFocusInMain = main.contains(document.activeElement) || tabs.contains(document.activeElement);
  renderChrome();
  renderMain();
  ensureEntryKey();
  if (pendingSearchPush) {
    pendingSearchPush = false;
    if (r.view === "search") searchEntryKey = entryKey();
  }
  const sameView = prev && prev.slug === r.slug && prev.view === r.view && prev.category === r.category;
  const searchUpdate = sameView && r.view === "search" && opts.fromSearch;
  if (restoreY != null && !searchUpdate) {
    window.scrollTo(0, restoreY);
  } else if (r.view === "category" && r.sectionId) {
    const el = document.getElementById("sec-" + r.sectionId);
    if (el) {
      const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
      requestAnimationFrame(() => el.scrollIntoView({ behavior: sameView && !reduce ? "smooth" : "auto", block: "start" }));
    }
  } else if (!(sameView && r.view === "search")) {
    window.scrollTo(0, 0);
  }
  if (!searchUpdate && prev) announceRoute(hadFocusInMain);
}

/** Tell assistive tech about the new view; move focus to its heading when the old focus target is gone. */
function announceRoute(hadFocusInMain) {
  const live = document.getElementById("route-announcer");
  if (live) {
    live.textContent = "";
    setTimeout(() => (live.textContent = document.title.replace(/ · Topps Checklists$/, "")), 60);
  }
  const active = document.activeElement;
  const lost = !active || active === document.body || !active.isConnected;
  if (lost || hadFocusInMain) {
    const h1 = main.querySelector("h1");
    if (h1) {
      if (!h1.hasAttribute("tabindex")) h1.setAttribute("tabindex", "-1");
      h1.focus({ preventScroll: true });
    }
  }
}

/* ---------------------------------------------------------------- rendering */

function renderChrome() {
  const set = state.set;
  const r = state.route;
  setSelect.innerHTML = state.index.sets
    .map((s) => `<option value="${esc(s.slug)}"${s.slug === set.slug ? " selected" : ""}>${esc(s.name)}</option>`)
    .join("");
  setSelect.disabled = state.index.sets.length < 2;
  const fmt = currentFormat();
  fmtSelect.innerHTML = set.formats
    .map((f) => `<option value="${esc(f.id)}"${f.id === fmt.id ? " selected" : ""}>${esc(f.label)}</option>`)
    .join("");
  const base = "#/" + encodeURIComponent(set.slug);
  const tab = (href, label, count, on) =>
    `<a class="tab${on ? " is-on" : ""}" href="${href}"${on ? ' aria-current="page"' : ""}><span>${esc(label)}</span>${count != null ? `<span class="tab-count">${count}</span>` : ""}</a>`;
  tabs.innerHTML =
    `<div class="tabs-inner">` +
    tab(base, "Overview", null, r.view === "overview") +
    set.categories.map((c) => tab(base + "/" + c.id, c.label, c.sectionCount, r.view === "category" && r.category === c.id)).join("") +
    `</div>`;
  const inner = tabs.firstElementChild;
  const onTab = tabs.querySelector(".is-on");
  if (onTab && inner.scrollWidth > inner.clientWidth) inner.scrollLeft = Math.max(0, onTab.offsetLeft - 16);
  searchInput.disabled = false;
  fmtSelect.disabled = false;
  if (r.view === "search") {
    // keep what the reader is typing (e.g. a trailing space), but follow back/forward to another query
    if (searchInput.value.trim() !== (r.query || "").trim()) searchInput.value = r.query || "";
  } else if (document.activeElement !== searchInput || !searchInput.value.trim()) {
    searchInput.value = "";
  }
  const viewLabel =
    r.view === "search" ? `“${r.query}”` : r.view === "category" ? (set.categories.find((c) => c.id === r.category) || {}).label : "Overview";
  document.title = `${viewLabel} · ${set.name} · Topps Checklists`;
}

function renderMain() {
  const c = ctx();
  const v = state.route.view;
  main.dataset.view = v;
  main.innerHTML = v === "overview" ? overviewView(c) : v === "search" ? searchView(c) : categoryView(c);
  main.querySelectorAll(".sec.is-open").forEach((el) => applyFilter(el));
}

function rerenderKeepingScroll() {
  const y = window.scrollY;
  renderMain();
  window.scrollTo(0, y);
  preview.refresh();
}

function rerenderSection(id) {
  const el = document.getElementById("sec-" + id);
  const s = state.set._sectionById[id];
  if (!el || !s) return;
  const tmp = document.createElement("div");
  tmp.innerHTML = sectionCard(s, ctx());
  const fresh = tmp.firstElementChild;
  el.replaceWith(fresh);
  if (state.expanded.has(id)) applyFilter(fresh);
  return fresh;
}

function loadingHTML() {
  return `<div class="loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading checklist…</div>`;
}

function errorHTML(title, err) {
  const local = /^(localhost|127\.0\.0\.1|\[::1\]|.*\.localhost|.*\.test)$/i.test(location.hostname);
  const detail = esc(err && err.message ? err.message : String(err));
  return `<div class="empty empty--error" role="alert"><div class="empty-art" aria-hidden="true"></div>
    <h1 class="view-title" tabindex="-1">${esc(title)}</h1>
    <p>The checklist data couldn't be loaded. Check your connection and try again.</p>
    <p><button type="button" class="btn" data-action="retry">Try again</button></p>
    ${local ? `<details class="dev-hint"><summary>Developer details</summary><p class="muted">${detail}</p>
    <p class="muted">Generate the data with <code>python -m pipeline build</code>, then serve the <code>site/</code> folder (for example <code>python -m http.server -d site</code>).</p></details>` : ""}</div>`;
}

/* ---------------------------------------------------------------- section interactions */

function toggleSection(id, open) {
  const el = document.getElementById("sec-" + id);
  const s = state.set._sectionById[id];
  if (!el || !s) return;
  const willOpen = open == null ? !state.expanded.has(id) : open;
  const body = el.querySelector(".sec-body");
  const btn = el.querySelector(".sec-toggle");
  if (willOpen) {
    state.expanded.add(id);
    if (!body.childElementCount) body.innerHTML = sectionBody(s, ctx());
    body.hidden = false;
    el.classList.add("is-open");
    applyFilter(el);
  } else {
    state.expanded.delete(id);
    body.hidden = true;
    el.classList.remove("is-open");
  }
  btn.setAttribute("aria-expanded", String(willOpen));
}

function applyFilter(el) {
  const id = el.dataset.sec;
  const s = state.set._sectionById[id];
  const table = el.querySelector("table.cards");
  if (!s || !table) return;
  const f = state.filters[id] || { q: "", rc: false };
  const tokens = fold(f.q).split(" ").filter(Boolean);
  const hlKey = tokens.join(" ");
  let shown = 0;
  const rows = table.tBodies[0].rows;
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const card = s.cards[+row.dataset.i];
    const ok = (!f.rc || card.rookie) && tokens.every((t) => card._s.indexOf(t) !== -1);
    row.hidden = !ok;
    if (ok) shown++;
    // highlight the match in visible rows (re-render only when the tokens changed)
    const want = ok ? hlKey : "";
    if ((row.dataset.hl || "") !== want) {
      const c = cardCells(card, want ? tokens : null);
      row.cells[0].innerHTML = c.code;
      row.cells[1].innerHTML = c.player;
      row.cells[2].innerHTML = c.team;
      row.dataset.hl = want;
    }
  }
  const count = el.querySelector(".table-count");
  if (count) count.textContent = tokens.length || f.rc ? `${fmtInt(shown)} of ${fmtInt(rows.length)}` : `${fmtInt(rows.length)} cards`;
  const none = el.querySelector(".no-match");
  if (none) none.hidden = shown > 0;
}

function setSectionRoute(id, open) {
  const r = Object.assign({}, state.route, { sectionId: open ? id : null });
  state.route = r;
  replaceHash(routeHash(r));
}

main.addEventListener("click", (e) => {
  // following a search result header opens the section already filtered to the query
  const fh = e.target.closest("[data-filter-sec]");
  if (fh && main.contains(fh)) {
    state.filters[fh.dataset.filterSec] = { q: fh.dataset.filterQ || "", rc: fh.dataset.filterRc === "1" };
    return;
  }
  let a = e.target.closest("[data-action]");
  if (!a || !main.contains(a)) {
    // the whole section header toggles, not just the name button
    const head = e.target.closest(".sec-head");
    if (!head || e.target.closest("a, button, input, label, [data-preview]")) return;
    if (window.getSelection && String(window.getSelection()).length) return;
    a = head.querySelector(".sec-toggle");
    if (!a) return;
  }
  const action = a.dataset.action;
  const secEl = a.closest(".sec");
  const id = secEl && secEl.dataset.sec;
  switch (action) {
    case "toggle": {
      toggleSection(id);
      setSectionRoute(id, state.expanded.has(id));
      break;
    }
    case "collapse-sec": {
      toggleSection(id, false);
      setSectionRoute(id, false);
      const head = secEl.querySelector(".sec-toggle");
      const top = secEl.getBoundingClientRect().top;
      const fullHeader = document.querySelector(".top").offsetHeight;
      // scrolling up brings the (phone) header rows back, so clear the full header height
      if (top < fullHeader) window.scrollTo(0, Math.max(0, top + window.scrollY - fullHeader - 12));
      if (head) head.focus({ preventScroll: true });
      break;
    }
    case "more-chips": {
      if (state.showNA.has(id)) state.showNA.delete(id);
      else state.showNA.add(id);
      const fresh = rerenderSection(id);
      const btn = fresh && fresh.querySelector('[data-action="more-chips"]');
      if (btn) btn.focus();
      break;
    }
    case "chip-sort":
      state.chipSort = a.dataset.value;
      store.set("tc.chipSort", state.chipSort);
      rerenderKeepingScroll();
      break;
    case "section-sort":
      state.sectionSort = a.dataset.value;
      rerenderKeepingScroll();
      break;
    case "expand-all":
      main.querySelectorAll(".sec").forEach((el) => toggleSection(el.dataset.sec, true));
      break;
    case "collapse-all":
      main.querySelectorAll(".sec").forEach((el) => toggleSection(el.dataset.sec, false));
      if (state.route.sectionId) setSectionRoute(null, false);
      break;
    case "body-tab": {
      state.bodyTab[id] = a.dataset.value;
      const s = state.set._sectionById[id];
      const body = secEl.querySelector(".sec-body");
      body.innerHTML = sectionBody(s, ctx());
      applyFilter(secEl);
      const t = body.querySelector(`[data-action="body-tab"][data-value="${a.dataset.value}"]`);
      if (t) t.focus();
      break;
    }
    case "rookies-toggle": {
      state.rookiesAll = !state.rookiesAll;
      const panel = a.closest("[data-rookies]");
      panel.classList.toggle("is-all", state.rookiesAll);
      a.setAttribute("aria-expanded", String(state.rookiesAll));
      a.textContent = state.rookiesAll ? "Show fewer" : `Show all ${state.set._rookies.length} rookies`;
      if (!state.rookiesAll && panel.getBoundingClientRect().top < 0) panel.scrollIntoView({ block: "start" });
      break;
    }
    case "search-parallels":
      state.searchAllParallels = !state.searchAllParallels;
      rerenderKeepingScroll();
      break;
    case "retry":
      location.reload();
      break;
    default:
      break;
  }
});

function filterRookies(input) {
  const panel = input.closest("[data-rookies]");
  const q = fold(input.value).split(" ").filter(Boolean);
  panel.classList.toggle("is-filtering", q.length > 0);
  let shown = 0;
  panel.querySelectorAll(".rookies-all li").forEach((li) => {
    const ok = q.every((t) => li.dataset.s.indexOf(t) !== -1);
    li.hidden = !ok;
    if (ok) shown++;
  });
  panel.querySelectorAll(".rookie-group").forEach((g) => (g.hidden = !g.querySelector("li:not([hidden])")));
  panel.querySelector(".rookies-none").hidden = !q.length || shown > 0;
}

main.addEventListener("input", (e) => {
  const t = e.target;
  if (t.dataset.action === "rookie-filter") return filterRookies(t);
  if (t.dataset.action !== "filter") return;
  const secEl = t.closest(".sec");
  const id = secEl.dataset.sec;
  state.filters[id] = Object.assign({ q: "", rc: false }, state.filters[id], { q: t.value });
  applyFilter(secEl);
});

main.addEventListener("change", (e) => {
  const t = e.target;
  if (t.dataset.action === "only-in-fmt") {
    state.onlyInFmt = t.checked;
    rerenderKeepingScroll();
    const again = main.querySelector('[data-action="only-in-fmt"]');
    if (again) again.focus();
    return;
  }
  if (t.dataset.action !== "rc-only") return;
  const secEl = t.closest(".sec");
  const id = secEl.dataset.sec;
  state.filters[id] = Object.assign({ q: "", rc: false }, state.filters[id], { rc: t.checked });
  applyFilter(secEl);
});

/* Arrow keys inside a parallel rainbow (one tab stop per rainbow) and the section sub-tabs. */
const ROVE_KEYS = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"];
main.addEventListener("keydown", (e) => {
  if (!ROVE_KEYS.includes(e.key) || e.altKey || e.ctrlKey || e.metaKey) return;
  const tab = e.target.closest('.subtabs [role="tab"]');
  if (tab) {
    const list = Array.from(tab.parentElement.querySelectorAll('[role="tab"]'));
    const i = list.indexOf(tab);
    const n = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? (i - 1 + list.length) % list.length : (i + 1) % list.length;
    e.preventDefault();
    if (list[n] !== tab) list[n].click();
    return;
  }
  const chip = e.target.closest("[data-rove]");
  if (!chip) return;
  const list = Array.from(chip.parentElement.querySelectorAll("[data-rove]"));
  const i = list.indexOf(chip);
  const back = e.key === "ArrowLeft" || e.key === "ArrowUp";
  const n = e.key === "Home" ? 0 : e.key === "End" ? list.length - 1 : Math.max(0, Math.min(list.length - 1, i + (back ? -1 : 1)));
  e.preventDefault();
  list[n].focus();
});
main.addEventListener("focusin", (e) => {
  const chip = e.target.closest && e.target.closest("[data-rove]");
  if (!chip) return;
  chip.parentElement.querySelectorAll("[data-rove]").forEach((c) => (c.tabIndex = c === chip ? 0 : -1));
});

/* ---------------------------------------------------------------- header controls */

setSelect.addEventListener("change", () => {
  const r = state.route || { view: "overview" };
  const next = { slug: setSelect.value, view: r.view === "category" ? "category" : "overview", category: r.category };
  location.hash = routeHash(next);
});

fmtSelect.addEventListener("change", () => {
  if (!state.set || !state.route) return;
  state.format = fmtSelect.value;
  store.set("tc.format", state.format);
  rerenderKeepingScroll();
});

const runSearch = debounce((q) => {
  if (!state.set) return;
  const query = q.trim();
  if (!query) {
    if (state.route.view !== "search") return;
    // leave search without adding a history entry: step back to where the search started, if we pushed it
    const back = state.lastHash || "#/" + encodeURIComponent(state.set.slug);
    if (searchEntryKey && searchEntryKey === entryKey() && location.hash !== back) {
      searchEntryKey = null;
      history.back();
    } else {
      replaceHash(back);
      onRoute();
    }
    return;
  }
  const h = routeHash({ slug: state.set.slug, view: "search", query });
  if (state.route.view === "search") {
    replaceHash(h);
    onRoute({ fromSearch: true });
  } else {
    state.lastHash = location.hash;
    pendingSearchPush = true;
    location.hash = h;
  }
}, 120);

searchInput.addEventListener("input", () => runSearch(searchInput.value));
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (searchInput.value) {
      searchInput.value = "";
      runSearch("");
    } else searchInput.blur();
    e.preventDefault();
  } else if (e.key === "Enter") {
    runSearch(searchInput.value);
  }
});
$("#search-form").addEventListener("submit", (e) => e.preventDefault());

document.addEventListener("keydown", (e) => {
  if (e.defaultPrevented) return;
  const tag = (e.target.tagName || "").toLowerCase();
  const typing = tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable;
  if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
    e.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
});

/* theme */
const themeBtn = $("#theme-toggle");
const darkMQ = matchMedia("(prefers-color-scheme: dark)");
function effectiveTheme() {
  return document.documentElement.dataset.theme || (darkMQ.matches ? "dark" : "light");
}
const THEME_COLOR = { light: "#f4f5f7", dark: "#0a0c11" };
function syncThemeButton() {
  const theme = effectiveTheme();
  // fixed name + pressed state ("Dark theme, pressed") instead of a label that flips with the state
  themeBtn.setAttribute("aria-label", "Dark theme");
  themeBtn.setAttribute("aria-pressed", String(theme === "dark"));
  themeBtn.title = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
  // browser chrome follows a manually chosen theme too
  if (document.documentElement.dataset.theme) {
    document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", THEME_COLOR[theme]));
  }
}
themeBtn.addEventListener("click", () => {
  const next = effectiveTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  store.set("tc.theme", next);
  syncThemeButton();
});
darkMQ.addEventListener && darkMQ.addEventListener("change", syncThemeButton);
syncThemeButton();

/* header shadow once scrolled; keep --header-h in sync so anchored sections clear the sticky header.
   On phones the header's control rows tuck away while scrolling down and return on scroll up. */
const header = $(".top");
const headerRows = $(".top-inner");
const phoneMQ = matchMedia("(max-width: 559px)");
function measureHeader() {
  document.documentElement.style.setProperty("--header-h", header.offsetHeight + "px");
  document.documentElement.style.setProperty("--tuck", headerRows.offsetHeight + 2 + "px");
}
if (window.ResizeObserver) new ResizeObserver(measureHeader).observe(header);
measureHeader();
let lastY = window.scrollY;
const onScroll = () => {
  const y = window.scrollY;
  header.classList.toggle("is-scrolled", y > 4);
  const dy = y - lastY;
  if (!phoneMQ.matches || y < header.offsetHeight || header.contains(document.activeElement)) {
    header.classList.remove("is-tucked");
    lastY = y;
  } else if (dy > 8) {
    header.classList.add("is-tucked");
    lastY = y;
  } else if (dy < -8) {
    header.classList.remove("is-tucked");
    lastY = y;
  }
};
window.addEventListener("scroll", onScroll, { passive: true });
header.addEventListener("focusin", () => header.classList.remove("is-tucked"));
onScroll();

/* ---------------------------------------------------------------- preview + boot */

const preview = initPreview((el) => {
  if (!state.set) return null;
  return previewContext(state.set, currentFormat(), el.dataset.sec, el.dataset.par || "");
});

async function boot() {
  try {
    state.index = await fetchJSON(DATA_ROOT + "sets.json");
    if (!state.index.sets || !state.index.sets.length) throw new Error("sets.json lists no sets");
  } catch (err) {
    main.innerHTML = errorHTML("No checklist data found.", err);
    return;
  }
  window.addEventListener("hashchange", onRoute);
  await onRoute();
}

boot();
