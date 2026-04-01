function fmtNum(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  return new Intl.NumberFormat().format(value);
}

function fmtShortJson(obj) {
  try {
    return JSON.stringify(obj);
  } catch {
    return String(obj);
  }
}

function fmtTime(value) {
  const date = value instanceof Date ? value : new Date(value || Date.now());
  return new Intl.DateTimeFormat([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).format(date);
}

function appendLog(el, line, maxLines = 160) {
  const current = el.textContent ? el.textContent.split("\n") : [];
  current.push(line);
  if (current.length > maxLines) {
    current.splice(0, current.length - maxLines);
  }
  el.textContent = current.join("\n");
  el.scrollTop = el.scrollHeight;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function setControlStatus(state, detail) {
  const statusEl = document.getElementById("control-status");
  const detailEl = document.getElementById("control-status-detail");
  statusEl.className = `status-indicator ${state}`;
  statusEl.textContent = state;
  detailEl.textContent = `${detail} at ${fmtTime()}`;
}

function setStreamStatus(elementId, state, detail) {
  const el = document.getElementById(elementId);
  if (!el) {
    return;
  }
  el.className = `status-indicator ${state}`;
  el.textContent = detail;
}

function showToast(kind, title, message, ttlMs = 4200) {
  const tray = document.getElementById("toast-tray");
  const toast = document.createElement("div");
  toast.className = `toast ${kind}`;
  toast.innerHTML = `<strong>${escapeHtml(title)}</strong><p>${escapeHtml(message)}</p>`;
  tray.appendChild(toast);
  window.setTimeout(() => {
    toast.remove();
  }, ttlMs);
}

function setButtonBusy(button, busy, busyLabel) {
  if (!button.dataset.defaultLabel) {
    button.dataset.defaultLabel = button.textContent;
  }
  button.disabled = busy;
  button.classList.toggle("is-loading", busy);
  button.textContent = busy ? busyLabel : button.dataset.defaultLabel;
}

async function withButtonBusy(button, busyLabel, work) {
  setButtonBusy(button, true, busyLabel);
  try {
    return await work();
  } finally {
    setButtonBusy(button, false, busyLabel);
  }
}

async function parseError(resp) {
  const text = await resp.text();
  try {
    const data = JSON.parse(text);
    return data.error || text || `HTTP ${resp.status}`;
  } catch {
    return text || `HTTP ${resp.status}`;
  }
}

async function requestJson(url, options = {}) {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    throw new Error(await parseError(resp));
  }
  return resp.status === 204 ? null : resp.json();
}

const shipsQuery = {
  offset: 0,
  limit: 20,
  faction: ""
};

const stationsQuery = {
  offset: 0,
  limit: 20,
  body_type: ""
};

const departuresByMinute = new Map();
const pirateStrengthHistory = [];
const operatorActionHistory = [];

const PIRATE_PRESETS = {
  calm: {
    pirate_spawn_probability_per_day: 0.35,
    pirate_strength_decay_per_day: 0.05,
    pirate_strength_end_threshold: 0.45,
    pirate_strength_start: 0.8,
    pirate_respawn_min_days: 0.8,
    pirate_respawn_max_days: 2.0
  },
  balanced: {
    pirate_spawn_probability_per_day: 0.65,
    pirate_strength_decay_per_day: 0.04,
    pirate_strength_end_threshold: 0.35,
    pirate_strength_start: 1.0,
    pirate_respawn_min_days: 0.4,
    pirate_respawn_max_days: 1.2
  },
  aggressive: {
    pirate_spawn_probability_per_day: 0.85,
    pirate_strength_decay_per_day: 0.03,
    pirate_strength_end_threshold: 0.25,
    pirate_strength_start: 1.2,
    pirate_respawn_min_days: 0.2,
    pirate_respawn_max_days: 0.8
  },
  chaos: {
    pirate_spawn_probability_per_day: 1.0,
    pirate_strength_decay_per_day: 0.02,
    pirate_strength_end_threshold: 0.15,
    pirate_strength_start: 1.4,
    pirate_respawn_min_days: 0.1,
    pirate_respawn_max_days: 0.4
  }
};

function getPirateInputValues() {
  return {
    pirate_spawn_probability_per_day: Number(document.getElementById("pirate-spawn-prob").value || "1.0"),
    pirate_strength_decay_per_day: Number(document.getElementById("pirate-decay").value || "0.03"),
    pirate_strength_end_threshold: Number(document.getElementById("pirate-end-threshold").value || "0.3"),
    pirate_strength_start: Number(document.getElementById("pirate-strength-start").value || "1.0"),
    pirate_respawn_min_days: Number(document.getElementById("pirate-respawn-min").value || "0.2"),
    pirate_respawn_max_days: Number(document.getElementById("pirate-respawn-max").value || "1.0")
  };
}

function setPirateInputValues(values) {
  document.getElementById("pirate-spawn-prob").value = values.pirate_spawn_probability_per_day;
  document.getElementById("pirate-decay").value = values.pirate_strength_decay_per_day;
  document.getElementById("pirate-end-threshold").value = values.pirate_strength_end_threshold;
  document.getElementById("pirate-strength-start").value = values.pirate_strength_start;
  document.getElementById("pirate-respawn-min").value = values.pirate_respawn_min_days;
  document.getElementById("pirate-respawn-max").value = values.pirate_respawn_max_days;
}

function recordOperatorAction(title, detail, status = "success") {
  const timestamp = new Date();
  operatorActionHistory.unshift({ title, detail, status, timestamp });
  if (operatorActionHistory.length > 8) {
    operatorActionHistory.splice(8);
  }

  const lastActionEl = document.getElementById("operator-last-action");
  const historyEl = document.getElementById("operator-action-history");
  if (!lastActionEl || !historyEl) {
    return;
  }

  lastActionEl.textContent = `${title} at ${fmtTime(timestamp)}`;
  historyEl.innerHTML = operatorActionHistory
    .map(
      (entry) => `
        <li>
          <strong>${escapeHtml(entry.title)}</strong>
          <span class="${escapeHtml(entry.status)}">${escapeHtml(entry.detail)}</span>
          <span>${escapeHtml(fmtTime(entry.timestamp))}</span>
        </li>
      `
    )
    .join("");
}

function nowMinuteKey(date = new Date()) {
  const d = new Date(date);
  d.setSeconds(0, 0);
  return d.toISOString();
}

function incrementDepartureMinute(isoTimestamp) {
  const key = nowMinuteKey(isoTimestamp ? new Date(isoTimestamp) : new Date());
  departuresByMinute.set(key, (departuresByMinute.get(key) || 0) + 1);

  const cutoff = Date.now() - 30 * 60 * 1000;
  for (const k of departuresByMinute.keys()) {
    if (new Date(k).getTime() < cutoff) {
      departuresByMinute.delete(k);
    }
  }
}

function pushPirateStrength(strength) {
  pirateStrengthHistory.push({ t: Date.now(), v: Number(strength) || 0 });
  if (pirateStrengthHistory.length > 90) {
    pirateStrengthHistory.splice(0, pirateStrengthHistory.length - 90);
  }
}

function drawSparkline(canvasId, values, color, fillColor) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) {
    return;
  }
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  ctx.fillStyle = "#071520";
  ctx.fillRect(0, 0, width, height);

  if (!values.length) {
    return;
  }

  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = Math.max(0.001, max - min);
  const xStep = values.length > 1 ? width / (values.length - 1) : width;

  ctx.beginPath();
  values.forEach((value, index) => {
    const x = index * xStep;
    const y = height - ((value - min) / range) * (height - 16) - 8;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  ctx.lineTo(width, height);
  ctx.lineTo(0, height);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
}

function drawCharts() {
  const depValues = Array.from(departuresByMinute.entries())
    .sort((a, b) => new Date(a[0]).getTime() - new Date(b[0]).getTime())
    .slice(-30)
    .map((entry) => entry[1]);
  const pirateValues = pirateStrengthHistory.slice(-40).map((entry) => entry.v);

  drawSparkline("departures-chart", depValues, "#36d6a5", "rgba(54, 214, 165, 0.18)");
  drawSparkline("pirate-chart", pirateValues, "#ffd166", "rgba(255, 209, 102, 0.18)");
}

function renderControlSummary(config, faults) {
  const scenarioEl = document.getElementById("active-scenario-summary");
  const faultsEl = document.getElementById("active-faults-summary");
  const activeFaultSelect = document.getElementById("fault-active-name");

  const activeScenario = config.active_scenario;
  if (activeScenario) {
    scenarioEl.innerHTML = `
      <div class="pill-row">
        <span class="mini-pill"><strong>${escapeHtml(activeScenario.name)}</strong></span>
        <span class="mini-pill">intensity ${escapeHtml(activeScenario.intensity)}</span>
        <span class="mini-pill">${escapeHtml(activeScenario.duration_seconds)}s</span>
      </div>
    `;
  } else {
    scenarioEl.innerHTML = '<span class="summary-empty">No active scenario.</span>';
  }

  const activeFaults = faults.active || {};
  const entries = Object.entries(activeFaults);
  if (activeFaultSelect) {
    activeFaultSelect.innerHTML = entries.length
      ? entries
          .map(([name]) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`)
          .join("")
      : '<option value="">none active</option>';
  }
  if (!entries.length) {
    faultsEl.innerHTML = '<span class="summary-empty">No active faults.</span>';
    return;
  }

  faultsEl.innerHTML = `<div class="pill-row">${entries
    .map(
      ([name, value]) =>
        `<span class="mini-pill"><strong>${escapeHtml(name)}</strong> rate ${escapeHtml(value.rate)}</span>`
    )
    .join("")}</div>`;
}

function renderPirateEventSummary(config) {
  const pirateEl = document.getElementById("pirate-event-summary");
  const pirate = config.pirate_event || {};

  if (pirate.active) {
    const elapsedSeconds = pirate.started_at
      ? Math.floor((Date.now() - new Date(pirate.started_at).getTime()) / 1000)
      : 0;
    const elapsedMin = Math.floor(elapsedSeconds / 60);
    const elapsedStr = elapsedMin > 0 ? `${elapsedMin}m` : `${elapsedSeconds}s`;
    pirateEl.innerHTML = `
      <div class="pill-row">
        <span class="mini-pill status-active"><strong>ACTIVE</strong></span>
        <span class="mini-pill"><strong>${escapeHtml(pirate.anchor_body || "?")}</strong></span>
        <span class="mini-pill">strength ${(pirate.strength || 0).toFixed(2)}</span>
        <span class="mini-pill">duration ${elapsedStr}</span>
      </div>
    `;
  } else if (pirate.next_spawn_earliest_at) {
    const nextSpawnDate = new Date(pirate.next_spawn_earliest_at);
    const nowDate = new Date();
    const minutesUntil = Math.ceil((nextSpawnDate.getTime() - nowDate.getTime()) / 60000);
    const spawnStr = minutesUntil > 0 ? `in ~${minutesUntil}m` : "soon";
    pirateEl.innerHTML = `<span class="mini-pill">Next spawn ${spawnStr}</span>`;
  } else {
    pirateEl.innerHTML = '<span class="summary-empty">Pirate event inactive.</span>';
  }
}

function setKpis(stats) {
  const summary = stats.summary || {};
  document.getElementById("kpi-ships").textContent = fmtNum(summary.ships);
  document.getElementById("kpi-in-transit").textContent = fmtNum(summary.ships_in_transit);
  document.getElementById("kpi-stations").textContent = fmtNum(summary.stations);
  document.getElementById("kpi-departures").textContent = fmtNum(summary.departures);
  document.getElementById("kpi-control-events").textContent = fmtNum(summary.control_events);
  document.getElementById("kpi-pirates").textContent =
    typeof stats.pirate_strength === "number" ? stats.pirate_strength.toFixed(2) : "-";

  const active = stats.active_scenario;
  const text = active
    ? `Scenario: ${active.name} (intensity ${active.intensity})`
    : "Scenario: none";
  document.getElementById("scenario-meta").textContent = text;

  pushPirateStrength(stats.pirate_strength || 0);
  drawCharts();
}

function renderShipStates(rows) {
  const tbody = document.getElementById("ship-state-body");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    const statusClass = row.status === "active" ? "status-active" : "status-other";
    tr.innerHTML = [
      `<td>${row.ship_id}</td>`,
      `<td>${row.faction}</td>`,
      `<td><span class=\"status-pill ${statusClass}\">${row.status}</span></td>`,
      `<td>${row.in_transit ? "yes" : "no"}</td>`,
      `<td>${row.source_station_id || "-"}</td>`,
      `<td>${row.destination_station_id || "-"}</td>`
    ].join("");
    tbody.appendChild(tr);
  }
}

function renderShips(rows, count, total) {
  const tbody = document.getElementById("ships-body");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = [
      `<td>${row.id}</td>`,
      `<td>${row.name}</td>`,
      `<td>${row.faction}</td>`,
      `<td>${row.ship_type}</td>`,
      `<td>${row.cargo}</td>`
    ].join("");
    tbody.appendChild(tr);
  }

  const page = Math.floor(shipsQuery.offset / shipsQuery.limit) + 1;
  document.getElementById("ships-page-meta").textContent = `${page} | ${count}/${total}`;
  document.getElementById("ships-prev").disabled = shipsQuery.offset <= 0;
  document.getElementById("ships-next").disabled = shipsQuery.offset + shipsQuery.limit >= total;
}

function renderStations(rows, count, total) {
  const tbody = document.getElementById("stations-body");
  tbody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = [
      `<td>${row.id}</td>`,
      `<td>${row.name}</td>`,
      `<td>${row.body_name}</td>`,
      `<td>${row.body_type}</td>`,
      `<td>${row.parent_body}</td>`
    ].join("");
    tbody.appendChild(tr);
  }

  const page = Math.floor(stationsQuery.offset / stationsQuery.limit) + 1;
  document.getElementById("stations-page-meta").textContent = `${page} | ${count}/${total}`;
  document.getElementById("stations-prev").disabled = stationsQuery.offset <= 0;
  document.getElementById("stations-next").disabled = stationsQuery.offset + stationsQuery.limit >= total;
}

async function refreshSnapshots() {
  const [stats, statePayload] = await Promise.all([
    requestJson("/stats"),
    requestJson("/ships/state?limit=20")
  ]);
  setKpis(stats);
  renderShipStates(statePayload.ships || []);
}

async function refreshShips() {
  const params = new URLSearchParams();
  params.set("offset", String(shipsQuery.offset));
  params.set("limit", String(shipsQuery.limit));
  if (shipsQuery.faction) {
    params.set("faction", shipsQuery.faction);
  }
  const payload = await requestJson(`/ships?${params.toString()}`);
  renderShips(payload.ships || [], payload.count || 0, payload.total_count || 0);
}

async function refreshStations() {
  const params = new URLSearchParams();
  params.set("offset", String(stationsQuery.offset));
  params.set("limit", String(stationsQuery.limit));
  if (stationsQuery.body_type) {
    params.set("body_type", stationsQuery.body_type);
  }
  const payload = await requestJson(`/stations?${params.toString()}`);
  renderStations(payload.stations || [], payload.count || 0, payload.total_count || 0);
}

async function loadControlData() {
  const [config, scenarios, faults] = await Promise.all([
    requestJson("/config"),
    requestJson("/scenarios"),
    requestJson("/faults")
  ]);

  document.getElementById("cfg-deterministic").checked = Boolean(config.deterministic_mode);
  const seed = config.deterministic_seed;
  document.getElementById("cfg-seed").value = seed !== null && seed !== undefined ? String(seed) : "";

  const scenarioSelect = document.getElementById("scenario-name");
  scenarioSelect.innerHTML = "";
  (scenarios.available || []).forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.name;
    option.textContent = entry.name;
    scenarioSelect.appendChild(option);
  });

  const faultSelect = document.getElementById("fault-name");
  faultSelect.innerHTML = "";
  (faults.available || []).forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.name;
    option.textContent = `${entry.name} (${entry.default_rate})`;
    faultSelect.appendChild(option);
  });

  setPirateInputValues({
    pirate_spawn_probability_per_day: config.pirate_spawn_probability_per_day ?? 1.0,
    pirate_strength_decay_per_day: config.pirate_strength_decay_per_day ?? 0.03,
    pirate_strength_end_threshold: config.pirate_strength_end_threshold ?? 0.3,
    pirate_strength_start: config.pirate_strength_start ?? 1.0,
    pirate_respawn_min_days: config.pirate_respawn_min_days ?? 0.2,
    pirate_respawn_max_days: config.pirate_respawn_max_days ?? 1.0
  });

  renderControlSummary(config, faults);
  renderPirateEventSummary(config);
}

function bindControls() {
  const ctrlLog = document.getElementById("control-log");
  const cfgSaveButton = document.getElementById("cfg-save");
  const resetButton = document.getElementById("ctl-reset");
  const scenarioActivateButton = document.getElementById("scenario-activate");
  const scenarioDeactivateButton = document.getElementById("scenario-deactivate");
  const faultActivateButton = document.getElementById("fault-activate");
  const faultDeactivateButton = document.getElementById("fault-deactivate");
  const faultClearButton = document.getElementById("fault-clear");
  const pirateApplyButton = document.getElementById("pirate-apply");
  const piratePresetApplyButton = document.getElementById("pirate-preset-apply");

  cfgSaveButton.addEventListener("click", async () => {
    await withButtonBusy(cfgSaveButton, "Applying...", async () => {
      try {
        const deterministicMode = document.getElementById("cfg-deterministic").checked;
        const seedRaw = document.getElementById("cfg-seed").value.trim();
        const payload = { deterministic_mode: deterministicMode };
        if (seedRaw) {
          payload.deterministic_seed = Number(seedRaw);
        }

        setControlStatus("pending", "Applying runtime configuration...");
        await requestJson("/config", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        await loadControlData();
        setControlStatus("success", "Runtime configuration updated.");
        appendLog(ctrlLog, "[control] config patched");
        recordOperatorAction("Config updated", "Deterministic mode and seed saved.");
        showToast("success", "Config Applied", "Runtime configuration updated.");
      } catch (err) {
        setControlStatus("error", `Config update failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Config update failed", String(err), "error");
        showToast("error", "Config Failed", String(err));
      }
    });
  });

  resetButton.addEventListener("click", async () => {
    if (!window.confirm("Reset the simulation state and clear departure history?")) {
      return;
    }

    await withButtonBusy(resetButton, "Resetting...", async () => {
      try {
        const seedRaw = document.getElementById("cfg-seed").value.trim();
        const payload = {};
        if (seedRaw) {
          payload.seed = Number(seedRaw);
        }

        setControlStatus("pending", "Resetting simulation state...");
        await requestJson("/control/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        await Promise.all([refreshSnapshots(), refreshShips(), refreshStations(), loadControlData()]);
        setControlStatus("success", "Simulation reset applied.");
        appendLog(ctrlLog, "[control] reset applied");
        recordOperatorAction("Simulation reset", "State and departures cleared.");
        showToast("success", "Simulation Reset", "State and departure history were reset.");
      } catch (err) {
        setControlStatus("error", `Reset failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Reset failed", String(err), "error");
        showToast("error", "Reset Failed", String(err));
      }
    });
  });

  scenarioActivateButton.addEventListener("click", async () => {
    await withButtonBusy(scenarioActivateButton, "Activating...", async () => {
      try {
        const payload = {
          name: document.getElementById("scenario-name").value,
          intensity: Number(document.getElementById("scenario-intensity").value || "1"),
          duration_seconds: Number(document.getElementById("scenario-duration").value || "300")
        };
        setControlStatus("pending", `Activating scenario ${payload.name}...`);
        await requestJson("/scenarios/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        await Promise.all([refreshSnapshots(), loadControlData()]);
        setControlStatus("success", `Scenario ${payload.name} is active.`);
        appendLog(ctrlLog, `[control] scenario activated: ${payload.name}`);
        recordOperatorAction("Scenario activated", `${payload.name} intensity ${payload.intensity}.`);
        showToast("success", "Scenario Activated", `${payload.name} is now active.`);
      } catch (err) {
        setControlStatus("error", `Scenario activation failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Scenario activation failed", String(err), "error");
        showToast("error", "Scenario Failed", String(err));
      }
    });
  });

  scenarioDeactivateButton.addEventListener("click", async () => {
    if (!window.confirm("Deactivate the current scenario?")) {
      return;
    }

    await withButtonBusy(scenarioDeactivateButton, "Clearing...", async () => {
      try {
        setControlStatus("pending", "Deactivating current scenario...");
        await requestJson("/scenarios/deactivate", { method: "POST" });
        await Promise.all([refreshSnapshots(), loadControlData()]);
        setControlStatus("success", "Scenario deactivated.");
        appendLog(ctrlLog, "[control] scenario deactivated");
        recordOperatorAction("Scenario deactivated", "Active scenario cleared.");
        showToast("success", "Scenario Cleared", "The active scenario was deactivated.");
      } catch (err) {
        setControlStatus("error", `Scenario deactivation failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Scenario deactivation failed", String(err), "error");
        showToast("error", "Scenario Clear Failed", String(err));
      }
    });
  });

  faultActivateButton.addEventListener("click", async () => {
    await withButtonBusy(faultActivateButton, "Injecting...", async () => {
      try {
        const name = document.getElementById("fault-name").value;
        const rate = Number(document.getElementById("fault-rate").value || "0.2");
        const duration = Number(document.getElementById("fault-duration").value || "120");
        const payload = { faults: { [name]: { rate, duration_seconds: duration } } };
        setControlStatus("pending", `Activating fault ${name}...`);
        await requestJson("/faults/activate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        await loadControlData();
        setControlStatus("success", `Fault ${name} activated.`);
        appendLog(ctrlLog, `[control] fault activated: ${name}`);
        recordOperatorAction("Fault activated", `${name} rate ${rate}.`);
        showToast("success", "Fault Activated", `${name} is now affecting live events.`);
      } catch (err) {
        setControlStatus("error", `Fault activation failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Fault activation failed", String(err), "error");
        showToast("error", "Fault Failed", String(err));
      }
    });
  });

  faultDeactivateButton.addEventListener("click", async () => {
    const name = document.getElementById("fault-active-name").value;
    if (!name) {
      showToast("warn", "No Fault Selected", "Choose an active fault to clear.");
      return;
    }
    if (!window.confirm(`Deactivate fault ${name}?`)) {
      return;
    }

    await withButtonBusy(faultDeactivateButton, "Clearing...", async () => {
      try {
        setControlStatus("pending", `Clearing fault ${name}...`);
        await requestJson("/faults/deactivate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ names: [name] })
        });
        await loadControlData();
        setControlStatus("success", `Fault ${name} cleared.`);
        appendLog(ctrlLog, `[control] fault cleared: ${name}`);
        recordOperatorAction("Fault cleared", `${name} deactivated.`);
        showToast("success", "Fault Cleared", `${name} was deactivated.`);
      } catch (err) {
        setControlStatus("error", `Fault clear failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Fault clear failed", String(err), "error");
        showToast("error", "Fault Clear Failed", String(err));
      }
    });
  });

  faultClearButton.addEventListener("click", async () => {
    if (!window.confirm("Clear all active faults?")) {
      return;
    }

    await withButtonBusy(faultClearButton, "Clearing...", async () => {
      try {
        setControlStatus("pending", "Clearing active faults...");
        await requestJson("/faults/deactivate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        });
        await loadControlData();
        setControlStatus("success", "All active faults cleared.");
        appendLog(ctrlLog, "[control] all faults cleared");
        recordOperatorAction("All faults cleared", "Every active fault was removed.");
        showToast("success", "Faults Cleared", "All active faults were cleared.");
      } catch (err) {
        setControlStatus("error", `Fault clear failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Clear all faults failed", String(err), "error");
        showToast("error", "Fault Clear Failed", String(err));
      }
    });
  });

  piratePresetApplyButton.addEventListener("click", () => {
    const presetName = document.getElementById("pirate-preset").value;
    if (presetName === "custom") {
      showToast("warn", "Custom Selected", "Pick a named preset to populate the pirate controls.");
      return;
    }

    const preset = PIRATE_PRESETS[presetName];
    if (!preset) {
      showToast("error", "Preset Missing", `Unknown preset: ${presetName}`);
      return;
    }

    setPirateInputValues(preset);
    recordOperatorAction("Pirate preset loaded", `${presetName} values loaded into inputs.`);
    showToast("success", "Preset Loaded", `${presetName} preset loaded. Click Apply to push it live.`);
  });

  pirateApplyButton.addEventListener("click", async () => {
    await withButtonBusy(pirateApplyButton, "Applying...", async () => {
      try {
        const payload = getPirateInputValues();
        setControlStatus("pending", "Applying pirate activity settings...");
        await requestJson("/config", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        await loadControlData();
        setControlStatus("success", "Pirate activity settings updated.");
        appendLog(ctrlLog, "[control] pirate settings patched");
        recordOperatorAction(
          "Pirate settings updated",
          `Spawn ${payload.pirate_spawn_probability_per_day.toFixed(2)}, respawn ${payload.pirate_respawn_min_days}-${payload.pirate_respawn_max_days} days.`
        );
        showToast("success", "Pirate Config Applied", "Activity settings updated. New events will use these parameters.");
      } catch (err) {
        setControlStatus("error", `Pirate settings update failed: ${err}`);
        appendLog(ctrlLog, `[control-error] ${err}`);
        recordOperatorAction("Pirate settings failed", String(err), "error");
        showToast("error", "Pirate Config Failed", String(err));
      }
    });
  });
}

function bindExplorerControls() {
  const ctrlLog = document.getElementById("control-log");

  document.getElementById("ships-refresh").addEventListener("click", async () => {
    shipsQuery.faction = document.getElementById("ships-faction").value;
    shipsQuery.limit = Number(document.getElementById("ships-limit").value);
    shipsQuery.offset = 0;
    try {
      await refreshShips();
    } catch (err) {
      appendLog(ctrlLog, `[ships-error] ${err}`);
      showToast("error", "Ships Refresh Failed", String(err));
    }
  });

  document.getElementById("ships-prev").addEventListener("click", async () => {
    shipsQuery.offset = Math.max(0, shipsQuery.offset - shipsQuery.limit);
    try {
      await refreshShips();
    } catch (err) {
      appendLog(ctrlLog, `[ships-error] ${err}`);
      showToast("error", "Ships Paging Failed", String(err));
    }
  });

  document.getElementById("ships-next").addEventListener("click", async () => {
    shipsQuery.offset += shipsQuery.limit;
    try {
      await refreshShips();
    } catch (err) {
      appendLog(ctrlLog, `[ships-error] ${err}`);
      showToast("error", "Ships Paging Failed", String(err));
    }
  });

  document.getElementById("stations-refresh").addEventListener("click", async () => {
    stationsQuery.body_type = document.getElementById("stations-body-type").value;
    stationsQuery.limit = Number(document.getElementById("stations-limit").value);
    stationsQuery.offset = 0;
    try {
      await refreshStations();
    } catch (err) {
      appendLog(ctrlLog, `[stations-error] ${err}`);
      showToast("error", "Stations Refresh Failed", String(err));
    }
  });

  document.getElementById("stations-prev").addEventListener("click", async () => {
    stationsQuery.offset = Math.max(0, stationsQuery.offset - stationsQuery.limit);
    try {
      await refreshStations();
    } catch (err) {
      appendLog(ctrlLog, `[stations-error] ${err}`);
      showToast("error", "Stations Paging Failed", String(err));
    }
  });

  document.getElementById("stations-next").addEventListener("click", async () => {
    stationsQuery.offset += stationsQuery.limit;
    try {
      await refreshStations();
    } catch (err) {
      appendLog(ctrlLog, `[stations-error] ${err}`);
      showToast("error", "Stations Paging Failed", String(err));
    }
  });
}

function initStreams() {
  const depLog = document.getElementById("departures-log");
  const ctrlLog = document.getElementById("control-log");

  setStreamStatus("departures-stream-status", "pending", "connecting");
  const depEs = new EventSource("/departures/stream");
  depEs.onopen = () => setStreamStatus("departures-stream-status", "success", "live");
  depEs.addEventListener("departure", (event) => {
    try {
      const payload = JSON.parse(event.data);
      const line = `${payload.id} | ${payload.departure_time} | ${payload.ship_id || "?"} | ${payload.source_station_id || "?"} -> ${payload.destination_station_id || "?"}`;
      appendLog(depLog, line);
      incrementDepartureMinute(payload.departure_time);
      drawCharts();
    } catch {
      appendLog(depLog, event.data);
    }
  });
  depEs.onerror = () => {
    setStreamStatus("departures-stream-status", "error", "reconnecting");
    appendLog(depLog, "[stream] departure connection interrupted");
  };

  setStreamStatus("control-stream-status", "pending", "connecting");
  const ctrlEs = new EventSource("/control-events/stream");
  ctrlEs.onopen = () => setStreamStatus("control-stream-status", "success", "live");
  ctrlEs.addEventListener("control_event", (event) => {
    try {
      const payload = JSON.parse(event.data);
      const line = `${payload.id} | ${payload.event_time} | ${payload.event_type}/${payload.action} | ${fmtShortJson(payload.payload)}`;
      appendLog(ctrlLog, line);
    } catch {
      appendLog(ctrlLog, event.data);
    }
  });
  ctrlEs.onerror = () => {
    setStreamStatus("control-stream-status", "error", "reconnecting");
    appendLog(ctrlLog, "[stream] control connection interrupted");
  };
}

async function init() {
  const depLog = document.getElementById("departures-log");
  const ctrlLog = document.getElementById("control-log");
  appendLog(depLog, "connecting to /departures/stream ...");
  appendLog(ctrlLog, "connecting to /control-events/stream ...");

  bindControls();
  bindExplorerControls();

  try {
    await Promise.all([
      refreshSnapshots(),
      refreshShips(),
      refreshStations(),
      loadControlData()
    ]);
  } catch (err) {
    appendLog(ctrlLog, `[error] ${err}`);
  }

  initStreams();
  recordOperatorAction("Console ready", "Dashboard connected to live snapshots.", "success");
  setControlStatus("idle", "Live streams connected. Console ready.");
  setInterval(async () => {
    try {
      await refreshSnapshots();
    } catch (err) {
      appendLog(ctrlLog, `[refresh-error] ${err}`);
    }
  }, 5000);
}

init();
