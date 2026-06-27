const DEFAULT_COLUMNS = [
  "name","website","on_platform","matched","email","emails_all",
  "phone","phones_all","ids","address","country","socials",
  "platform","source_query","status","notes",
];

let RECIPES = [];
let GROUPED = {};
let currentJob = null;

const $ = (id) => document.getElementById(id);

async function loadRecipes() {
  const res = await fetch("/api/recipes");
  const data = await res.json();
  RECIPES = data.recipes;
  GROUPED = data.grouped;
  const cat = $("category");
  cat.innerHTML = "";
  Object.keys(GROUPED).forEach((c) => {
    const o = document.createElement("option");
    o.value = c; o.textContent = c; cat.appendChild(o);
  });
  populateTypes();
}

function populateTypes() {
  const cat = $("category").value;
  const type = $("type");
  type.innerHTML = "";
  (GROUPED[cat] || []).forEach((r) => {
    const o = document.createElement("option");
    o.value = r.id; o.textContent = r.type; type.appendChild(o);
  });
  showFingerprints();
}

function selectedRecipe() {
  const id = $("type").value;
  return RECIPES.find((r) => r.id === id);
}

function showFingerprints() {
  const r = selectedRecipe();
  $("fingerprints").textContent = r
    ? "Matches if page contains: " + r.verify_fingerprints.join(", ")
    : "";
}

function buildColumns() {
  const box = $("columns");
  box.innerHTML = "";
  DEFAULT_COLUMNS.forEach((c) => {
    const id = "col_" + c;
    const label = document.createElement("label");
    label.className = "flex items-center gap-1";
    label.innerHTML = `<input type="checkbox" id="${id}" checked /> ${c}`;
    box.appendChild(label);
  });
}

function selectedColumns() {
  return DEFAULT_COLUMNS.filter((c) => $("col_" + c)?.checked);
}

function chip(confirmed) {
  const yes = confirmed === "Y" || confirmed === true;
  const cls = yes ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500";
  return `<span class="px-2 py-0.5 rounded-full ${cls}">${yes ? "Y" : "N"}</span>`;
}

function addRow(lead) {
  const tr = document.createElement("tr");
  tr.className = "border-t";
  tr.innerHTML =
    `<td class="p-2">${chip(lead.on_platform)}</td>` +
    `<td class="p-2">${lead.name || ""}</td>` +
    `<td class="p-2"><a class="text-emerald-600 underline" href="${lead.website}" target="_blank">${lead.website}</a></td>` +
    `<td class="p-2">${lead.email || ""}</td>` +
    `<td class="p-2">${lead.phone || ""}</td>`;
  $("rows").appendChild(tr);
}

function logLine(msg) {
  const el = $("log");
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}

async function runJob() {
  $("rows").innerHTML = "";
  $("log").textContent = "";
  $("bar").style.width = "0%";
  $("dlXlsx").disabled = true;
  $("dlCsv").disabled = true;

  const manualHosts = ($("manualHosts").value || "")
    .split(/[\n,]/).map((s) => s.trim()).filter(Boolean);
  const body = {
    recipe_id: $("type").value,
    source: $("source").value,
    keyword: $("keyword").value,
    country: $("country").value,
    limit: parseInt($("limit").value, 10),
    delay: parseFloat($("delay").value),
    concurrency: parseInt($("concurrency").value, 10),
    only_confirmed: $("onlyConfirmed").checked,
    manual_hosts: manualHosts,
    columns: selectedColumns(),
  };
  const res = await fetch("/api/jobs", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const { job_id } = await res.json();
  currentJob = job_id;

  let lastQuery = "";
  let rawCandidates = null;
  const es = new EventSource(`/api/jobs/${job_id}/stream`);
  es.addEventListener("progress", (e) => {
    const d = JSON.parse(e.data);
    if (d.query !== undefined) lastQuery = d.query;
    if (d.raw_candidates !== undefined) rawCandidates = d.raw_candidates;
    const pct = d.total ? Math.round((d.checked / d.total) * 100) : 0;
    $("bar").style.width = pct + "%";
    $("summary").textContent = `${d.checked}/${d.total} checked · ${d.confirmed} confirmed`;
    if (d.log) logLine(d.log);
  });
  es.addEventListener("lead", (e) => addRow(JSON.parse(e.data).lead));
  es.addEventListener("done", (e) => {
    const d = JSON.parse(e.data);
    const raw = d.raw_candidates ?? rawCandidates ?? d.total;
    const q = d.query || lastQuery;
    let msg;
    if (raw === 0) {
      msg = `0 candidates found for query: ${q}. Try a different source, keyword, or manual domains.`;
    } else if (d.confirmed === 0) {
      msg = `${raw} candidate(s) found, ${d.checked} checked, 0 confirmed on platform (query: ${q}).`;
    } else {
      msg = `Done — ${raw} candidate(s), ${d.checked} checked, ${d.confirmed} confirmed (query: ${q}).`;
    }
    $("summary").textContent = msg;
    $("dlXlsx").disabled = false;
    $("dlCsv").disabled = false;
    es.close();
  });
  es.addEventListener("error", () => { logLine("[stream closed]"); es.close(); });
}

async function customRecipe() {
  const type = prompt("Type name (e.g. Calendly):");
  if (!type) return;
  const fp = prompt("Verify fingerprint (e.g. assets.calendly.com):");
  if (!fp) return;
  const urlscan = prompt("urlscan query:", `domain:${fp}`) || `domain:${fp}`;
  const body = { category: "Custom", type, urlscan_query: urlscan,
                 verify_fingerprints: [fp] };
  const test = await fetch("/api/recipes/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, source: "urlscan" }),
  }).then((r) => r.json());
  if (!confirm(`Test: ${test.matched}/${test.checked} candidates matched. Save recipe?`))
    return;
  await fetch("/api/recipes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  await loadRecipes();
}

function wire() {
  $("category").addEventListener("change", populateTypes);
  $("type").addEventListener("change", showFingerprints);
  $("limit").addEventListener("input", () => $("limitVal").textContent = $("limit").value);
  $("runBtn").addEventListener("click", runJob);
  $("customBtn").addEventListener("click", customRecipe);
  $("dlXlsx").addEventListener("click", () => currentJob && (window.location = `/api/jobs/${currentJob}/results.xlsx`));
  $("dlCsv").addEventListener("click", () => currentJob && (window.location = `/api/jobs/${currentJob}/results.csv`));
}

buildColumns();
wire();
loadRecipes();
