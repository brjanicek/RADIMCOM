// ---------- DECODERS › GRAVES › REC (meteor_rec.py): the echoes into the recordings folder (RECORDINGS tab) ----------
// Loaded after app.js and uses its globals ($, mtVfo, mtDet, adError). app.js calls mtRecLoad from mtLoad.
// The REC key is twice (SETTINGS › RECORDINGS and the head of ECHOES), both the same setting.

var mtRec = null;            // the state of the active VFO: {on, kinds, iq, band, saved, last, error, retro}
var mtRecAt = 0, mtRecBase = "";

async function mtRecLoad(v, force) {
  if (!v || (!force && v.base === mtRecBase && Date.now() - mtRecAt < 5000)) return;
  mtRecAt = Date.now();
  mtRecBase = v.base;
  try {
    const j = await fetch(v.base + "/api/meteors/rec").then((r) => r.json());
    if (v === mtVfo()) { mtRec = j; mtRecRender(); }
  } catch { /* server unreachable */ }
}

function mtRecRender() {
  const r = mtRec;
  if (!r || !document.getElementById("mtRecB")) return;
  for (const x of document.querySelectorAll(".mt-rec")) x.checked = !!r.on;
  for (const x of document.querySelectorAll(".mt-reck")) x.classList.toggle("rec-on", !!r.on);
  for (const x of document.querySelectorAll(".mt-reck-kind")) x.checked = (r.kinds || []).includes(x.dataset.kind);
  $("mtRecIq").checked = !!r.iq;
  $("mtRecBand").checked = !!r.band;
  const what = ["MP3", r.iq ? "IQ ECHO" : "", r.band ? "IQ BAND" : ""].filter(Boolean).join(" + ");
  $("mtRecV").textContent = r.on ? `REC ${what}` : "off";
  $("mtRecB").classList.toggle("lit", !!r.on);
  $("mtRecB").classList.toggle("bad", !!r.error);
  $("mtRecSub").textContent = r.error ? r.error
    : r.on ? `${r.saved} echo${r.saved === 1 ? "" : "es"} saved since the start${r.last ? ` · last ${r.last}` : ""}` +
      (r.band && !r.retro ? " · PRE-REC is off: no IQ BAND" : "")
    : "RECORDINGS tab › the day folder, source GRAVES; SAVE in the detail of an echo saves that one";
}

async function mtRecSet(body) {
  const v = mtVfo();          // the VFO the GRAVES page shows (where GRAVES runs)
  if (!v) return;
  try {
    const r = await fetch(v.base + "/api/meteors/rec", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    mtRec = await r.json();
  } catch (e) { adError(`GRAVES REC: ${e.message}`); }
  mtRecRender();
}

for (const x of document.querySelectorAll(".mt-rec")) x.addEventListener("change", () => mtRecSet({ on: x.checked }));
for (const x of document.querySelectorAll(".mt-reck-kind")) {
  x.addEventListener("change", () => mtRecSet({ kinds: [...document.querySelectorAll(".mt-reck-kind")].filter((k) => k.checked).map((k) => k.dataset.kind) }));
}
$("mtRecIq").addEventListener("change", () => mtRecSet({ iq: $("mtRecIq").checked }));
$("mtRecBand").addEventListener("change", () => mtRecSet({ band: $("mtRecBand").checked }));

// SAVE in the detail of an echo: that one into the recordings now
$("mtDetSave").addEventListener("click", async () => {
  if (!mtDet) return;
  const b = $("mtDetSave");
  b.disabled = true;
  try {
    const r = await fetch(mtDet.base + "/api/meteors/rec/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ts: mtDet.ts }) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    b.textContent = "SAVED ✓";
    b.title = `Saved into the recordings folder:\n${j.files.join("\n")}`;
    setTimeout(() => { b.textContent = "SAVE"; }, 2500);
  } catch (e) {
    adError(`GRAVES SAVE: ${e.message}`);
  } finally {
    b.disabled = false;
  }
});
