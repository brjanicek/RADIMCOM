// ---------- IQ PLAYER (iqplay.py): an IQ file played through the active VFO instead of its dongle ----------
// Thanks to Dano OM1ATS for the idea.
// Loaded after app.js and uses its globals ($, st, active, vbase, setBodyTab, adError, escHtml, recsSize, recsSecs,
// fmtMHz, recall, store). app.js calls iqpStatus from its state, iqpOpen / iqpRowIcon from the RECORDINGS tab and uses
// IQP_ICON and iqpStatTitle in the VFO display (the only sign there: the virtual dongle, blue and blinking, instead of
// the USB / network icon). The receiver does the rest: the file is its "dongle".

// virtual dongle: "IQ" in the place of the USB / network icon (same height, so nothing moves)
var IQP_ICON = `<svg class="usb-icon iqp-icon" viewBox="0 0 690 440" aria-label="IQ file">` +
  `<text x="345" y="400" text-anchor="middle" textLength="640" lengthAdjust="spacingAndGlyphs" fill="currentColor" ` +
  `font-family="system-ui, sans-serif" font-weight="800" font-size="520">IQ</text></svg>`;
var IQP_FMT = { u8: "8 bit", s8: "8 bit signed", s16: "16 bit", f32: "float" };
var iqpSeeking = false;       // the position slider is being dragged: the state does not move it
var iqpFile = null;           // OPEN window: {rel | path} of the file being set up, and its probe

function iqpTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return recsSecs(s);
}

function iqpStatTitle(p) {
  return `IQ PLAYER: ${p.name}${p.paused ? " (paused)" : p.ended ? " (at the end)" : ""}\n` +
    `${iqpRate(p.fs_file)} ${IQP_FMT[p.fmt] || p.fmt}${p.fs !== p.fs_file ? ` → ${iqpRate(p.fs)}` : ""}, centre ${fmtMHz(p.centre, 6)} MHz\n` +
    "the VFO plays the file instead of its dongle: BACK TO VFO in the IQ PLAYER bar";
}

function iqpRate(fs) {
  return fs >= 1e6 ? `${+(fs / 1e6).toFixed(3)} MS/s` : `${+(fs / 1e3).toFixed(1)} kS/s`;
}

function iqpRowIcon(f) {
  const on = st && st.iq_play && st.iq_play.path && st.iq_play.path.replace(/\\/g, "/").endsWith("/" + f.path);
  return `<span class="iqp-row-ico${on ? " on" : ""}" title="Play through this VFO (IQ PLAYER)">${PP_ICO.play}</span>`;
}

// ----- SETTINGS › STATION: the virtual dongle in the lane of the VFO (instead of the dongle block, as a chained VFO) -----
function sdgIqAnt() {
  return sdgBlk("ANTENNA", `<span class="v">–</span><span>in the recording</span>`, "off k-ant",
    "IQ PLAYER: the samples come from a file recorded earlier, no antenna now");
}

function sdgIqFile(s) {
  const p = s.iq_play;
  const run = p.ended ? sdgChip("END", "warn") : p.paused ? sdgChip("PAUSED", "warn") : sdgChip("PLAYING", "iq blink");
  return sdgBlk("IQ FILE", `<span class="v sdg-iqf" title="${escHtml(p.path)}">${escHtml(p.name)}</span>` +
    `<span>${iqpRate(p.fs_file)} ${escHtml(IQP_FMT[p.fmt] || p.fmt)}${p.fs !== p.fs_file ? ` → ${iqpRate(p.fs)}` : ""}</span>` +
    `<span>centre ${sdgHz(p.centre)} · ${iqpTime(p.pos)} / ${iqpTime(p.secs)}</span>` +
    `<span class="chips">${sdgChip("VIRTUAL DONGLE", "on")}${run}${p.loop ? sdgChip("LOOP", "on") : ""}</span>`,
    `sdg-dev sdg-iqp k-dev ${p.error ? "lit bad" : "lit"}`, "IQ PLAYER: an IQ file is the dongle of this VFO; its blocks go in real time " +
    "with the centre and the sample rate of the file (faster files divided down, slower upsampled); DC, NB, the spectrum, the mixer and " +
    "everything after run as with a dongle. BACK TO VFO in the IQ PLAYER bar opens the dongle again");
}

/** The bar above the tabs: shown while the active VFO plays a file. */
function iqpStatus(s) {
  const p = s && s.iq_play;
  const bar = $("iqpBar");
  bar.hidden = !p;
  if (!p) return;
  $("iqpName").textContent = p.name;
  $("iqpName").title = p.path;
  $("iqpPlay").innerHTML = p.paused || p.ended ? `${PP_ICO.play}PLAY` : `${PP_ICO.pause}PAUSE`;
  $("iqpLoop").checked = !!p.loop;
  $("iqpLen").textContent = iqpTime(p.secs);
  const seek = $("iqpSeek");
  seek.max = String(Math.max(1, Math.round(p.secs * 10)));
  if (!iqpSeeking) {
    seek.value = String(Math.round(p.pos * 10));
    $("iqpTime").textContent = iqpTime(p.pos);
  }
  $("iqpInfo").textContent = `${fmtMHz(p.centre, 3)} MHz · ${iqpRate(p.fs_file)} ${IQP_FMT[p.fmt] || p.fmt}` +
    `${p.fs !== p.fs_file ? ` → ${iqpRate(p.fs)}` : ""} · tuned ${fmtMHz(s.tune_hz, 6)} MHz${p.ended ? " · END" : ""}`;
  $("iqpInfo").title = p.error || iqpStatTitle(p);
  $("iqpInfo").classList.toggle("error", !!p.error);
}

async function iqpPost(what, body) {
  const r = await fetch(`${vbase}/api/iqplay/${what}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

/** A file to play: {rel} from RECORDINGS or {path} from the disk. Known file = plays at once, otherwise the OPEN window asks. */
async function iqpOpen(file) {
  try {
    const info = await iqpPost("probe", file);
    if (info.ready) return iqpStart(file, {});
    iqpDlgOpen();
    iqpShowFile(file, info);
  } catch (e) {
    adError(`IQ PLAYER: ${e.message}`);
  }
}

async function iqpStart(file, extra) {
  try {
    await iqpPost("start", { ...file, ...extra, loop: recall("iqpLoop") === "1" });
    $("iqpDlg").hidden = true;
    setBodyTab("scope");       // the waterfall and the spectrum of the file
  } catch (e) {
    if (!$("iqpDlg").hidden) $("iqpDlgMsg").textContent = e.message;
    else adError(`IQ PLAYER: ${e.message}`);
  }
}

// ----- the bar -----
$("iqpPlay").addEventListener("click", () => {
  const p = st && st.iq_play;
  if (p) iqpPost("control", { pause: !(p.paused || p.ended) }).catch((e) => adError(`IQ PLAYER: ${e.message}`));
});
$("iqpSeek").addEventListener("input", () => { iqpSeeking = true; $("iqpTime").textContent = iqpTime($("iqpSeek").value / 10); });
$("iqpSeek").addEventListener("change", () => {
  iqpPost("control", { seek: $("iqpSeek").value / 10 }).catch((e) => adError(`IQ PLAYER: ${e.message}`))
    .finally(() => { iqpSeeking = false; });
});
$("iqpLoop").addEventListener("change", () => {
  store("iqpLoop", $("iqpLoop").checked ? "1" : "0");
  iqpPost("control", { loop: $("iqpLoop").checked }).catch((e) => adError(`IQ PLAYER: ${e.message}`));
});
$("iqpBack").addEventListener("click", () => iqpPost("stop").catch((e) => adError(`IQ PLAYER: ${e.message}`)));
$("iqpOpenKey").addEventListener("click", () => iqpDlgOpen());

// ----- OPEN window: folders and IQ files of the disk of the receiver's PC -----
function iqpDlgOpen() {
  $("iqpDlg").hidden = false;
  $("iqpDlgMsg").textContent = "";
  if (!$("iqpDlgList").dataset.dir) iqpBrowse(recall("iqpDir") || "");
}

async function iqpBrowse(dir) {
  try {
    const r = await fetch(`${vbase}/api/iqplay/browse?dir=${encodeURIComponent(dir)}`);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    const list = $("iqpDlgList");
    list.dataset.dir = j.dir;
    $("iqpDlgPath").value = j.dir;
    if (j.dir) store("iqpDir", j.dir);
    const rows = [];
    if (j.parent !== null) rows.push(`<li class="dir" data-dir="${escHtml(j.parent)}">↑ ..</li>`);
    for (const d of j.dirs) rows.push(`<li class="dir" data-dir="${escHtml(j.dir ? `${j.dir.replace(/[\\/]$/, "")}\\${d}` : d)}">${RECS_DIR_ICO}${escHtml(d)}</li>`);
    for (const f of j.files) rows.push(`<li class="file" data-path="${escHtml(`${j.dir.replace(/[\\/]$/, "")}\\${f.name}`)}"><span>${escHtml(f.name)}</span><span class="sz">${recsSize(f.size)}</span></li>`);
    list.innerHTML = rows.join("") || `<li class="none">No folders or IQ files here</li>`;
    $("iqpDlgMsg").textContent = "";
  } catch (e) {
    $("iqpDlgMsg").textContent = e.message;
  }
}

async function iqpPick(path) {
  try {
    iqpShowFile({ path }, await iqpPost("probe", { path }));
  } catch (e) {
    $("iqpDlgMsg").textContent = e.message;
  }
}

/** The file chosen: what was found out about it, the missing values to fill in. */
function iqpShowFile(file, info) {
  iqpFile = { file, info };
  $("iqpDlgFile").hidden = false;
  $("iqpDlgName").textContent = info.name;
  $("iqpDlgName").title = info.path;
  $("iqpDlgCentre").value = info.centre != null ? +(info.centre / 1e6).toFixed(6) : "";
  $("iqpDlgRate").value = info.fs != null ? +(info.fs / 1e3).toFixed(3) : "";
  const fmt = $("iqpDlgFmt");
  fmt.innerHTML = Object.entries(info.formats || {}).map(([k, n]) => `<option value="${k}">${escHtml(n)}</option>`).join("");
  fmt.value = info.fmt || "s8";
  fmt.disabled = !!info.wav;
  $("iqpDlgLen").textContent = `${recsSize(info.size)}${info.secs ? ` · ${iqpTime(info.secs)}` : ""}`;
  $("iqpDlgMsg").textContent = info.ready ? "" : "Fill in what the file does not say (centre, sample rate, format).";
}

$("iqpDlgList").addEventListener("click", (e) => {
  const li = e.target.closest("li");
  if (!li) return;
  if (li.dataset.dir !== undefined) iqpBrowse(li.dataset.dir);
  else if (li.dataset.path) iqpPick(li.dataset.path);
});
$("iqpDlgList").addEventListener("dblclick", (e) => {
  const li = e.target.closest("li.file");
  if (li && iqpFile && iqpFile.file.path === li.dataset.path) $("iqpDlgPlay").click();
});
$("iqpDlgPath").addEventListener("keydown", (e) => {
  if (e.key !== "Enter") return;
  const v = $("iqpDlgPath").value.trim().replace(/^"|"$/g, "");
  if (/\.[a-z0-9-]+$/i.test(v)) iqpPick(v); else iqpBrowse(v);
});
$("iqpDlgPlay").addEventListener("click", () => {
  if (!iqpFile) { $("iqpDlgMsg").textContent = "Choose a file first."; return; }
  const c = parseFloat($("iqpDlgCentre").value), r = parseFloat($("iqpDlgRate").value);
  if (!(c >= 0) || !(r > 0)) { $("iqpDlgMsg").textContent = "The centre frequency and the sample rate are needed."; return; }
  iqpStart(iqpFile.file, { centre: c * 1e6, fs: r * 1e3, fmt: $("iqpDlgFmt").value });
});
$("iqpDlgClose").addEventListener("click", () => { $("iqpDlg").hidden = true; });
$("iqpDlg").addEventListener("keydown", (e) => { if (e.key === "Escape") $("iqpDlg").hidden = true; });
