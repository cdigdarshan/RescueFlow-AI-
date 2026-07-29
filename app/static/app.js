const lanes = ["Lane A", "Lane B", "Lane C", "Lane D"];
const laneCounts = document.querySelector("#laneCounts");
const vehicleTypes = document.querySelector("#vehicleTypes");

const signalColors = {
  RED: "#dc4654",
  YELLOW: "#f3bf3b",
  GREEN: "#31b884",
};

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = value;
}

function renderStorageStatus(database) {
  const storage = document.querySelector("#storageStatus");
  const status = database.available ? "online" : "offline";
  storage.dataset.status = status;
  storage.querySelector("strong").textContent = database.available ? "Online" : "Offline";
}

function renderFinalSignal(status) {
  const signal = document.querySelector("#finalSignal");
  signal.dataset.status = status;
  document.querySelector("#finalSignalText").textContent = status;
  signal.querySelectorAll("[data-light]").forEach((light) => {
    const active = light.dataset.light === status;
    light.style.background = active ? signalColors[status] : "#2d3748";
    light.style.boxShadow = active ? `0 0 0 7px ${signalColors[status]}26` : "none";
  });
}

function renderCountdown(data) {
  const widget = document.querySelector("#countdownWidget");
  const lamp = document.querySelector("#countdownLamp");
  const fill = document.querySelector("#countdownFill");
  const seconds = Math.max(0, data.secondsRemaining || 0);
  const total = Math.max(1, data.greenTime || 1);
  const percent = Math.max(0, Math.min(100, (seconds / total) * 100));

  widget.dataset.status = data.finalSignal;
  lamp.style.background = signalColors[data.finalSignal] || signalColors.RED;
  document.querySelector("#secondsRemaining").textContent = seconds;
  fill.style.width = `${percent}%`;
}

function renderEmergencyPriority(data) {
  const priority = document.querySelector("#emergencyPriority");
  const text = document.querySelector("#emergencyPriorityText");
  const meta = document.querySelector("#emergencyPriorityMeta");
  const detector = data.emergencyDetector || {};
  const phase = data.priorityMode || "NORMAL";

  if (!detector.available && !data.emergencyActive) {
    priority.dataset.status = "unavailable";
    text.textContent = "Detector unavailable";
    meta.textContent = detector.configured
      ? detector.error || "Unable to load ambulance model"
      : "Add assets/models/ambulance.pt";
    return;
  }

  if (phase === "RECOVERY_ALL_RED") {
    priority.dataset.status = "transition";
    text.textContent = "Recovery: all lanes red";
    meta.textContent = "Returning safely to normal operation";
    return;
  }

  if (!data.emergencyActive) {
    priority.dataset.status = "inactive";
    text.textContent = "Normal";
    meta.textContent = "ByteTrack detector ready";
    return;
  }

  const phaseLabels = {
    CLEARING_CURRENT_GREEN: "Clearing current green",
    ALL_RED_SAFETY: "Safety interval",
    EMERGENCY_GREEN: "Emergency green",
  };
  priority.dataset.status = phase === "EMERGENCY_GREEN" ? "active" : "transition";
  const trackId = data.emergencyTrackId == null ? "" : ` #${data.emergencyTrackId}`;
  text.textContent = `${phaseLabels[phase] || "Emergency"}: ${data.emergencyType}${trackId} in ${data.emergencyLane}`;
  const confidence = data.emergencyConfidence == null
    ? ""
    : ` • ${Math.round(data.emergencyConfidence * 100)}% confidence`;
  meta.textContent = `${data.emergencyTrackingStatus || "TRACKING"}${confidence}`;
}

function renderLaneCounts(counts, uniqueCounts, queueMetrics, greenLane) {
  const max = Math.max(1, ...Object.values(counts));
  laneCounts.innerHTML = lanes
    .map((lane) => {
      const count = counts[lane] || 0;
      const unique = uniqueCounts[lane] || 0;
      const queue = queueMetrics[lane] || {
        queueMeters: 0,
        averageWaitSeconds: 0,
      };
      const width = Math.max(6, (count / max) * 100);
      const density = count <= 2 ? "low" : count <= 5 ? "medium" : "high";
      const active = lane === greenLane ? " active" : "";
      return `
        <article class="bar-row${active}" data-density="${density}">
          <div class="bar-label">
            <div class="bar-title">
              <strong>${lane}</strong>
              <small>${density}</small>
            </div>
            <span>${count} vehicles | ${queue.queueMeters} meters queue | ${queue.averageWaitSeconds}s avg wait | ${unique} tracked</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width: ${width}%"></div>
          </div>
        </article>
      `;
    })
    .join("");
}

async function refreshReport() {
  const response = await fetch("/reports", { cache: "no-store" });
  const data = await response.json();

  setText("reportSnapshots", data.snapshots || 0);
  setText("reportAverage", data.averageVehicles || 0);
  setText("reportHighDensity", data.highDensityEvents || 0);
}

function renderVehicleTypes(types) {
  vehicleTypes.innerHTML = Object.entries(types)
    .map(
      ([type, count]) => `
        <article>
          <span>${type}</span>
          <strong>${count}</strong>
        </article>
      `
    )
    .join("");
}

async function refreshStats() {
  const response = await fetch("/stats", { cache: "no-store" });
  const data = await response.json();

  setText("totalVehicles", data.totalVehicles);
  setText("totalUniqueVehicles", data.totalUniqueVehicles);
  setText("trafficDensity", data.trafficDensity);
  setText("greenLane", data.greenLane);

  renderStorageStatus(data.database);
  renderFinalSignal(data.finalSignal);
  renderCountdown(data);
  renderEmergencyPriority(data);
  renderLaneCounts(data.laneCounts, data.uniqueLaneCounts, data.queueMetrics, data.greenLane);
  renderVehicleTypes(data.vehicleTypes);
}

refreshStats();
refreshReport();
setInterval(refreshStats, 900);
setInterval(refreshReport, 10000);
