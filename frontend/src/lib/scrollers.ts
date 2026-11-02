/** Tables and charts that are wider than a phone scroll sideways inside their box. A box that scrolls
 * must be reachable from the keyboard (WCAG 2.1.1), so any such box that overflows gets tabindex=0,
 * and loses it again when the screen is wide enough. Watches the DOM, so every page is covered. */
const SCROLLERS = ".tbl, .table-wrap, .table-scroll, .tbl-wrap, .results";

function mark(): void {
  for (const el of document.querySelectorAll<HTMLElement>(SCROLLERS)) {
    const scrolls = el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== "visible";
    if (scrolls && !el.hasAttribute("tabindex")) {
      el.setAttribute("tabindex", "0");
      el.dataset.scrollFocus = "1"; // ours to remove; a tabindex set by the page itself is left alone
    } else if (!scrolls && el.dataset.scrollFocus) {
      el.removeAttribute("tabindex");
      delete el.dataset.scrollFocus;
    }
  }
}

export function keepScrollersFocusable(): void {
  let queued = false;
  const later = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      mark();
    });
  };
  new MutationObserver(later).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", later);
}
