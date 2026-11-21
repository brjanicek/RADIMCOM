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
    `<button type="button" data-tb="mminfo" class="mm-info${vmInfoOn() ? " on" : ""}" title="The info of a point or area of the vector maps under the mouse (on / off)">Map info ${vmInfoOn() ? "ON" : "OFF"}</button>` +
    `<button type="button" data-tb="mmedit" class="mm-edit${vmEditOn() ? " on" : ""}" title="The right click card of a point or area of the vector maps: own name, note, hide (on / off)">Map edit ${vmEditOn() ? "ON" : "OFF"}</button>` +
    `<button type="button" data-tb="mmsave" title="Store the maps shown now (vector maps, base map, A/D map, ADS-B range) into a memory">Save actual</button>` +
    `<button type="button" data-tb="mmexp" title="Save chosen memories into a .json file">Export</button>` +
    `<button type="button" data-tb="mmimp" title="Load memories from a .json file (Export) into chosen memories">Import</button>`;
}

/** A key of the Maps bar pressed (from the click handler of the bars in app.js). */
function mapMemoClick(b) {
  if (b.dataset.tb === "mm") { mapMemoRecall(+b.dataset.mm); return; }
  if (b.dataset.tb === "mmsave") mapMemoDialog(b);
  else if (b.dataset.tb === "mmexp") mapMemoExport(b);
  else if (b.dataset.tb === "mminfo") { vmInfoSet(!vmInfoOn()); mapMemoRedraw(); }
  else if (b.dataset.tb === "mmedit") { vmEditSet(!vmEditOn()); mapMemoRedraw(); }
  else if (b.dataset.tb === "mmimp") mapMemoImportPick(b);
}

/** A small window over the map above the bars (one at a time; the same key again closes it). */
function mapMemoWin(btn, kind, html) {
  const wrap = btn.closest(".com-bars"), box = wrap && wrap.parentElement;
  if (!box) return null;
  const had = box.querySelector(":scope > .mm-dlg");
  if (had) { had.remove(); if (had.dataset.kind === kind) return null; }
  const dlg = document.createElement("div");
  dlg.className = "mm-dlg";
  dlg.dataset.kind = kind;
  dlg.innerHTML = html;
  box.appendChild(dlg);
  dlg.style.bottom = `${wrap.offsetHeight + 6}px`;
  L.DomEvent.disableClickPropagation(dlg);
  L.DomEvent.disableScrollPropagation(dlg);
  dlg.addEventListener("keydown", (e) => { if (e.key === "Escape") dlg.remove(); });
  return dlg;
}
const mapMemoRedraw = () => { if (typeof renderComTbar === "function" && comMap) { if (comMap._bars) comMap._bars._html = ""; renderComTbar(); } };

/** Export: the used memories with a checkbox each (all checked); Export saves them as mapmemo.json. */
function mapMemoExport(btn) {
  const list = mapMemos(), used = list.map((m, i) => [m, i]).filter(([m]) => m);
  const dlg = mapMemoWin(btn, "exp", `<div class="mm-dlg-h">Export <button type="button" class="mm-x" data-mmd="x" title="Close">✕</button></div>` +
    (used.length ? `<div class="mm-dlg-list">${used.map(([m, i]) => `<label><span><input type="checkbox" data-mmi="${i}" checked> ${i + 1}: ${escHtml(mapMemoName(m, i))}</span></label>`).join("")}</div>` +
      `<div class="mm-dlg-act"><button type="button" data-mmd="all">All / none</button><button type="button" data-mmd="ok">Export</button><button type="button" data-mmd="x">Cancel</button></div>`
      : `<p class="mm-dlg-note">No memory stored yet.</p>`));
  if (!dlg) return;
  dlg.addEventListener("click", (e) => {
    e.stopPropagation();
    const a = e.target.closest("button[data-mmd]");
    if (!a) return;
    const boxes = [...dlg.querySelectorAll("input[data-mmi]")];
    if (a.dataset.mmd === "x") dlg.remove();
    else if (a.dataset.mmd === "all") { const on = !boxes.every((x) => x.checked); boxes.forEach((x) => { x.checked = on; }); }
    else if (a.dataset.mmd === "ok") {
      const memos = boxes.filter((x) => x.checked).map((x) => ({ slot: +x.dataset.mmi + 1, ...list[+x.dataset.mmi] }));
      if (!memos.length) return;
      const blob = new Blob([JSON.stringify({ radimcom: "mapmemo", version: 1, exported: new Date().toISOString(), memos }, null, 1)], { type: "application/json" });
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url;
      link.download = `mapmemo_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      dlg.remove();
    }
  });
}

/** Import: a .json file of Export is chosen, then each of its memories gets a checkbox and the memory it goes into. */
function mapMemoImportPick(btn) {
  const inp = document.createElement("input");
  inp.type = "file";
  inp.accept = ".json,application/json";
  inp.addEventListener("change", () => {
    const f = inp.files && inp.files[0];
    if (!f) return;
    f.text().then((t) => {
      let d = null;
      try { d = JSON.parse(t); } catch { d = null; }
      const memos = d && Array.isArray(d.memos) ? d.memos.filter((m) => m && typeof m === "object" && m.o && typeof m.o === "object") : [];
      mapMemoImport(btn, memos, f.name);
    });
  });
  inp.click();
}
function mapMemoImport(btn, memos, fname) {
  const list = mapMemos();
  const target = (j) => `<select data-mmt="${j}">${list.map((m, i) => `<option value="${i}"${i === Math.min(MAP_MEMO_N, Math.max(1, +memos[j].slot || j + 1)) - 1 ? " selected" : ""}>` +
    `→ ${i + 1}: ${escHtml(m ? mapMemoName(m, i) : "(empty)")}</option>`).join("")}</select>`;
  const dlg = mapMemoWin(btn, "imp", `<div class="mm-dlg-h">Import <small>${escHtml(fname)}</small> <button type="button" class="mm-x" data-mmd="x" title="Close">✕</button></div>` +
    (memos.length ? `<div class="mm-dlg-list">${memos.map((m, j) => `<label><span><input type="checkbox" data-mmj="${j}" checked> ${escHtml(String(m.name || `MapMemo ${j + 1}`).slice(0, 30))}</span>${target(j)}</label>`).join("")}</div>` +
      `<div class="mm-dlg-ask" hidden></div>` +
      `<div class="mm-dlg-act"><button type="button" data-mmd="ok">Import</button><button type="button" data-mmd="x">Cancel</button></div>`
      : `<p class="mm-dlg-note">No map memory in this file.</p>`));
  if (!dlg) return;
  const ask = dlg.querySelector(".mm-dlg-ask"), act = dlg.querySelector(".mm-dlg-act");
  const chosen = () => [...dlg.querySelectorAll("input[data-mmj]")].filter((x) => x.checked).map((x) => [+x.dataset.mmj, +dlg.querySelector(`select[data-mmt="${x.dataset.mmj}"]`).value]);
  const write = () => {
    const cur = mapMemos();
    for (const [j, i] of chosen()) {
      const m = memos[j];
      cur[i] = { name: String(m.name || "").trim().slice(0, 30) || `MapMemo ${i + 1}`, at: +m.at || Date.now(),
        o: Object.fromEntries(Object.entries(m.o).filter(([k]) => MAP_MEMO_OPT.test(k))), vm: m.vm && typeof m.vm === "object" ? m.vm : null };
    }
    try { localStorage.setItem(MAP_MEMO_KEY, JSON.stringify(cur)); } catch { /* no storage */ }
    dlg.remove();
    mapMemoRedraw();
  };
  dlg.addEventListener("change", () => { if (ask) { ask.hidden = true; act.hidden = false; } });
  dlg.addEventListener("click", (e) => {
    e.stopPropagation();
    const a = e.target.closest("button[data-mmd]");
    if (!a) return;
    const k = a.dataset.mmd;
    if (k === "x") { dlg.remove(); return; }
    if (k === "no") { ask.hidden = true; act.hidden = false; return; }
    if (k === "yes") { write(); return; }
    if (k !== "ok") return;
    const c = chosen(), into = c.map(([, i]) => i);
    if (!c.length) return;
    if (new Set(into).size < into.length) { ask.innerHTML = "Two memories go into the same place: choose another."; ask.hidden = false; return; }
    const used = into.filter((i) => mapMemos()[i]);
    if (!used.length) { write(); return; }
    ask.innerHTML = `Overwrite ${used.map((i) => escHtml(mapMemoName(mapMemos()[i], i))).join(", ")}? <button type="button" data-mmd="yes">Overwrite</button><button type="button" data-mmd="no">No</button>`;
    ask.hidden = false;
    act.hidden = true;
  });
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
  if ((e.key === MAP_MEMO_KEY || e.key === "vmMapInfo" || e.key === "vmMapEdit") && typeof renderComTbar === "function" && typeof comMap !== "undefined" && comMap) renderComTbar();
});
