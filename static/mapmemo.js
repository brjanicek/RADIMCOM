// ===== Map memory: 10 stored map setups (vector maps, base map, A/D map, ADS-B range, station) =====
// The Maps bar under the COMPOSITE map (under Tracks and Tracker): one key per memory recalls it (grey = empty),
// "Save actual" stores the setup shown now into a memory chosen in a small window (asks before overwriting).
// Kept in this browser (like the map settings), the same in all its tabs and windows. Loaded before app.js;
// app.js registers the bar (COM_BARS) and calls mapMemoBarHtml() / mapMemoClick().

const MAP_MEMO_KEY = "mapMemos", MAP_MEMO_N = 10;
// the keys of the map settings a memory holds (the rest, e.g. the tracks, stays as it is)
const MAP_MEMO_OPT = /^(base|baseColor|baseUrl|dark|sea|stIcon|cSt|ad|adMax|adUnit|adFine|adOpa|adFineOpa|cAd|cAdFine|rng|[cofp]Rng\d+)$/;

/** The memories: an array of MAP_MEMO_N, each null (empty) or {name, at, o: {map settings}, vm: {vector maps}}. */
function mapMemos() {
  let v = null;
  try { v = JSON.parse(localStorage.getItem(MAP_MEMO_KEY) || "null"); } catch { v = null; }
  return Array.from({ length: MAP_MEMO_N }, (_, i) => (Array.isArray(v) && v[i] && typeof v[i] === "object" && v[i].o ? v[i] : null));
}
const mapMemoName = (m, i) => (m && m.name) || `MapMemo ${i + 1}`;

/** The setup shown now. */
function mapMemoTake() {
  const o = Object.fromEntries(Object.entries(mapOpts).filter(([k]) => MAP_MEMO_OPT.test(k)));
  const v = vmOpt(), vm = { on: !!v.on, ...Object.fromEntries(VM_VIEW_KEYS.map((k) => [k, v[k]])) };
  return { o, vm: JSON.parse(JSON.stringify(vm)) };
}

function mapMemoSave(i, name) {
  const list = mapMemos();
  list[i] = { name: String(name || "").trim().slice(0, 30) || `MapMemo ${i + 1}`, at: Date.now(), ...mapMemoTake() };
  try { localStorage.setItem(MAP_MEMO_KEY, JSON.stringify(list)); } catch { /* no storage */ }
}

/** Recalls memory i: the map settings in this browser, the vector maps view on the server (all windows follow). */
function mapMemoRecall(i) {
  const m = mapMemos()[i];
  if (!m) return;
  const o = Object.fromEntries(Object.entries(m.o || {}).filter(([k]) => MAP_MEMO_OPT.test(k)));
  if (Object.keys(o).length) mapOptsSet(o);
  if (m.vm) vmSet({ ...Object.fromEntries(VM_VIEW_KEYS.filter((k) => k in m.vm).map((k) => [k, m.vm[k]])), on: m.vm.on !== false });
  if (typeof vmRefillAll === "function") vmRefillAll();   // an open settings window shows it
}

/** The keys of the Maps bar. */
function mapMemoBarHtml() {
  return mapMemos().map((m, i) => `<button type="button" data-tb="mm" data-mm="${i}"${m ? "" : " disabled"} ` +
    `title="${m ? `Recall ${escHtml(mapMemoName(m, i))} (stored ${new Date(m.at || 0).toLocaleString()})` : "Empty: Save actual stores the maps shown now"}">${escHtml(mapMemoName(m, i))}</button>`).join("") +
    `<button type="button" data-tb="mmsave" class="mm-save" title="Store the maps shown now (vector maps, base map, A/D map, ADS-B range) into a memory">Save actual</button>`;
}

/** A key of the Maps bar pressed (from the click handler of the bars in app.js). */
function mapMemoClick(b) {
  if (b.dataset.tb === "mm") { mapMemoRecall(+b.dataset.mm); return; }
  if (b.dataset.tb === "mmsave") mapMemoDialog(b);
}

/** The small "Save actual" window: which memory, its name; an empty one is written at once, a used one asks first. */
function mapMemoDialog(btn) {
  const wrap = btn.closest(".com-bars"), box = wrap && wrap.parentElement;   // over the map (not in the bars: they are drawn again)
  if (!box) return;
  let dlg = box.querySelector(":scope > .mm-dlg");
  if (dlg) { dlg.remove(); return; }
  const list = mapMemos(), first = Math.max(0, list.findIndex((m) => !m));
  dlg = document.createElement("div");
  dlg.className = "mm-dlg";
  dlg.innerHTML = `<div class="mm-dlg-h">Save actual <button type="button" class="mm-x" data-mmd="x" title="Close">✕</button></div>` +
    `<label>Memory <select data-mmd="i">${list.map((m, i) => `<option value="${i}"${i === first ? " selected" : ""}>${i + 1}: ${escHtml(m ? mapMemoName(m, i) : "(empty)")}</option>`).join("")}</select></label>` +
    `<label>Name <input type="text" data-mmd="name" maxlength="30" value="${escHtml(mapMemoName(list[first], first))}"></label>` +
    `<div class="mm-dlg-ask" hidden></div>` +
    `<div class="mm-dlg-act"><button type="button" data-mmd="ok">OK</button><button type="button" data-mmd="x">Cancel</button></div>`;
  box.appendChild(dlg);
  dlg.style.bottom = `${wrap.offsetHeight + 6}px`;
  L.DomEvent.disableClickPropagation(dlg);
  L.DomEvent.disableScrollPropagation(dlg);
  const sel = dlg.querySelector('[data-mmd="i"]'), name = dlg.querySelector('[data-mmd="name"]'), ask = dlg.querySelector(".mm-dlg-ask");
  const act = dlg.querySelector(".mm-dlg-act");
  const done = () => { dlg.remove(); if (typeof renderComTbar === "function") { if (comMap && comMap._bars) comMap._bars._html = ""; renderComTbar(); } };
  sel.addEventListener("change", () => { const i = +sel.value; name.value = mapMemoName(mapMemos()[i], i); ask.hidden = true; act.hidden = false; });
  const ok = () => {
    const i = +sel.value, m = mapMemos()[i];
    if (!m) { mapMemoSave(i, name.value); done(); return; }
    ask.innerHTML = `Overwrite ${escHtml(mapMemoName(m, i))}? <button type="button" data-mmd="yes">Overwrite</button><button type="button" data-mmd="no">No</button>`;
    ask.hidden = false;
    act.hidden = true;
  };
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); ok(); } else if (e.key === "Escape") dlg.remove(); });
  dlg.addEventListener("click", (e) => {
    e.stopPropagation();
    const a = e.target.closest("[data-mmd]");
    if (!a || a.tagName !== "BUTTON") return;
    const k = a.dataset.mmd;
    if (k === "x") dlg.remove();
    else if (k === "ok") ok();
    else if (k === "yes") { mapMemoSave(+sel.value, name.value); done(); }
    else if (k === "no") { ask.hidden = true; act.hidden = false; }
  });
  name.focus();
  name.select();
}

// another tab or window stored a memory: its keys show it
window.addEventListener("storage", (e) => {
  if (e.key === MAP_MEMO_KEY && typeof renderComTbar === "function" && typeof comMap !== "undefined" && comMap) renderComTbar();
});
