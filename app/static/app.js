const DEFAULT_COLUMNS = [
  "name","website","on_platform","matched","email","emails_all",
  "phone","phones_all","ids","address","country","socials",
  "platform","source_query","status","notes",
];

let RECIPES = [];
let GROUPED = {};
let currentJob = null;

const $ = (id) => document.getElementById(id);

// Region presets: filter the Type list to a market's popular platforms + auto-fill
// Country. UI-only convenience — does NOT geo-filter the scraped leads. ids=null => all.
const REGION_PRESETS = {
  Global: { country: "", ids: null },
  US: { country: "US", ids: ["shopify","woocommerce","bigcommerce","toast","chownow","slice","square","authorizenet","affirm","sezzle","stripe_checkout","paypal_buttons","hubspot","intercom","drift","calendly","acuity","housecallpro","mindbody","mailchimp","klaviyo","gtm","hotjar","squarespace","wix","webflow","godaddy","trustpilot","typeform"] },
  UK: { country: "GB", ids: ["shopify","woocommerce","bigcommerce","flipdish","gloriafood","gocardless","worldpay","clearpay","stripe_checkout","paypal_buttons","calendly","acuity","simplybook","trustpilot","intercom","tawkto","mailchimp","klaviyo","wix","squarespace","godaddy","typeform"] },
  EU: { country: "", ids: ["shopify","woocommerce","prestashop","gloriafood","flipdish","mollie","adyen","klarna","stripe_checkout","gocardless","calendly","calcom","typeform","mailchimp","klaviyo","wix","squarespace","jimdo","trustpilot"] },
  CA: { country: "CA", ids: ["shopify","woocommerce","bigcommerce","square","stripe_checkout","paypal_buttons","calendly","acuity","mailchimp","klaviyo","wix","squarespace","hubspot","intercom"] },
  AU: { country: "AU", ids: ["shopify","woocommerce","square","clearpay","stripe_checkout","paypal_buttons","calendly","acuity","mailchimp","wix","squarespace","hubspot","typeform"] },
};

function presetSet() {
  const p = REGION_PRESETS[$("region").value];
  return p && p.ids ? new Set(p.ids) : null;  // null => no filtering
}

async function loadRecipes() {
  const res = await fetch("/api/recipes");
  const data = await res.json();
  RECIPES = data.recipes;
  GROUPED = data.grouped;
  populateCategories();
}

function populateCategories() {
  const set = presetSet();
  const cat = $("category");
  const prev = cat.value;
  cat.innerHTML = "";
  Object.keys(GROUPED).forEach((c) => {
    const types = GROUPED[c].filter((r) => !set || set.has(r.id));
    if (types.length === 0) return;  // hide categories with no preset types
    const o = document.createElement("option");
    o.value = c; o.textContent = c; cat.appendChild(o);
  });
  if (prev && [...cat.options].some((o) => o.value === prev)) cat.value = prev;
  populateTypes();
}

function populateTypes() {
  const set = presetSet();
  const cat = $("category").value;
  const type = $("type");
  type.innerHTML = "";
  (GROUPED[cat] || [])
    .filter((r) => !set || set.has(r.id))
    .forEach((r) => {
      const o = document.createElement("option");
      o.value = r.id; o.textContent = r.type; type.appendChild(o);
    });
  showFingerprints();
}

function onRegionChange() {
  const region = $("region").value;
  const p = REGION_PRESETS[region];
  $("country").value = p.country || "";
  $("regionNote").classList.toggle("hidden", region === "Global");
  populateCategories();
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

  // Confirmed cell — chip() returns a fixed string based on a boolean; safe.
  const tdConfirmed = document.createElement("td");
  tdConfirmed.className = "p-2";
  tdConfirmed.innerHTML = chip(lead.on_platform);
  tr.appendChild(tdConfirmed);

  // Name cell
  const tdName = document.createElement("td");
  tdName.className = "p-2";
  tdName.textContent = lead.name || "";
  tr.appendChild(tdName);

  // Website cell — only allow http/https hrefs to prevent javascript: injection
  const tdWebsite = document.createElement("td");
  tdWebsite.className = "p-2";
  const a = document.createElement("a");
  a.className = "text-emerald-600 underline";
  a.textContent = lead.website || "";
  a.rel = "noopener noreferrer";
  a.target = "_blank";
  const ws = lead.website || "";
  if (ws.startsWith("http://") || ws.startsWith("https://")) {
    a.href = ws;
  }
  tdWebsite.appendChild(a);
  tr.appendChild(tdWebsite);

  // Email cell
  const tdEmail = document.createElement("td");
  tdEmail.className = "p-2";
  tdEmail.textContent = lead.email || "";
  tr.appendChild(tdEmail);

  // Phone cell
  const tdPhone = document.createElement("td");
  tdPhone.className = "p-2";
  tdPhone.textContent = lead.phone || "";
  tr.appendChild(tdPhone);

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

// Admin-gated fetch: recipe management (create/test) may require admin Basic-auth
// when ADMIN_PASSWORD is configured server-side. On 401, prompt once and retry.
let ADMIN_AUTH = null;
async function adminFetch(url, opts) {
  const withAuth = () => ({
    ...opts,
    headers: { ...(opts.headers || {}), ...(ADMIN_AUTH ? { Authorization: ADMIN_AUTH } : {}) },
  });
  let res = await fetch(url, withAuth());
  if (res.status === 401) {
    const u = prompt("Admin username:", "admin");
    if (u === null) return res;
    const p = prompt("Admin password:");
    if (p === null) return res;
    ADMIN_AUTH = "Basic " + btoa(u + ":" + p);
    res = await fetch(url, withAuth());
    if (res.status === 401) { alert("Admin login failed."); ADMIN_AUTH = null; }
  }
  return res;
}

async function customRecipe() {
  const type = prompt("Type name (e.g. Calendly):");
  if (!type) return;
  const fp = prompt("Verify fingerprint (e.g. assets.calendly.com):");
  if (!fp) return;
  const urlscan = prompt("urlscan query:", `domain:${fp}`) || `domain:${fp}`;
  const body = { category: "Custom", type, urlscan_query: urlscan,
                 verify_fingerprints: [fp] };
  const testRes = await adminFetch("/api/recipes/test", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, source: "urlscan" }),
  });
  if (!testRes.ok) return;  // 401 cancelled or failed
  const test = await testRes.json();
  if (!confirm(`Test: ${test.matched}/${test.checked} candidates matched. Save recipe?`))
    return;
  const createRes = await adminFetch("/api/recipes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!createRes.ok) return;
  await loadRecipes();
}

// ---- Jobs / History view ----
function showView(name) {
  $("view-search").classList.toggle("hidden", name !== "search");
  $("view-jobs").classList.toggle("hidden", name !== "jobs");
  const active = "block px-3 py-2 rounded-lg bg-emerald-50 text-emerald-700 font-medium";
  const idle = "block px-3 py-2 rounded-lg text-slate-500";
  $("nav-search").className = name === "search" ? active : idle;
  $("nav-jobs").className = name === "jobs" ? active : idle;
  if (name === "jobs") loadJobs();
}

function jobStatusChip(status) {
  const map = {
    done: "bg-emerald-100 text-emerald-700",
    running: "bg-amber-100 text-amber-700",
    pending: "bg-slate-100 text-slate-500",
    error: "bg-red-100 text-red-700",
  };
  const span = document.createElement("span");
  span.className = `px-2 py-0.5 rounded-full text-xs ${map[status] || "bg-slate-100 text-slate-500"}`;
  span.textContent = status || "—";
  return span;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function dlLink(label, href) {
  const a = document.createElement("a");
  a.className = "text-emerald-600 underline mr-3";
  a.textContent = label;
  a.href = href;
  return a;
}

async function loadJobs() {
  const tbody = $("jobsRows");
  tbody.innerHTML = "";
  let jobs = [];
  try {
    jobs = (await fetch("/api/jobs").then((r) => r.json())).jobs || [];
  } catch (e) { /* leave empty */ }
  $("jobsEmpty").classList.toggle("hidden", jobs.length > 0);
  jobs.forEach((j) => {
    const tr = document.createElement("tr");
    tr.className = "border-t";
    const td = (child) => {
      const c = document.createElement("td");
      c.className = "p-3";
      if (child instanceof Node) c.appendChild(child);
      else c.textContent = child == null ? "" : String(child);
      return c;
    };
    tr.appendChild(td(fmtDate(j.created_at)));
    tr.appendChild(td(j.type));
    tr.appendChild(td(j.source));
    tr.appendChild(td(jobStatusChip(j.status)));
    tr.appendChild(td(j.lead_count == null ? "" : j.lead_count));
    const dl = document.createElement("td");
    dl.className = "p-3 whitespace-nowrap";
    const id = encodeURIComponent(j.id);
    dl.appendChild(dlLink(".xlsx", `/api/jobs/${id}/results.xlsx`));
    dl.appendChild(dlLink(".csv", `/api/jobs/${id}/results.csv`));
    tr.appendChild(dl);
    tbody.appendChild(tr);
  });
}

function wire() {
  $("nav-search").addEventListener("click", (e) => { e.preventDefault(); showView("search"); });
  $("nav-jobs").addEventListener("click", (e) => { e.preventDefault(); showView("jobs"); });
  $("jobsRefresh").addEventListener("click", loadJobs);
  $("region").addEventListener("change", onRegionChange);
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
