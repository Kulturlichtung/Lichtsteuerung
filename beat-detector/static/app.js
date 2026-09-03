/* Tuning UI client. Talks to web_ui.py's /ws endpoint: receives a
 * "config" message on connect and after every edit (server is the
 * single source of truth -- see web_ui.py's handle_ws), and "metrics"
 * messages at ~10Hz with live flux/threshold/level_db data. Sends
 * set_sensitivity / set_intensity_thresholds edits back.
 *
 * The beat-detection threshold line is NOT a stored value -- it's
 * mean + sensitivity*std, recomputed every tick in beat_osc.py. A drag
 * on that line is inverted into a new sensitivity using the most
 * recently broadcast mean/std (see onBeatDragEnd below). The number
 * field, by contrast, edits sensitivity directly -- no inversion
 * needed there.
 */
(function () {
  "use strict";

  const WINDOW_S = 30;
  const RECONNECT_MS = 1000;

  const statusEl = document.getElementById("status");
  const qlcLink = document.getElementById("qlc-link");
  qlcLink.href = `http://${location.hostname}:9999/`;

  const sensitivityInput = document.getElementById("sensitivity");
  const d1Input = document.getElementById("d1");
  const d2Input = document.getElementById("d2");
  const d3Input = document.getElementById("d3");

  let ws = null;
  let lastMean = null;
  let lastStd = null;
  let draggingBeat = false;
  let draggingIntensity = { d1: false, d2: false, d3: false };
  // Suppress the input's own "change" handler while we're the one
  // writing its value from an incoming config broadcast.
  let applyingRemoteConfig = false;

  const fluxData = [];
  const levelData = [];

  function trimOld(arr, latestT) {
    while (arr.length && latestT - arr[0].x > WINDOW_S) arr.shift();
  }

  function clamp(v, lo, hi) {
    return Math.min(Math.max(v, lo), hi);
  }

  const beatChart = new Chart(document.getElementById("beatChart"), {
    type: "line",
    data: {
      datasets: [{
        label: "Flux",
        data: fluxData,
        borderColor: "#4da3ff",
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0,
      }],
    },
    options: {
      animation: false,
      parsing: false,
      scales: {
        x: { type: "linear", ticks: { display: false } },
        y: { beginAtZero: true },
      },
      plugins: {
        legend: { display: false },
        annotation: {
          annotations: {
            threshold: {
              type: "line",
              yMin: 0,
              yMax: 0,
              borderColor: "#e0a030",
              borderWidth: 2,
              draggable: true,
              label: { content: "Schwelle", display: true, position: "end" },
              enter: () => { draggingBeat = true; },
              leave: () => { draggingBeat = false; },
              onDragEnd: onBeatDragEnd,
            },
          },
        },
      },
    },
  });

  const intensityChart = new Chart(document.getElementById("intensityChart"), {
    type: "line",
    data: {
      datasets: [{
        label: "Pegel (dB)",
        data: levelData,
        borderColor: "#4dd0a3",
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0,
      }],
    },
    options: {
      animation: false,
      parsing: false,
      scales: {
        x: { type: "linear", ticks: { display: false } },
        y: {},
      },
      plugins: {
        legend: { display: false },
        annotation: {
          annotations: {
            d1: intensityLineAnnotation("D1", "#e05555", "d1"),
            d2: intensityLineAnnotation("D2", "#e0a030", "d2"),
            d3: intensityLineAnnotation("D3", "#4da3ff", "d3"),
          },
        },
      },
    },
  });

  function intensityLineAnnotation(label, color, key) {
    return {
      type: "line",
      yMin: 0,
      yMax: 0,
      borderColor: color,
      borderWidth: 2,
      draggable: true,
      label: { content: label, display: true, position: "end" },
      enter: () => { draggingIntensity[key] = true; },
      leave: () => { draggingIntensity[key] = false; },
      onDragEnd: onIntensityDragEnd,
    };
  }

  function onBeatDragEnd() {
    const ann = beatChart.options.plugins.annotation.annotations.threshold;
    if (lastStd === null || lastStd <= 0) return;
    const sensitivity = clamp((ann.yMin - lastMean) / lastStd, 0.1, 10.0);
    sendMessage({ type: "set_sensitivity", value: sensitivity });
  }

  function onIntensityDragEnd() {
    const anns = intensityChart.options.plugins.annotation.annotations;
    sendMessage({
      type: "set_intensity_thresholds",
      values: [anns.d1.yMin, anns.d2.yMin, anns.d3.yMin],
    });
  }

  function sendMessage(msg) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }

  function applyConfig(cfg) {
    applyingRemoteConfig = true;
    try {
      if (!draggingBeat) {
        sensitivityInput.value = cfg.sensitivity;
      }
      const [d1, d2, d3] = cfg.intensity_thresholds_db;
      if (!draggingIntensity.d1) d1Input.value = d1;
      if (!draggingIntensity.d2) d2Input.value = d2;
      if (!draggingIntensity.d3) d3Input.value = d3;

      const anns = intensityChart.options.plugins.annotation.annotations;
      if (!draggingIntensity.d1) { anns.d1.yMin = d1; anns.d1.yMax = d1; }
      if (!draggingIntensity.d2) { anns.d2.yMin = d2; anns.d2.yMax = d2; }
      if (!draggingIntensity.d3) { anns.d3.yMin = d3; anns.d3.yMax = d3; }
      intensityChart.update("none");
    } finally {
      applyingRemoteConfig = false;
    }
  }

  sensitivityInput.addEventListener("change", () => {
    if (applyingRemoteConfig) return;
    sendMessage({ type: "set_sensitivity", value: parseFloat(sensitivityInput.value) });
  });

  function sendThresholdsFromInputs() {
    if (applyingRemoteConfig) return;
    sendMessage({
      type: "set_intensity_thresholds",
      values: [parseFloat(d1Input.value), parseFloat(d2Input.value), parseFloat(d3Input.value)],
    });
  }
  d1Input.addEventListener("change", sendThresholdsFromInputs);
  d2Input.addEventListener("change", sendThresholdsFromInputs);
  d3Input.addEventListener("change", sendThresholdsFromInputs);

  function applyMetrics(m) {
    if (m.flux !== null && m.flux !== undefined) {
      fluxData.push({ x: m.t, y: m.flux });
      trimOld(fluxData, m.t);
    }
    if (m.threshold !== null && m.threshold !== undefined && !draggingBeat) {
      const ann = beatChart.options.plugins.annotation.annotations.threshold;
      ann.yMin = m.threshold;
      ann.yMax = m.threshold;
    }
    if (m.mean !== null && m.mean !== undefined) lastMean = m.mean;
    if (m.std !== null && m.std !== undefined) lastStd = m.std;

    levelData.push({ x: m.t, y: m.level_db });
    trimOld(levelData, m.t);

    beatChart.update("none");
    intensityChart.update("none");
  }

  function setStatus(connected) {
    statusEl.textContent = connected ? "verbunden" : "getrennt";
    statusEl.className = connected ? "connected" : "disconnected";
    const disabled = !connected;
    document.getElementById("beat-controls").dataset.disabled = String(disabled);
    document.getElementById("intensity-controls").dataset.disabled = String(disabled);
  }

  function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => setStatus(true);
    ws.onclose = () => {
      setStatus(false);
      setTimeout(connect, RECONNECT_MS);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (data.type === "config") applyConfig(data);
      else if (data.type === "metrics") applyMetrics(data);
    };
  }

  connect();
})();
