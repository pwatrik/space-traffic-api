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

function initStreams() {
  const depLog = document.getElementById("departures-log");
  const ctrlLog = document.getElementById("control-log");

  const depEs = new EventSource("/departures/stream");
  depEs.addEventListener("departure", (event) => {
    try {
      const payload = JSON.parse(event.data);
      const line = `${payload.id} | ${payload.departure_time} | ${payload.ship_id || "?"} | ${payload.source_station_id || "?"} -> ${payload.destination_station_id || "?"}`;
      appendLog(depLog, line);
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

  try {
    await refreshSnapshots();
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
