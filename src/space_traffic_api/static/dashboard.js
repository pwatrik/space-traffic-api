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

function appendLog(el, line, maxLines = 160) {
  const current = el.textContent ? el.textContent.split("\n") : [];
  current.push(line);
  if (current.length > maxLines) {
    current.splice(0, current.length - maxLines);
  }
  el.textContent = current.join("\n");
  el.scrollTop = el.scrollHeight;
}

function setControlStatus(text) {
  document.getElementById("control-status").textContent = `Control status: ${text}`;
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
  const [statsResp, stateResp] = await Promise.all([
    fetch("/stats"),
    fetch("/ships/state?limit=20")
  ]);
  if (!statsResp.ok || !stateResp.ok) {
    throw new Error("Snapshot fetch failed.");
  }
  const stats = await statsResp.json();
  const statePayload = await stateResp.json();
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
  const resp = await fetch(`/ships?${params.toString()}`);
  if (!resp.ok) {
    throw new Error("Ships fetch failed.");
  }
  const payload = await resp.json();
  renderShips(payload.ships || [], payload.count || 0, payload.total_count || 0);
}

async function refreshStations() {
  const params = new URLSearchParams();
  params.set("offset", String(stationsQuery.offset));
  params.set("limit", String(stationsQuery.limit));
  if (stationsQuery.body_type) {
    params.set("body_type", stationsQuery.body_type);
  }
  const resp = await fetch(`/stations?${params.toString()}`);
  if (!resp.ok) {
    throw new Error("Stations fetch failed.");
  }
  const payload = await resp.json();
  renderStations(payload.stations || [], payload.count || 0, payload.total_count || 0);
}

async function loadControlData() {
  const [configResp, scenariosResp, faultsResp] = await Promise.all([
    fetch("/config"),
    fetch("/scenarios"),
    fetch("/faults")
  ]);
  if (!configResp.ok || !scenariosResp.ok || !faultsResp.ok) {
    throw new Error("Control data fetch failed.");
  }

  const config = await configResp.json();
  const scenarios = await scenariosResp.json();
  const faults = await faultsResp.json();

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
}

function bindControls() {
  const ctrlLog = document.getElementById("control-log");

  document.getElementById("cfg-save").addEventListener("click", async () => {
    try {
      const deterministicMode = document.getElementById("cfg-deterministic").checked;
      const seedRaw = document.getElementById("cfg-seed").value.trim();
      const payload = { deterministic_mode: deterministicMode };
      if (seedRaw) {
        payload.deterministic_seed = Number(seedRaw);
      }

      const resp = await fetch("/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus("config updated");
      appendLog(ctrlLog, "[control] config patched");
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
  });

  document.getElementById("ctl-reset").addEventListener("click", async () => {
    try {
      const seedRaw = document.getElementById("cfg-seed").value.trim();
      const payload = {};
      if (seedRaw) {
        payload.seed = Number(seedRaw);
      }
      const resp = await fetch("/control/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus("reset applied");
      appendLog(ctrlLog, "[control] reset applied");
      await Promise.all([refreshSnapshots(), refreshShips(), refreshStations()]);
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
  });

  document.getElementById("scenario-activate").addEventListener("click", async () => {
    try {
      const payload = {
        name: document.getElementById("scenario-name").value,
        intensity: Number(document.getElementById("scenario-intensity").value || "1"),
        duration_seconds: Number(document.getElementById("scenario-duration").value || "300")
      };
      const resp = await fetch("/scenarios/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus(`scenario ${payload.name} active`);
      appendLog(ctrlLog, `[control] scenario activated: ${payload.name}`);
      await refreshSnapshots();
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
  });

  document.getElementById("scenario-deactivate").addEventListener("click", async () => {
    try {
      const resp = await fetch("/scenarios/deactivate", { method: "POST" });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus("scenario deactivated");
      appendLog(ctrlLog, "[control] scenario deactivated");
      await refreshSnapshots();
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
  });

  document.getElementById("fault-activate").addEventListener("click", async () => {
    try {
      const name = document.getElementById("fault-name").value;
      const rate = Number(document.getElementById("fault-rate").value || "0.2");
      const duration = Number(document.getElementById("fault-duration").value || "120");
      const payload = { faults: { [name]: { rate, duration_seconds: duration } } };
      const resp = await fetch("/faults/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus(`fault ${name} activated`);
      appendLog(ctrlLog, `[control] fault activated: ${name}`);
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
  });

  document.getElementById("fault-clear").addEventListener("click", async () => {
    try {
      const resp = await fetch("/faults/deactivate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
      });
      if (!resp.ok) {
        throw new Error(await resp.text());
      }
      setControlStatus("all faults cleared");
      appendLog(ctrlLog, "[control] all faults cleared");
    } catch (err) {
      setControlStatus(`error: ${err}`);
      appendLog(ctrlLog, `[control-error] ${err}`);
    }
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
    }
  });

  document.getElementById("ships-prev").addEventListener("click", async () => {
    shipsQuery.offset = Math.max(0, shipsQuery.offset - shipsQuery.limit);
    try {
      await refreshShips();
    } catch (err) {
      appendLog(ctrlLog, `[ships-error] ${err}`);
    }
  });

  document.getElementById("ships-next").addEventListener("click", async () => {
    shipsQuery.offset += shipsQuery.limit;
    try {
      await refreshShips();
    } catch (err) {
      appendLog(ctrlLog, `[ships-error] ${err}`);
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
    }
  });

  document.getElementById("stations-prev").addEventListener("click", async () => {
    stationsQuery.offset = Math.max(0, stationsQuery.offset - stationsQuery.limit);
    try {
      await refreshStations();
    } catch (err) {
      appendLog(ctrlLog, `[stations-error] ${err}`);
    }
  });

  document.getElementById("stations-next").addEventListener("click", async () => {
    stationsQuery.offset += stationsQuery.limit;
    try {
      await refreshStations();
    } catch (err) {
      appendLog(ctrlLog, `[stations-error] ${err}`);
    }
  });
}

function initStreams() {
  const depLog = document.getElementById("departures-log");
  const ctrlLog = document.getElementById("control-log");

  const depEs = new EventSource("/departures/stream");
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
  depEs.onerror = () => appendLog(depLog, "[stream] departure connection interrupted");

  const ctrlEs = new EventSource("/control-events/stream");
  ctrlEs.addEventListener("control_event", (event) => {
    try {
      const payload = JSON.parse(event.data);
      const line = `${payload.id} | ${payload.event_time} | ${payload.event_type}/${payload.action} | ${fmtShortJson(payload.payload)}`;
      appendLog(ctrlLog, line);
    } catch {
      appendLog(ctrlLog, event.data);
    }
  });
  ctrlEs.onerror = () => appendLog(ctrlLog, "[stream] control connection interrupted");
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
  setInterval(async () => {
    try {
      await refreshSnapshots();
    } catch (err) {
      appendLog(ctrlLog, `[refresh-error] ${err}`);
    }
  }, 5000);
}

init();
