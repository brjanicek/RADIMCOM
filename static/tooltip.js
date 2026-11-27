// ---------- Tooltips: one dark tooltip of our own for every title="" of the page ----------
// The browser's tooltip cannot be styled (white on most systems) and closes on the mouse wheel. Over an element with a
// title, the title is taken off it (so the browser shows nothing) and shown in #tipBox after a short delay; a title
// the code sets meanwhile (a new level, a new state) is taken over at once, so the tooltip stays up and current, also
// while the wheel turns. When the mouse leaves, the title is put back, so the code reading el.title sees it as before.
// The titles of the outer elements (a row around a cell with its own title) and the <title> of SVG shapes are taken
// off as well while the mouse is there: otherwise the browser shows its white tooltip next to ours.
// Independent of app.js: it only needs the DOM.

(function () {
  const SHOW_MS = 450;          // about the delay of the browser's tooltip
  const box = document.createElement("div");
  box.id = "tipBox";
  box.className = "key-tip";
  box.hidden = true;
  box.setAttribute("role", "tooltip");
  document.body.appendChild(box);

  let el = null, text = "", timer = null, x = 0, y = 0, mx = 0, my = 0;   // x, y: where it opens; mx, my: the mouse now
  let off = [];                 // what was taken off: [node, title text] or [svg node, its <title> element]
  const watch = new MutationObserver(() => take());

  /** The <title> child of an SVG shape (the browser's tooltip of SVG), or null. */
  const svgTitle = (n) => (n instanceof SVGElement && !(n instanceof SVGTitleElement)
    ? Array.prototype.find.call(n.children, (c) => c instanceof SVGTitleElement) || null : null);
  const hasTip = (n) => n.hasAttribute("title") || !!svgTitle(n);
  /** The nearest element with a tooltip from n up, or null. */
  function tipOf(n) {
    for (let p = n instanceof Element ? n : null; p; p = p.parentElement) if (hasTip(p)) return p;
    return null;
  }

  /** Takes the tooltips off el and all elements around it (put back by restore). */
  function strip() {
    for (let p = el; p; p = p.parentElement) {
      const st = svgTitle(p);
      if (st) {
        off.push([p, st]);
        if (p === el) text = st.textContent;
        st.remove();
      }
      if (p !== el && p.hasAttribute("title")) {
        off.push([p, p.getAttribute("title")]);
        p.removeAttribute("title");
      }
    }
  }
  function restore() {
    for (const [n, v] of off) {
      if (typeof v === "string") { if (n.getAttribute("title") === null) n.setAttribute("title", v); }
      else if (!v.parentNode) n.insertBefore(v, n.firstChild);
    }
    off = [];
  }

  /** The title of the element under the mouse into the tooltip (and off the element). */
  function take() {
    if (!el) return;
    const t = el.getAttribute("title");
    if (t === null) return;
    watch.disconnect();
    text = t;                   // "" = no tooltip now (a canvas off its marker): hidden, never the old text again
    el.removeAttribute("title");
    watch.observe(el, { attributes: true, attributeFilter: ["title"] });
    if (!text) { box.hidden = true; return; }
    if (!box.hidden) { if (box.textContent !== text) { box.textContent = text; place(); } }
    else if (!timer) timer = setTimeout(show, SHOW_MS);   // back on a marker of the same canvas: shown again
  }

  function place() {
    const w = box.offsetWidth, h = box.offsetHeight;
    let left = x + 12, top = y + 20;
    if (left + w > window.innerWidth - 4) left = Math.max(4, window.innerWidth - w - 4);
    if (top + h > window.innerHeight - 4) top = Math.max(4, y - h - 10);
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }

  /** The element under the mouse was drawn again (a panel rebuilt by innerHTML every few seconds) while the mouse stands
   *  still: no mouseover comes, so the tooltip goes over to the element now under the mouse (-> false when there is none). */
  function follow() {
    if (!el || el.isConnected) return !!el;
    const t = tipOf(document.elementFromPoint(mx, my));
    restore();
    watch.disconnect();
    if (!t) { el = null; text = ""; box.hidden = true; return false; }
    el = t;
    strip();
    take();
    return true;
  }
  setInterval(() => { if (el && !el.isConnected && follow() && box.hidden && !timer) timer = setTimeout(show, SHOW_MS); }, 200);

  function show() {
    timer = null;
    if (el && !el.isConnected) follow();
    if (!el || !text || !el.isConnected) return;
    box.textContent = text;
    box.hidden = false;
    place();
  }

  function leave() {
    clearTimeout(timer);
    timer = null;
    watch.disconnect();
    if (el && el.getAttribute("title") === null && text && !svgTitle(el) && !off.some(([n, v]) => n === el && typeof v !== "string")) {
      el.setAttribute("title", text);                    // back, for the code
    }
    restore();
    el = null;
    text = "";
    box.hidden = true;
  }

  document.addEventListener("mouseover", (e) => {
    let t = tipOf(e.target);
    if (t === el && t) return;
    // still inside the element (its title is off it now, so the search finds none), unless an inner element has a
    // tooltip of its own
    if (el && el.contains(e.target) && !(t && el.contains(t))) return;
    // the element was drawn again (a chart redrawn every second): the new one with the same text keeps the tooltip up
    const st = t && svgTitle(t);
    if (t && el && !el.isConnected && (st ? st.textContent : t.getAttribute("title")) === text) {
      restore();
      el = t;
      strip();
      take();
      return;
    }
    leave();
    t = tipOf(e.target);                                 // the titles are back now: an outer element may have one
    if (!t) return;
    el = t;
    x = mx = e.clientX; y = my = e.clientY;
    strip();
    take();
    if (!timer) timer = setTimeout(show, SHOW_MS);
  }, true);
  document.addEventListener("mousemove", (e) => {
    mx = e.clientX; my = e.clientY;
    if (el && !el.isConnected && follow()) return;   // drawn again under the mouse: the new element keeps the tooltip
    if (!el) return;
    if (!el.contains(e.target)) { leave(); return; }
    if (box.hidden) { x = e.clientX; y = e.clientY; }   // shown: it stays where it opened, as the browser's
  }, true);
  document.addEventListener("mouseleave", leave);
  document.addEventListener("mousedown", () => { if (el) { box.hidden = true; clearTimeout(timer); timer = null; } }, true);
  window.addEventListener("blur", leave);
  // only a scroll that moves the element under the mouse closes it (a list next to it restoring its scroll, e.g. the
  // echoes of GRAVES redrawn every second, must not make the tooltip blink)
  document.addEventListener("scroll", (e) => {
    const s = e.target;
    if (!box.hidden && el && (s === document || s === document.documentElement || (s instanceof Node && s.contains(el)))) leave();
  }, true);
}());
