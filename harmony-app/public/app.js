// Usage Pulse — Harmony client shell.
// Fetches data.json from the GitHub Pages site that Pulse already publishes to, and
// paints the DOM. Polls every 5 min — matches the launchd push cadence. The shell
// itself is cached 1h by Harmony's CloudFront; the cache-buster query param on each
// fetch keeps the DATA fresh without redeploying the shell.
const DATA_URL = "https://mikezy.github.io/pulse/data.json";
const POLL_MS = 5 * 60 * 1000;

// Kept in sync with render.py::_FUN_FACTS so the desktop and Kindle views agree.
const FACTS = [
  "Slow is smooth, smooth is fast.",
  "What gets measured gets managed.",
  "Make the invisible visible.",
  "The cost of not doing the work shows up later.",
  "Small steps, every day.",
  "Kindle: the original e-ink dashboard.",
  "Ship beats perfect.",
  "Numbers don't lie. Dashboards sometimes do.",
];

const $ = (id) => document.getElementById(id);
const fmt = (n) => (n ?? 0).toLocaleString("en-US");

function paint(d) {
  const s = d.system || {}, c = d.claude || {};

  $("cpu").textContent  = s.cpu_pct ?? "—";
  $("ram").textContent  = `${s.ram_used_gb ?? "—"}/${s.ram_total_gb ?? "—"}`;
  $("disk").textContent = `${s.disk_used_gb ?? "—"}/${s.disk_total_gb ?? "—"}`;
  $("batt").innerHTML   = (s.battery_pct == null ? "—" : s.battery_pct + "%")
                          + (s.battery_ac ? '<span style="font-size:14px;"> AC</span>' : "");

  $("sessions").textContent   = fmt(c.sessions_all);
  $("messages").textContent   = fmt(c.messages_all);
  $("tokens").textContent     = c.tokens_compact ?? "—";
  $("activedays").textContent = `${c.active_days_all ?? 0}`;
  $("curstreak").textContent  = `${c.current_streak ?? 0}d`;
  $("longstreak").textContent = `${c.longest_streak ?? 0}d`;

  // Heatmap: 7 rows × 5 cols of bucket values 0..3 → <td class="h{v}">
  const heat = $("heat");
  heat.innerHTML = "";
  (c.heatmap_4w || []).forEach((row) => {
    const tr = document.createElement("tr");
    row.forEach((v) => {
      const td = document.createElement("td");
      td.className = "h" + v;
      tr.appendChild(td);
    });
    heat.appendChild(tr);
  });

  // Rotate fun-fact on the same 30s cadence as the Kindle render.
  $("fact").textContent = FACTS[Math.floor(Date.now() / 30000) % FACTS.length];
  const ts = d.generated_at_utc ? new Date(d.generated_at_utc) : new Date();
  $("stamp").textContent = ts.toLocaleString();
}

async function tick() {
  try {
    const r = await fetch(DATA_URL + "?t=" + Date.now(), { cache: "no-store" });
    if (r.ok) paint(await r.json());
  } catch (e) {
    /* keep last good paint on transient fetch/CORS errors */
  }
}

tick();
setInterval(tick, POLL_MS);
