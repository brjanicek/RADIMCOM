// ---------- Tooltips: one dark tooltip of our own for every title="" of the page ----------
// The browser's tooltip cannot be styled (white on most systems) and closes on the mouse wheel. Over an element with a
// title, the title is taken off it (so the browser shows nothing) and shown in #tipBox after a short delay; a title
// the code sets meanwhile (a new level, a new state) is taken over at once, so the tooltip stays up and current, also
// while the wheel turns. When the mouse leaves, the title is put back, so the code reading el.title sees it as before.
// Independent of app.js: it only needs the DOM.

(function () {
  const SHOW_MS = 450;          // about the delay of the browser's tooltip
  const box = document.createElement("div");
  box.id = "tipBox";
  box.className = "key-tip";
  box.hidden = true;
  box.setAttribute("role", "tooltip");
  document.body.appendChild(box);

  let el = null, text = "", timer = null, x = 0, y = 0;
  const watch = new MutationObserver(() => take());

  /** The title of the element under the mouse into the tooltip (and off the element). */
  function take() {
    if (!el) return;
    const t = el.getAttribute("title");
    if (t === null) return;
    watch.disconnect();
    if (t !== "") text = t;
    el.removeAttribute("title");
    watch.observe(el, { attributes: true, attributeFilter: ["title"] });
    if (!box.hidden) {
      if (!text) { box.hidden = true; return; }
      if (box.textContent !== text) { box.textContent = text; place(); }
    }
  }

  function place() {
    const w = box.offsetWidth, h = box.offsetHeight;
    let left = x + 12, top = y + 20;
    if (left + w > window.innerWidth - 4) left = Math.max(4, window.innerWidth - w - 4);
    if (top + h > window.innerHeight - 4) top = Math.max(4, y - h - 10);
    box.style.left = `${left}px`;
    box.style.top = `${top}px`;
  }

  function show() {
    timer = null;
    if (!el || !text || !el.isConnected) return;
    box.textContent = text;
    box.hidden = false;
    place();
  }

  function leave() {
    clearTimeout(timer);
    timer = null;
    watch.disconnect();
    if (el && el.getAttribute("title") === null && text) el.setAttribute("title", text);   // back, for the code
    el = null;
    text = "";
    box.hidden = true;
  }

  document.addEventListener("mouseover", (e) => {
    const t = e.target instanceof Element ? e.target.closest("[title]") : null;
    if (t === el) return;
    // still inside the element (its title is off it now, so closest() finds an outer one or none), unless an inner
    // element has a title of its own
    if (el && el.contains(e.target) && !(t && el.contains(t))) return;
    leave();
    if (!t) return;
    el = t;
    x = e.clientX; y = e.clientY;
    take();
    timer = setTimeout(show, SHOW_MS);
  }, true);
  document.addEventListener("mousemove", (e) => {
    if (!el) return;
    if (!el.contains(e.target)) { leave(); return; }
    if (box.hidden) { x = e.clientX; y = e.clientY; }   // shown: it stays where it opened, as the browser's
  }, true);
  document.addEventListener("mouseleave", leave);
  document.addEventListener("mousedown", () => { if (el) { box.hidden = true; clearTimeout(timer); timer = null; } }, true);
  window.addEventListener("blur", leave);
  document.addEventListener("scroll", () => { if (!box.hidden) leave(); }, true);
}());
