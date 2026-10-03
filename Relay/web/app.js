/* Relay — frontend (mapa Leaflet + panel fairness). Bez build-stepu. */

const CATEGORY_COLORS = {
  food: "#e67e22",
  water: "#3498db",
  meds: "#e74c3c",
  hygiene: "#9b59b6",
  other: "#7f8c8d",
};

const SEVERITY_COLORS = {
  1: "#2ecc71",
  2: "#a4d96c",
  3: "#f1c40f",
  4: "#e67e22",
  5: "#e74c3c",
};

const MODE_HINTS = {
  fair_share:
    "Maksymalizuje wklęsłą użyteczność — pomoc dociera też do dalekich, pilnych punktów.",
  nearest_fit:
    "Minimalizuje objazd — wszystko płynie do najbliższego punktu (baseline „Uber”).",
};

let map;
let layers;
let didFit = false;
let state = null;

function initMap() {
  map = L.map("map", { zoomControl: true }).setView([52.2297, 21.0117], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  layers = {
    trips: L.layerGroup().addTo(map),
    crates: L.layerGroup().addTo(map),
    needs: L.layerGroup().addTo(map),
    suggestions: L.layerGroup().addTo(map),
  };

  const legend = L.control({ position: "topright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "map-legend");
    div.innerHTML = `
      <div class="ml-title">Legenda mapy</div>
      <div class="ml-row"><span class="key line-gray"></span> przejazd O → D</div>
      <div class="ml-row"><span class="key dot-small"></span> skrzynka (kategoria)</div>
      <div class="ml-row"><span class="key dot-big"></span> punkt potrzeb (pilność)</div>
      <div class="ml-row"><span class="key line-orange"></span> sugerowany objazd</div>`;
    return div;
  };
  legend.addTo(map);
}

function allCoords(s) {
  const pts = [];
  (s.need_points || []).forEach((n) => pts.push([n.lat, n.lon]));
  (s.trips || []).forEach((t) => {
    pts.push([t.olat, t.olon]);
    pts.push([t.dlat, t.dlon]);
  });
  (s.crates || []).forEach((c) => pts.push([c.lat, c.lon]));
  return pts;
}

function drawTrips(trips) {
  layers.trips.clearLayers();
  trips.forEach((t) => {
    L.polyline(
      [
        [t.olat, t.olon],
        [t.dlat, t.dlon],
      ],
      { color: "#4a5b6e", weight: 2, dashArray: "2 5", opacity: 0.9 }
    )
      .bindPopup(
        `<b>Przejazd ${t.id}</b><br>budżet: ${t.detour_budget_min} min<br>` +
          `wolne sloty: ${t.slots_free} / status: ${t.status}`
      )
      .addTo(layers.trips);
  });
}

function drawCrates(crates) {
  layers.crates.clearLayers();
  crates.forEach((c) => {
    if (c.status !== "available") return;
    L.circleMarker([c.lat, c.lon], {
      radius: 4,
      color: CATEGORY_COLORS[c.category] || "#7f8c8d",
      fillColor: CATEGORY_COLORS[c.category] || "#7f8c8d",
      fillOpacity: 0.85,
      weight: 1,
    })
      .bindPopup(`<b>Skrzynka ${c.id}</b><br>kategoria: ${c.category}`)
      .addTo(layers.crates);
  });
}

function drawNeeds(needPoints, metrics) {
  layers.needs.clearLayers();
  const metricById = {};
  (metrics.points || []).forEach((p) => (metricById[p.need_id] = p));

  needPoints.forEach((n) => {
    const m = metricById[n.id] || {
      capacity: 1,
      unmet: 0,
      fill_pct: 100,
      projected_fill_pct: 100,
      projected_unmet: 0,
    };
    const unmetRatio = m.capacity > 0 ? m.projected_unmet / m.capacity : 0;
    const radius = 8 + 16 * unmetRatio;
    const color = SEVERITY_COLORS[n.severity] || "#7f8c8d";

    L.circleMarker([n.lat, n.lon], {
      radius,
      color,
      fillColor: color,
      fillOpacity: 0.5,
      weight: 2,
    })
      .bindPopup(
        `<b>${n.name || n.id}</b><br>` +
          `severity: ${n.severity}<br>` +
          `zapełnienie: ${m.fill_pct}% → ${m.projected_fill_pct}% (po sugestiach)<br>` +
          `braki: ${m.projected_unmet} / ${m.capacity}<br>` +
          `status: ${n.status}`
      )
      .addTo(layers.needs);
  });
}

function drawSuggestions(suggestions) {
  layers.suggestions.clearLayers();
  suggestions.forEach((s, idx) => {
    const route = s.route.map((p) => [p[0], p[1]]);
    L.polyline(route, {
      color: "#f0a53c",
      weight: 3,
      opacity: 0.95,
    })
      .bindPopup(
        `<b>Objazd ${idx + 1}</b><br>` +
          `+${s.extra_minutes} min → ${s.need.name}<br>` +
          `skrzynki: ${s.crate_ids.join(", ")}`
      )
      .addTo(layers.suggestions);

    L.marker(route[route.length - 2], {
      icon: L.divIcon({
        className: "sugg-pin",
        html: `<div style="background:#f0a53c;color:#06120c;border-radius:50%;width:20px;height:20px;` +
          `display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;` +
          `border:2px solid #06120c;">${idx + 1}</div>`,
        iconSize: [20, 20],
      }),
    }).addTo(layers.suggestions);
  });
}

function renderPanel() {
  const s = state;
  // Mode
  document.querySelectorAll("#mode-switch button").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === s.mode);
  });
  document.getElementById("mode-hint").textContent = MODE_HINTS[s.mode] || "";

  // Starvation
  document.getElementById("starvation-value").textContent =
    s.metrics.starvation_index + "%";
  document.getElementById("starvation-proj").textContent =
    s.metrics.projected_starvation_index + "%";

  // Points
  const pointsEl = document.getElementById("points");
  pointsEl.innerHTML = "";
  (s.metrics.points || [])
    .slice()
    .sort((a, b) => b.severity - a.severity)
    .forEach((p) => {
      const row = document.createElement("div");
      row.className = "point";
      row.innerHTML = `
        <span class="dot" style="background:${SEVERITY_COLORS[p.severity]}"></span>
        <span class="name">${p.name || p.need_id}<span class="sev">sev ${p.severity}</span></span>
        <span class="pct">${p.fill_pct}% → ${p.projected_fill_pct}%</span>
        <span class="bar">
          <span class="fill" style="width:${p.fill_pct}%"></span>
          <span class="proj" style="left:${p.fill_pct}%;width:${Math.max(
        0,
        p.projected_fill_pct - p.fill_pct
      )}%"></span>
        </span>`;
      pointsEl.appendChild(row);
    });

  // Suggestions
  const suggEl = document.getElementById("suggestions");
  document.getElementById("suggestions-count").textContent = s.suggestions.length;
  suggEl.innerHTML = "";
  if (!s.suggestions.length) {
    suggEl.innerHTML =
      '<p class="empty">Brak sugestii — brak dostępnych skrzynek, przejazdów lub otwartych punktów.</p>';
  }
  s.suggestions.forEach((sg, idx) => {
    const card = document.createElement("div");
    card.className = "suggestion";
    const chips = sg.crates
      .map(
        (c) =>
          `<span class="chip" style="border-color:${
            CATEGORY_COLORS[c.category]
          }">${c.id} · ${c.category}</span>`
      )
      .join("");
    card.innerHTML = `
      <div class="title">${idx + 1}. ${sg.need.name || sg.need_id}
        <span class="sev">(+${sg.extra_minutes} min)</span></div>
      <div class="meta">
        przejazd <b>${sg.trip_id}</b> · punkt <b>${sg.need_id}</b><br>
        zysk użyteczności: <b>${sg.utility_gain}</b>
      </div>
      <div class="crates">${chips}</div>
      <button class="claim" data-idx="${idx}">Przejmij</button>`;
    suggEl.appendChild(card);
  });

  suggEl.querySelectorAll("button.claim").forEach((btn) => {
    btn.addEventListener("click", () => claim(s.suggestions[parseInt(btn.dataset.idx, 10)]));
  });
}

function renderAll() {
  drawTrips(state.trips);
  drawCrates(state.crates);
  drawNeeds(state.need_points, state.metrics);
  drawSuggestions(state.suggestions);
  renderPanel();

  if (!didFit) {
    const pts = allCoords(state);
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.15));
    didFit = true;
  }
}

function toast(msg, isError = false) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}

async function loadState() {
  try {
    const res = await fetch("/state");
    if (!res.ok) throw new Error("HTTP " + res.status);
    state = await res.json();
    renderAll();
  } catch (err) {
    toast("Błąd ładowania stanu: " + err.message, true);
  }
}

async function claim(sg) {
  if (!sg) return;
  try {
    const res = await fetch("/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        trip_id: sg.trip_id,
        need_id: sg.need_id,
        crate_ids: sg.crate_ids,
      }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || "HTTP " + res.status);
    }
    toast("Przejęto objazd → " + (sg.need.name || sg.need_id));
    await loadState();
  } catch (err) {
    toast("Nie udało się przejąć: " + err.message, true);
    await loadState();
  }
}

async function setMode(mode) {
  try {
    const res = await fetch("/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    await loadState();
  } catch (err) {
    toast("Nie udało się zmienić trybu: " + err.message, true);
  }
}

async function reset() {
  try {
    const res = await fetch("/reset", { method: "POST" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    didFit = false;
    toast("Zresetowano do seeda");
    await loadState();
  } catch (err) {
    toast("Nie udało się zresetować: " + err.message, true);
  }
}

function renderLegend() {
  const el = document.getElementById("legend-cats");
  el.innerHTML =
    "Skrzynki: " +
    Object.entries(CATEGORY_COLORS)
      .map(
        ([cat, col]) =>
          `<span class="legend-cat"><i style="background:${col}"></i>${cat}</span>`
      )
      .join("");
}

const HELP_KEY = "relay-help-dismissed";

function openHelp() {
  const overlay = document.getElementById("help-overlay");
  overlay.hidden = false;
}

function closeHelp() {
  const overlay = document.getElementById("help-overlay");
  const remember = document.getElementById("help-hide");
  if (remember && remember.checked) {
    try {
      localStorage.setItem(HELP_KEY, "1");
    } catch (_) {
      /* localStorage może być wyłączony — ignorujemy */
    }
  }
  overlay.hidden = true;
}

function initHelp() {
  document.getElementById("help-btn").addEventListener("click", openHelp);
  document.getElementById("help-btn-2").addEventListener("click", openHelp);
  document.getElementById("help-close").addEventListener("click", closeHelp);
  document.getElementById("help-ok").addEventListener("click", closeHelp);
  document
    .getElementById("help-overlay")
    .addEventListener("click", (e) => {
      if (e.target.id === "help-overlay") closeHelp();
    });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeHelp();
  });

  let dismissed = false;
  try {
    dismissed = localStorage.getItem(HELP_KEY) === "1";
  } catch (_) {
    dismissed = false;
  }
  if (!dismissed) openHelp();
}

function main() {
  initMap();
  renderLegend();
  initHelp();
  document.querySelectorAll("#mode-switch button").forEach((b) => {
    b.addEventListener("click", () => setMode(b.dataset.mode));
  });
  document.getElementById("reset-btn").addEventListener("click", reset);
  loadState();
}

document.addEventListener("DOMContentLoaded", main);
