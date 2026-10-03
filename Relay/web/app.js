/* Relay — frontend (Leaflet map + fairness panel). No build step. */

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

const STATUS_COLORS = {
  claimed: "#3498db",
  picked_up: "#9b59b6",
  delivered: "#2ecc71",
};

const STATUS_LABELS = {
  available: "available",
  claimed: "claimed",
  picked_up: "picked up",
  delivered: "delivered",
  used: "used",
  suggested: "suggested",
  expired: "expired",
  open: "open",
  closed: "closed",
};

const MODE_HINTS = {
  fair_share:
    "Maximizes concave utility — aid also reaches far-away, urgent points.",
  nearest_fit:
    "Minimizes detour — everything flows to the nearest point (the \"Uber\" baseline).",
};

let map;
let layers;
let config = null;
let state = null;
let compare = null;
let didFit = false;
let clockOffset = 0;
let lastTtlReload = 0;

const filters = {
  trips: true,
  crates: true,
  needs: true,
  suggestions: true,
  detours: true,
  category: "all",
  needStatus: "all",
};

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

const serverNow = () => Date.now() / 1000 + clockOffset;

// ---------------------------------------------------------------------------
// Map
// ---------------------------------------------------------------------------

function initMap() {
  map = L.map("map", { zoomControl: true }).setView(
    [config?.center.lat ?? 52.2297, config?.center.lon ?? 21.0117],
    11
  );
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);

  layers = {
    trips: L.layerGroup().addTo(map),
    crates: L.layerGroup().addTo(map),
    needs: L.layerGroup().addTo(map),
    detours: L.layerGroup().addTo(map),
    suggestions: L.layerGroup().addTo(map),
  };

  const legend = L.control({ position: "topright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "map-legend");
    div.innerHTML = `
      <div class="ml-title">Map legend</div>
      <div class="ml-row"><span class="key line-gray"></span> trip O → D</div>
      <div class="ml-row"><span class="key dot-small"></span> crate (category)</div>
      <div class="ml-row"><span class="key dot-big"></span> need-point (urgency)</div>
      <div class="ml-row"><span class="key line-orange"></span> suggested detour</div>
      <div class="ml-row"><span class="key line-teal"></span> active detour</div>`;
    return div;
  };
  legend.addTo(map);

  const filterCtl = L.control({ position: "topleft" });
  filterCtl.onAdd = () => {
    const div = L.DomUtil.create("div", "map-filters");
    div.innerHTML = `
      <div class="mf-title">Layers</div>
      <label><input type="checkbox" data-flag="trips" checked> Trips</label>
      <label><input type="checkbox" data-flag="crates" checked> Crates</label>
      <label><input type="checkbox" data-flag="needs" checked> Need-points</label>
      <label><input type="checkbox" data-flag="suggestions" checked> Suggestions</label>
      <label><input type="checkbox" data-flag="detours" checked> Active detours</label>
      <div class="mf-title">Crate category</div>
      <select data-filter="category">
        <option value="all">all</option>
        ${(config?.categories ?? [])
          .map((c) => `<option value="${c}">${c}</option>`)
          .join("")}
      </select>
      <div class="mf-title">Need-point status</div>
      <select data-filter="needStatus">
        <option value="all">all</option>
        <option value="open">open</option>
        <option value="closed">closed</option>
      </select>`;
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);
    div.querySelectorAll("input[data-flag]").forEach((el) => {
      el.addEventListener("change", () => {
        filters[el.dataset.flag] = el.checked;
        renderAll();
      });
    });
    div.querySelectorAll("select[data-filter]").forEach((el) => {
      el.addEventListener("change", () => {
        filters[el.dataset.filter] = el.value;
        renderAll();
      });
    });
    return div;
  };
  filterCtl.addTo(map);
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

function routeOf(route) {
  return route.map((p) => [p[0], p[1]]);
}

function drawTrips(trips) {
  layers.trips.clearLayers();
  if (!filters.trips) return;
  trips.forEach((t) => {
    L.polyline(
      [
        [t.olat, t.olon],
        [t.dlat, t.dlon],
      ],
      { color: "#4a5b6e", weight: 2, dashArray: "2 5", opacity: 0.9 }
    )
      .bindPopup(
        `<b>Trip ${esc(t.id)}</b><br>budget: ${t.detour_budget_min} min<br>` +
          `free slots: ${t.slots_free} / status: ${STATUS_LABELS[t.status] || t.status}`
      )
      .addTo(layers.trips);
  });
}

function drawCrates(crates) {
  layers.crates.clearLayers();
  if (!filters.crates) return;
  crates.forEach((c) => {
    if (filters.category !== "all" && c.category !== filters.category) return;
    const color = CATEGORY_COLORS[c.category] || "#7f8c8d";
    const done = c.status !== "available";
    L.circleMarker([c.lat, c.lon], {
      radius: done ? 3 : 4,
      color,
      fillColor: color,
      fillOpacity: done ? 0.25 : 0.85,
      weight: 1,
      dashArray: done ? "2 2" : null,
    })
      .bindPopup(
        `<b>Crate ${esc(c.id)}</b><br>category: ${c.category}<br>` +
          `status: ${STATUS_LABELS[c.status] || c.status}`
      )
      .addTo(layers.crates);
  });
}

function drawNeeds(needPoints, metrics) {
  layers.needs.clearLayers();
  if (!filters.needs) return;
  const metricById = {};
  (metrics.points || []).forEach((p) => (metricById[p.need_id] = p));

  needPoints.forEach((n) => {
    if (filters.needStatus !== "all" && n.status !== filters.needStatus) return;
    const m = metricById[n.id] || {
      capacity: 1,
      unmet: 0,
      fill_pct: 100,
      projected_fill_pct: 100,
      projected_unmet: 0,
      delivered_physical: 0,
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
        `<b>${esc(n.name || n.id)}</b><br>` +
          `severity: ${n.severity}<br>` +
          `fill: ${m.fill_pct}% → ${m.projected_fill_pct}% (after suggestions)<br>` +
          `unmet: ${m.projected_unmet} / ${m.capacity}<br>` +
          `physically delivered: ${m.delivered_physical || 0}<br>` +
          `status: ${STATUS_LABELS[n.status] || n.status}`
      )
      .addTo(layers.needs);
  });
}

function drawSuggestions(suggestions) {
  layers.suggestions.clearLayers();
  if (!filters.suggestions) return;
  suggestions.forEach((s, idx) => {
    const route = routeOf(s.route);
    L.polyline(route, {
      color: "#f0a53c",
      weight: 3,
      opacity: 0.95,
      dashArray: "6 6",
    })
      .bindPopup(
        `<b>Suggested detour ${idx + 1}</b><br>` +
          `+${s.extra_minutes} min → ${esc(s.need.name)}<br>` +
          `crates: ${s.crate_ids.join(", ")}`
      )
      .addTo(layers.suggestions);

    L.marker(route[route.length - 2], {
      icon: L.divIcon({
        className: "sugg-pin",
        html:
          `<div style="background:#f0a53c;color:#06120c;border-radius:50%;width:20px;height:20px;` +
          `display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;` +
          `border:2px solid #06120c;">${idx + 1}</div>`,
        iconSize: [20, 20],
      }),
    }).addTo(layers.suggestions);
  });
}

function drawDetours(detours) {
  layers.detours.clearLayers();
  if (!filters.detours) return;
  detours
    .filter((d) => d.status !== "suggested")
    .forEach((d) => {
      const trip = (state.trips || []).find((t) => t.id === d.trip_id);
      const need = (state.need_points || []).find((n) => n.id === d.need_id);
      if (!trip || !need) return;
      const route = [
        [trip.olat, trip.olon],
        ...d.crates.map((c) => [c.lat, c.lon]),
        [need.lat, need.lon],
        [trip.dlat, trip.dlon],
      ];
      const color = STATUS_COLORS[d.status] || "#7f8c8d";
      L.polyline(route, { color, weight: 4, opacity: 0.95 })
        .bindPopup(
          `<b>Detour ${esc(d.id)}</b><br>` +
            `status: ${STATUS_LABELS[d.status] || d.status}<br>` +
            `${d.crate_ids.length} crates → ${esc(need.name || need.id)}`
        )
        .addTo(layers.detours);
    });
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

function renderPanel() {
  const s = state;
  document.querySelectorAll("#mode-switch button").forEach((b) => {
    b.classList.toggle("active", b.dataset.mode === s.mode);
  });
  document.getElementById("mode-hint").textContent = MODE_HINTS[s.mode] || "";

  document.getElementById("starvation-value").textContent =
    s.metrics.starvation_index + "%";
  document.getElementById("starvation-proj").textContent =
    s.metrics.projected_starvation_index + "%";

  document.getElementById("counters").innerHTML =
    `<span class="counter">in transit <b>${s.physical.in_transit}</b></span>` +
    `<span class="counter">delivered <b>${s.physical.delivered}</b></span>` +
    `<span class="counter">active detours <b>${activeDetours().length}</b></span>`;

  renderPoints();
  renderSuggestions();
  renderDetours();
}

function renderPoints() {
  const pointsEl = document.getElementById("points");
  pointsEl.innerHTML = "";
  (state.metrics.points || [])
    .slice()
    .sort((a, b) => b.severity - a.severity)
    .forEach((p) => {
      const row = document.createElement("div");
      row.className = "point";
      row.innerHTML = `
        <span class="dot" style="background:${SEVERITY_COLORS[p.severity]}"></span>
        <span class="name">${esc(p.name || p.need_id)}<span class="sev">sev ${p.severity}</span></span>
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
}

function renderSuggestions() {
  const suggEl = document.getElementById("suggestions");
  document.getElementById("suggestions-count").textContent = state.suggestions.length;
  suggEl.innerHTML = "";
  if (!state.suggestions.length) {
    suggEl.innerHTML =
      '<p class="empty">No suggestions — no available crates, trips, or open need-points.</p>';
    return;
  }
  state.suggestions.forEach((sg, idx) => {
    const card = document.createElement("div");
    card.className = "suggestion";
    const chips = sg.crates
      .map(
        (c) =>
          `<span class="chip" style="border-color:${CATEGORY_COLORS[c.category]}">` +
          `${esc(c.id)} · ${c.category}</span>`
      )
      .join("");
    const ttl = sg.expires_at
      ? `<div class="ttl" data-expires="${sg.expires_at}">valid for …</div>`
      : "";
    card.innerHTML = `
      <div class="title">${idx + 1}. ${esc(sg.need.name || sg.need_id)}
        <span class="sev">(+${sg.extra_minutes} min)</span></div>
      <div class="meta">
        trip <b>${esc(sg.trip_id)}</b> · need-point <b>${esc(sg.need_id)}</b><br>
        utility gain: <b>${sg.utility_gain}</b>
      </div>
      <div class="crates">${chips}</div>
      ${ttl}
      <button class="claim" data-idx="${idx}">Claim</button>`;
    suggEl.appendChild(card);
  });
  suggEl.querySelectorAll("button.claim").forEach((btn) => {
    btn.addEventListener("click", () =>
      claim(state.suggestions[parseInt(btn.dataset.idx, 10)])
    );
  });
  updateTtlLabels();
}

function activeDetours() {
  return (state.detours || []).filter((d) => d.status !== "suggested");
}

function renderDetours() {
  const dets = activeDetours();
  const el = document.getElementById("detours");
  document.getElementById("detours-count").textContent = dets.length;
  el.innerHTML = "";
  if (!dets.length) {
    el.innerHTML = '<p class="empty">No active detours yet — claim a suggestion.</p>';
    return;
  }
  dets.forEach((d) => {
    const need = (state.need_points || []).find((n) => n.id === d.need_id);
    const card = document.createElement("div");
    card.className = "detour";
    const chips = (d.crates || [])
      .map(
        (c) =>
          `<span class="chip" style="border-color:${CATEGORY_COLORS[c.category]}">` +
          `${esc(c.crate_id ?? c.id)}</span>`
      )
      .join("");
    let actions = "";
    if (d.status === "claimed") {
      actions += `<button class="checkpoint" data-id="${esc(d.id)}" data-action="pickup">Picked up</button>`;
    }
    if (d.status === "claimed" || d.status === "picked_up") {
      actions += `<button class="checkpoint deliver" data-id="${esc(d.id)}" data-action="deliver">Delivered</button>`;
    }
    card.innerHTML = `
      <div class="title">${esc(need?.name || d.need_id)}
        <span class="status-badge s-${d.status}">${STATUS_LABELS[d.status] || d.status}</span></div>
      <div class="meta">${d.crate_ids.length} crates · trip ${esc(d.trip_id)}</div>
      <div class="crates">${chips}</div>
      <div class="actions">${actions}</div>`;
    el.appendChild(card);
  });
  el.querySelectorAll("button.checkpoint").forEach((btn) => {
    btn.addEventListener("click", () =>
      checkpoint(btn.dataset.id, btn.dataset.action)
    );
  });
}

function updateTtlLabels() {
  const now = serverNow();
  document.querySelectorAll("[data-expires]").forEach((el) => {
    const expires = parseFloat(el.dataset.expires);
    const left = Math.round(expires - now);
    if (left <= 0) {
      el.textContent = "expired";
      el.classList.add("expired");
    } else {
      el.textContent = `valid for ${left}s`;
      el.classList.remove("expired");
    }
  });
}

// ---------------------------------------------------------------------------
// Manage tab
// ---------------------------------------------------------------------------

function renderManage() {
  const q = (document.getElementById("manage-search")?.value || "").toLowerCase();
  const match = (id, extra) =>
    !q ||
    String(id).toLowerCase().includes(q) ||
    String(extra ?? "").toLowerCase().includes(q);

  const needs = (state.need_points || []).filter((n) => match(n.id, n.name));
  const trips = (state.trips || []).filter((t) => match(t.id));
  const crates = (state.crates || []).filter((c) => match(c.id, c.category));

  document.getElementById("manage-needs-count").textContent = needs.length;
  document.getElementById("manage-trips-count").textContent = trips.length;
  document.getElementById("manage-crates-count").textContent = crates.length;

  document.getElementById("manage-needs").innerHTML = needs
    .map(
      (n) => `
      <div class="manage-row">
        <div><b>${esc(n.name || n.id)}</b><span class="muted"> sev ${n.severity} · ${STATUS_LABELS[n.status] || n.status}</span>
          <div class="muted small">${Object.entries(n.requirements)
            .map(([c, r]) => `${c} ${r.delivered}/${r.needed}`)
            .join(" · ") || "no demand"}</div></div>
        <div class="manage-actions">
          <button class="mini" data-edit="need" data-id="${esc(n.id)}">Edit</button>
          <button class="mini danger" data-delete="need" data-id="${esc(n.id)}">Delete</button>
        </div>
      </div>`
    )
    .join("") || '<p class="empty">No need-points.</p>';

  document.getElementById("manage-trips").innerHTML = trips
    .map(
      (t) => `
      <div class="manage-row">
        <div><b>${esc(t.id)}</b><span class="muted"> ${t.detour_budget_min} min · ${t.slots_free} slots · ${STATUS_LABELS[t.status] || t.status}</span>
          <div class="muted small">${t.olat.toFixed(4)}, ${t.olon.toFixed(4)} → ${t.dlat.toFixed(4)}, ${t.dlon.toFixed(4)}</div></div>
        <div class="manage-actions">
          <button class="mini" data-edit="trip" data-id="${esc(t.id)}">Edit</button>
          <button class="mini danger" data-delete="trip" data-id="${esc(t.id)}">Delete</button>
        </div>
      </div>`
    )
    .join("") || '<p class="empty">No trips.</p>';

  document.getElementById("manage-crates").innerHTML = crates
    .map(
      (c) => `
      <div class="manage-row">
        <div><b>${esc(c.id)}</b><span class="muted"> ${c.category} · ${STATUS_LABELS[c.status] || c.status}</span>
          <div class="muted small">${c.lat.toFixed(4)}, ${c.lon.toFixed(4)}</div></div>
        <div class="manage-actions">
          <button class="mini" data-edit="crate" data-id="${esc(c.id)}">Edit</button>
          <button class="mini danger" data-delete="crate" data-id="${esc(c.id)}">Delete</button>
        </div>
      </div>`
    )
    .join("") || '<p class="empty">No crates.</p>';

  document.querySelectorAll("#tab-manage [data-edit]").forEach((b) =>
    b.addEventListener("click", () => openEdit(b.dataset.edit, b.dataset.id))
  );
  document.querySelectorAll("#tab-manage [data-delete]").forEach((b) =>
    b.addEventListener("click", () => removeResource(b.dataset.delete, b.dataset.id))
  );
}

// ---------------------------------------------------------------------------
// Edit modal
// ---------------------------------------------------------------------------

let editTarget = null;

function field(label, name, value, opts = "") {
  return `<label>${label} <input name="${name}" type="number" step="any" value="${value}" ${opts}></label>`;
}

function openEdit(kind, id) {
  editTarget = { kind, id };
  const form = document.getElementById("edit-form");
  let html = "";

  if (kind === "crate") {
    const c = state.crates.find((x) => x.id === id);
    html =
      `<label>Category <select name="category" class="cat-select"></select></label>` +
      `<div class="row">${field("Latitude", "lat", c.lat)}${field("Longitude", "lon", c.lon)}</div>`;
    form.innerHTML = html;
    selectCategory(form.querySelector("select"), c.category);
  } else if (kind === "trip") {
    const t = state.trips.find((x) => x.id === id);
    form.innerHTML =
      `<div class="row">${field("From lat", "olat", t.olat)}${field("From lon", "olon", t.olon)}</div>` +
      `<div class="row">${field("To lat", "dlat", t.dlat)}${field("To lon", "dlon", t.dlon)}</div>` +
      `<div class="row">${field("Budget (min)", "detour_budget_min", t.detour_budget_min, 'min="0.1"')}` +
      `${field("Free slots", "slots_free", t.slots_free, 'min="1" step="1"')}</div>`;
  } else {
    const n = state.need_points.find((x) => x.id === id);
    const reqs = Object.entries(n.requirements)
      .map(
        ([c, r]) =>
          `<label>${c} <input name="req-${c}" type="number" min="0" step="1" value="${r.needed}"></label>`
      )
      .join("");
    form.innerHTML =
      `<div class="row">
        <label>Name <input name="name" type="text" value="${esc(n.name || "")}"></label>
        <label>Urgency <select name="severity">
          ${[1, 2, 3, 4, 5]
            .map((s) => `<option value="${s}" ${s === n.severity ? "selected" : ""}>${s}</option>`)
            .join("")}
        </select></label>
      </div>
      <div class="row">${field("Latitude", "lat", n.lat)}${field("Longitude", "lon", n.lon)}</div>
      <label>Status <select name="status">
        <option value="open" ${n.status === "open" ? "selected" : ""}>open</option>
        <option value="closed" ${n.status === "closed" ? "selected" : ""}>closed</option>
      </select></label>
      <p class="form-label">Demand per category</p>
      <div class="req-grid">${reqs}</div>`;
  }

  document.getElementById("edit-title").textContent = `Edit ${kind}`;
  document.getElementById("edit-overlay").hidden = false;
}

function selectCategory(select, value) {
  select.innerHTML = (config?.categories ?? [])
    .map((c) => `<option value="${c}" ${c === value ? "selected" : ""}>${c}</option>`)
    .join("");
}

function closeEdit() {
  document.getElementById("edit-overlay").hidden = true;
  editTarget = null;
}

async function saveEdit() {
  if (!editTarget) return;
  const { kind, id } = editTarget;
  const form = document.getElementById("edit-form");
  const data = new FormData(form);
  let url, body;

  if (kind === "crate") {
    body = {
      category: data.get("category"),
      lat: parseFloat(data.get("lat")),
      lon: parseFloat(data.get("lon")),
    };
    url = `/crates/${encodeURIComponent(id)}`;
  } else if (kind === "trip") {
    body = {
      olat: parseFloat(data.get("olat")),
      olon: parseFloat(data.get("olon")),
      dlat: parseFloat(data.get("dlat")),
      dlon: parseFloat(data.get("dlon")),
      detour_budget_min: parseFloat(data.get("detour_budget_min")),
      slots_free: parseInt(data.get("slots_free"), 10),
    };
    url = `/trips/${encodeURIComponent(id)}`;
  } else {
    const requirements = {};
    for (const [key, value] of data.entries()) {
      if (key.startsWith("req-")) {
        requirements[key.slice(4)] = parseInt(value, 10) || 0;
      }
    }
    body = {
      name: data.get("name"),
      lat: parseFloat(data.get("lat")),
      lon: parseFloat(data.get("lon")),
      severity: parseInt(data.get("severity"), 10),
      status: data.get("status"),
      requirements,
    };
    url = `/need-points/${encodeURIComponent(id)}`;
  }

  try {
    const res = await fetch(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "HTTP " + res.status);
    }
    closeEdit();
    toast("Saved " + kind);
    await loadState();
  } catch (err) {
    toast("Save failed: " + err.message, true);
  }
}

async function removeResource(kind, id) {
  if (!window.confirm(`Delete ${kind} ${id}?`)) return;
  const url = {
    crate: `/crates/${encodeURIComponent(id)}`,
    trip: `/trips/${encodeURIComponent(id)}`,
    need: `/need-points/${encodeURIComponent(id)}`,
  }[kind];
  try {
    const res = await fetch(url, { method: "DELETE" });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "HTTP " + res.status);
    }
    toast(`Deleted ${kind} ${id}`);
    await loadState();
  } catch (err) {
    toast("Delete failed: " + err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

async function loadState() {
  try {
    const res = await fetch("/state");
    if (!res.ok) throw new Error("HTTP " + res.status);
    state = await res.json();
    clockOffset = state.server_time - Date.now() / 1000;
    renderAll();
  } catch (err) {
    toast("Failed to load state: " + err.message, true);
  }
}

async function claim(sg) {
  if (!sg) return;
  const body = sg.detour_id
    ? { detour_id: sg.detour_id }
    : { trip_id: sg.trip_id, need_id: sg.need_id, crate_ids: sg.crate_ids };
  try {
    const res = await fetch("/claim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "HTTP " + res.status);
    }
    toast("Claimed detour → " + (sg.need.name || sg.need_id));
    await loadState();
  } catch (err) {
    toast("Claim failed: " + err.message, true);
    await loadState();
  }
}

async function checkpoint(detourId, action) {
  const suffix = action === "pickup" ? "pickup" : "deliver";
  try {
    const res = await fetch(
      `/detours/${encodeURIComponent(detourId)}/${suffix}`,
      { method: "POST" }
    );
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "HTTP " + res.status);
    }
    toast(action === "pickup" ? "Marked as picked up" : "Marked as delivered");
    await loadState();
  } catch (err) {
    toast("Checkpoint failed: " + err.message, true);
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
    toast("Could not switch mode: " + err.message, true);
  }
}

async function reset() {
  try {
    const res = await fetch("/reset", { method: "POST" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    didFit = false;
    toast("Reset to seed");
    await loadState();
  } catch (err) {
    toast("Reset failed: " + err.message, true);
  }
}

// ---------------------------------------------------------------------------
// Compare
// ---------------------------------------------------------------------------

async function runCompare() {
  try {
    const [fairRes, nearestRes] = await Promise.all([
      fetch("/state?mode=fair_share"),
      fetch("/state?mode=nearest_fit"),
    ]);
    if (!fairRes.ok || !nearestRes.ok) throw new Error("HTTP error");
    compare = { fair: await fairRes.json(), nearest: await nearestRes.json() };
    renderCompare();
  } catch (err) {
    toast("Comparison failed: " + err.message, true);
  }
}

function renderCompare() {
  if (!compare) return;
  const { fair, nearest } = compare;
  const nearestById = {};
  nearest.metrics.points.forEach((p) => (nearestById[p.need_id] = p));

  let starved = 0;
  const rows = fair.metrics.points
    .slice()
    .sort((a, b) => b.severity - a.severity)
    .map((p) => {
      const n = nearestById[p.need_id] || { projected_fill_pct: 0 };
      const delta = p.projected_fill_pct - n.projected_fill_pct;
      if (delta > 0) starved++;
      const cls = delta > 0 ? "diff-pos" : "";
      return `<tr class="${cls}">
        <td>${esc(p.name || p.need_id)}</td>
        <td>${p.severity}</td>
        <td>${p.projected_fill_pct}%</td>
        <td>${n.projected_fill_pct}%</td>
        <td>${delta > 0 ? "+" : ""}${delta}%</td>
      </tr>`;
    })
    .join("");

  document.getElementById("compare-summary").innerHTML = `
    <div class="cmp-grid">
      <div><span class="cmp-label">Fair-share</span>
        <b>${fair.metrics.projected_starvation_index}%</b></div>
      <div><span class="cmp-label">Nearest-fit</span>
        <b>${nearest.metrics.projected_starvation_index}%</b></div>
      <div><span class="cmp-label">Points helped more</span>
        <b>${starved}</b></div>
    </div>
    <p class="section-help">Fair-share reaches <b>${starved}</b> point(s) that Nearest-fit
      leaves behind. Rows highlighted in green are the fairness win.</p>`;
  document.getElementById("compare-body").innerHTML = rows;
  document.getElementById("compare-table").hidden = false;
}

// ---------------------------------------------------------------------------
// Tabs / forms / help
// ---------------------------------------------------------------------------

function initTabs() {
  document.querySelectorAll("#tabs button").forEach((b) => {
    b.addEventListener("click", () => {
      const tab = b.dataset.tab;
      document.querySelectorAll("#tabs button").forEach((x) =>
        x.classList.toggle("active", x === b)
      );
      document.querySelectorAll(".tab").forEach((s) => {
        s.hidden = s.id !== `tab-${tab}`;
      });
      if (tab === "manage") renderManage();
      if (tab === "compare" && !compare) runCompare();
    });
  });
}

function numberVal(data, name) {
  return parseFloat(data.get(name));
}

async function submitJson(url, body, okMsg) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.detail || "HTTP " + res.status);
    }
    const out = await res.json();
    toast(`${okMsg} ${out.id}`);
    await loadState();
    return true;
  } catch (err) {
    toast("Failed: " + err.message, true);
    return false;
  }
}

function initForms() {
  // Category selects and the need demand grid.
  const cats = config?.categories ?? [];
  document
    .querySelectorAll(
      "#tab-add .cat-select, #edit-form .cat-select"
    )
    .forEach((sel) => selectCategory(sel, cats[0]));
  const grid = document.getElementById("need-reqs");
  if (grid) {
    grid.innerHTML = cats
      .map(
        (c) =>
          `<label>${c} <input name="req-${c}" type="number" min="0" step="1" value="0"></label>`
      )
      .join("");
  }

  document.getElementById("form-crate").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(e.target);
    await submitJson(
      "/crates",
      {
        category: data.get("category"),
        lat: numberVal(data, "lat"),
        lon: numberVal(data, "lon"),
      },
      "Added crate"
    );
  });

  document.getElementById("form-trip").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(e.target);
    await submitJson(
      "/trips",
      {
        olat: numberVal(data, "olat"),
        olon: numberVal(data, "olon"),
        dlat: numberVal(data, "dlat"),
        dlon: numberVal(data, "dlon"),
        detour_budget_min: numberVal(data, "detour_budget_min"),
        slots_free: parseInt(data.get("slots_free"), 10),
      },
      "Added trip"
    );
  });

  document.getElementById("form-need").addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = new FormData(e.target);
    const requirements = {};
    for (const [key, value] of data.entries()) {
      if (key.startsWith("req-")) {
        const qty = parseInt(value, 10) || 0;
        if (qty > 0) requirements[key.slice(4)] = qty;
      }
    }
    await submitJson(
      "/need-points",
      {
        name: data.get("name"),
        lat: numberVal(data, "lat"),
        lon: numberVal(data, "lon"),
        severity: parseInt(data.get("severity"), 10),
        requirements,
      },
      "Added need-point"
    );
  });
}

function initManage() {
  const search = document.getElementById("manage-search");
  if (search) search.addEventListener("input", renderManage);
  document.getElementById("edit-close").addEventListener("click", closeEdit);
  document.getElementById("edit-save").addEventListener("click", saveEdit);
  document.getElementById("edit-overlay").addEventListener("click", (e) => {
    if (e.target.id === "edit-overlay") closeEdit();
  });
}

function initCompare() {
  document
    .getElementById("compare-refresh")
    .addEventListener("click", runCompare);
}

function renderLegend() {
  const el = document.getElementById("legend-cats");
  el.innerHTML =
    "Crates: " +
    Object.entries(CATEGORY_COLORS)
      .map(
        ([cat, col]) =>
          `<span class="legend-cat"><i style="background:${col}"></i>${cat}</span>`
      )
      .join("") +
    "<div class='legend-note'>Urgency: " +
    [1, 2, 3, 4, 5]
      .map(
        (s) =>
          `<span class="legend-cat"><i style="background:${SEVERITY_COLORS[s]};border-radius:50%"></i>sev ${s}</span>`
      )
      .join("") +
    "</div>";
}

function renderAll() {
  drawTrips(state.trips);
  drawCrates(state.crates);
  drawNeeds(state.need_points, state.metrics);
  drawSuggestions(state.suggestions);
  drawDetours(state.detours);
  renderPanel();
  if (!document.getElementById("tab-manage").hidden) renderManage();

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

// --- Help ---

const HELP_KEY = "relay-help-dismissed";

function openHelp() {
  document.getElementById("help-overlay").hidden = false;
}

function closeHelp() {
  const remember = document.getElementById("help-hide");
  if (remember && remember.checked) {
    try {
      localStorage.setItem(HELP_KEY, "1");
    } catch (_) {
      /* localStorage may be disabled — ignore */
    }
  }
  document.getElementById("help-overlay").hidden = true;
}

function initHelp() {
  document.getElementById("help-btn").addEventListener("click", openHelp);
  document.getElementById("help-btn-2").addEventListener("click", openHelp);
  document.getElementById("help-close").addEventListener("click", closeHelp);
  document.getElementById("help-ok").addEventListener("click", closeHelp);
  document.getElementById("help-overlay").addEventListener("click", (e) => {
    if (e.target.id === "help-overlay") closeHelp();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeHelp();
      closeEdit();
    }
  });

  let dismissed = false;
  try {
    dismissed = localStorage.getItem(HELP_KEY) === "1";
  } catch (_) {
    dismissed = false;
  }
  if (!dismissed) openHelp();
}

function startTtlTicker() {
  setInterval(() => {
    updateTtlLabels();
    const now = serverNow();
    const anyExpired = (state?.suggestions || []).some(
      (s) => s.expires_at && s.expires_at <= now
    );
    if (anyExpired && Date.now() - lastTtlReload > 1500) {
      lastTtlReload = Date.now();
      loadState();
    }
  }, 1000);
}

async function boot() {
  try {
    config = await (await fetch("/config")).json();
  } catch (_) {
    config = { categories: [], modes: [], center: { lat: 52.2297, lon: 21.0117 } };
  }
  initMap();
  renderLegend();
  initHelp();
  initTabs();
  initForms();
  initManage();
  initCompare();
  document.querySelectorAll("#mode-switch button").forEach((b) => {
    b.addEventListener("click", () => setMode(b.dataset.mode));
  });
  document.getElementById("reset-btn").addEventListener("click", reset);
  startTtlTicker();
  await loadState();
}

document.addEventListener("DOMContentLoaded", boot);
