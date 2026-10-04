// Floating parallel preview: hover / keyboard focus / tap any element with [data-preview].
// Shows the parallel's example image when the data has one, otherwise a generated card mock.
import { esc } from "./util.js";
import { swatchAttrs, describe } from "./swatch.js";

const SILHOUETTE = `<svg class="mock-player" viewBox="0 0 100 130" aria-hidden="true" focusable="false">
  <path d="M71 38 L93 4" stroke="currentColor" stroke-width="4.2" stroke-linecap="round"/>
  <circle cx="50" cy="25" r="10"/>
  <path d="M39 22 Q50 9 61 21 L66 24 L58 23 Q50 18 41 24 Z"/>
  <path d="M37 40 Q50 33 63 39 L72 40 L75 36 L78 39 L72 47 L64 47 L66 76 Q51 80 37 76 L39 55 L30 63 L26 59 Z"/>
  <path d="M38 75 L29 118 L38 120 L50 86 L57 120 L67 118 L65 75 Z"/>
</svg>`;

/** Generated card mock (2.5 x 3.5) for a swatch. */
export function mockHTML(sw, info) {
  info = info || {};
  const tag = sw.fx.includes("variation") ? `<span class="mock-tag">VAR</span>` : "";
  const serial = sw.fx.includes("oneofone") ? `<span class="mock-serial">1/1</span>` : "";
  const plate = sw.pattern === "plate" ? `<span class="mock-plateid">${esc((sw.plateId || "").toUpperCase())}</span>` : "";
  return `<div class="mock" ${swatchAttrs(sw)} aria-hidden="true">
    <div class="mock-frame">
      <div class="mock-photo">${SILHOUETTE}</div>
      <div class="mock-plate">
        <span class="mock-name">${esc(info.player || "Player Name")}</span>
        <span class="mock-team">${esc(info.team || "")}</span>
      </div>
      <span class="mock-logo">CHROME</span>
      ${info.code ? `<span class="mock-code">${esc(info.code)}</span>` : ""}
    </div>
    <div class="mock-pattern"></div>
    <div class="mock-sheen"></div>
    ${tag}${serial}${plate}
  </div>`;
}

/** Tiny chip swatch. */
export function dotHTML(sw) {
  return `<span class="sw" ${swatchAttrs(sw)} aria-hidden="true"><span class="sw-pat"></span></span>`;
}

/**
 * @param {(el: Element) => (null | {kicker, title, sw, image, info, rows: [{label, odds, rate, active}], note})} resolve
 */
export function initPreview(resolve) {
  const pop = document.createElement("div");
  pop.className = "preview";
  pop.id = "parallel-preview";
  pop.setAttribute("role", "tooltip");
  pop.hidden = true;
  document.body.appendChild(pop);

  let anchor = null;
  let pinned = false;
  let showTimer = 0;
  let hideTimer = 0;
  let raf = 0;

  function render(el) {
    const ctx = resolve(el);
    if (!ctx) return false;
    const visual = ctx.image
      ? `<img class="pv-img" src="${esc(ctx.image)}" alt="Example: ${esc(ctx.title)}" loading="eager" decoding="async">`
      : mockHTML(ctx.sw, ctx.info);
    let desc = describe(ctx.sw);
    if (desc.toLowerCase() === String(ctx.title).toLowerCase()) desc = "";
    const rows = ctx.rows
      .map(
        (r) => `<div class="pv-row${r.active ? " is-active" : ""}${r.odds.indexOf("odds--none") > -1 ? " is-none" : ""}">
          <span class="pv-fmt">${esc(r.label)}</span><span class="pv-val">${r.odds}</span><span class="pv-rate">${esc(r.rate || "")}</span></div>`
      )
      .join("");
    pop.innerHTML = `<button type="button" class="pv-close" aria-label="Close preview" title="Close (Esc)"><span aria-hidden="true">×</span></button>
      <div class="pv-visual">${visual}</div>
      <div class="pv-info">
        <div class="pv-kicker" title="${esc(ctx.kicker || "")}">${esc(ctx.kicker || "")}</div>
        <div class="pv-title">${esc(ctx.title)}</div>
        ${desc ? `<div class="pv-desc">${esc(desc)}</div>` : ""}
        <div class="pv-rows">${rows}</div>
        <div class="pv-foot">${ctx.image ? "Example image" : "Illustration — not the actual card design"}${ctx.note ? " · " + esc(ctx.note) : ""}</div>
      </div>`;
    const img = pop.querySelector(".pv-img");
    if (img) {
      img.addEventListener("error", () => {
        img.outerHTML = mockHTML(ctx.sw, ctx.info);
      }, { once: true });
    }
    return true;
  }

  function place() {
    if (!anchor || pop.hidden) return;
    if (!anchor.isConnected) return hide(true);
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    if (vw < 560) {
      pop.classList.add("is-sheet");
      pop.style.left = pop.style.top = "";
      return;
    }
    pop.classList.remove("is-sheet");
    const r = anchor.getBoundingClientRect();
    if (r.bottom < 0 || r.top > vh) return hide(true);
    const w = pop.offsetWidth;
    const h = pop.offsetHeight;
    let top = r.bottom + 10;
    if (top + h > vh - 8 && r.top - h - 10 > 8) top = r.top - h - 10;
    top = Math.max(8, Math.min(top, vh - h - 8));
    let left = r.left + r.width / 2 - w / 2;
    left = Math.max(8, Math.min(left, vw - w - 8));
    pop.style.left = Math.round(left) + "px";
    pop.style.top = Math.round(top) + "px";
  }

  /** On phones the sheet covers the bottom of the screen: nudge the page so the tapped chip stays visible. */
  function revealAnchor() {
    if (!anchor || !pop.classList.contains("is-sheet")) return;
    const a = anchor.getBoundingClientRect();
    const sheetTop = pop.getBoundingClientRect().top;
    if (a.bottom > sheetTop - 8) window.scrollBy(0, a.bottom - sheetTop + 16);
  }

  function show(el, pin) {
    clearTimeout(hideTimer);
    clearTimeout(showTimer);
    const wasHidden = pop.hidden;
    if (anchor !== el || wasHidden) {
      if (anchor) anchor.removeAttribute("aria-describedby");
      if (!render(el)) return;
      anchor = el;
      el.setAttribute("aria-describedby", pop.id);
      pop.hidden = false;
      // animate only when appearing; moving between chips just swaps the content (no blink)
      if (wasHidden) {
        pop.classList.remove("is-in");
        void pop.offsetWidth;
        pop.classList.add("is-in");
      }
    }
    if (pin != null) pinned = pin;
    pop.classList.toggle("is-pinned", pinned);
    place();
    if (pin) revealAnchor();
  }

  function hide(force) {
    clearTimeout(showTimer);
    if (pinned && !force) return;
    pinned = false;
    pop.classList.remove("is-pinned");
    if (anchor) anchor.removeAttribute("aria-describedby");
    anchor = null;
    pop.hidden = true;
  }

  const target = (e) => (e.target && e.target.closest ? e.target.closest("[data-preview]") : null);

  document.addEventListener("pointerover", (e) => {
    if (e.pointerType !== "mouse") return;
    const el = target(e);
    if (!el) return;
    if (pinned && anchor !== el) return;
    clearTimeout(hideTimer);
    clearTimeout(showTimer);
    showTimer = setTimeout(() => {
      // a click may have pinned another preview while this hover was pending
      if (pinned && anchor !== el) return;
      show(el);
    }, anchor ? 0 : 90);
  });
  document.addEventListener("pointerout", (e) => {
    if (e.pointerType !== "mouse") return;
    const el = target(e);
    if (!el || (e.relatedTarget && el.contains(e.relatedTarget))) return;
    clearTimeout(showTimer);
    if (!pinned) hideTimer = setTimeout(() => hide(), 120);
  });
  document.addEventListener("focusin", (e) => {
    const el = target(e);
    if (el && el.matches(":focus-visible")) show(el);
  });
  document.addEventListener("focusout", (e) => {
    const el = target(e);
    if (el && !pinned) hide();
  });
  document.addEventListener("click", (e) => {
    if (pop.contains(e.target)) {
      // taps on the sheet keep it open; only the close button dismisses it
      if (e.target.closest(".pv-close")) {
        const back = anchor;
        hide(true);
        if (back && back.isConnected && e.detail === 0) back.focus();
      }
      return;
    }
    const el = target(e);
    if (el) {
      if (pinned && anchor === el) hide(true);
      else show(el, true);
      return;
    }
    if (pinned && !pop.contains(e.target)) hide(true);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !pop.hidden) {
      hide(true);
      e.preventDefault();
    }
  });
  // swipe the phone sheet down to dismiss it
  let touchY = null;
  pop.addEventListener("touchstart", (e) => {
    touchY = pop.classList.contains("is-sheet") && e.touches.length === 1 ? e.touches[0].clientY : null;
  }, { passive: true });
  pop.addEventListener("touchend", (e) => {
    if (touchY == null) return;
    const dy = e.changedTouches[0].clientY - touchY;
    touchY = null;
    if (dy > 40) hide(true);
  }, { passive: true });

  const onMove = () => {
    if (pop.hidden) return;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(place);
  };
  window.addEventListener("scroll", onMove, { passive: true, capture: true });
  window.addEventListener("resize", onMove);

  return {
    hide: () => hide(true),
    refresh: () => {
      if (anchor && !pop.hidden) render(anchor) && place();
    },
    isOpen: () => !pop.hidden,
  };
}
