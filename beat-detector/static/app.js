/* Tuning UI client. Talks to web_ui.py's /ws endpoint: receives a
 * "config" message on connect and after every edit (server is the
 * single source of truth -- see web_ui.py's handle_ws), and "metrics"
 * messages at ~10Hz with live flux/mean/std/threshold/level_db data.
 * Sends set_sensitivity / set_intensity_thresholds / reset_to_default
 * edits back.
 *
 * Beat chart: beat_osc.py's own math is threshold = mean + sensitivity
 * * std, i.e. sensitivity only makes sense in units of "std deviations
 * above the rolling mean" -- plotting the raw flux value against that
 * threshold (both in flux's own arbitrary FFT-magnitude units, which
 * swing with the music) made the threshold line look like it was
 * jumping around 5-10 while the Sensitivity field next to it read a
 * completely unrelated-looking "3.1". Fixed by transforming to the
 * *same* unit sensitivity is already in: z = (flux - mean) / std. A
 * beat fires when z > sensitivity, so plotting z against a flat line
 * at y = sensitivity is the actual, literal comparison beat_osc.py
 * makes -- the line is now genuinely constant (only moves when the
 * user changes Sensitivity, not every audio tick), and dragging it
 * needs no inverse-math anymore: the y-position the user drops it at
 * *is* the new sensitivity value.
 */
(function () {
  "use strict";

  const WINDOW_S = 30;
  // Keep a few extra seconds of data beyond the visible window before
  // trimming, and pin the x-axis to an explicit min/max every update
  // instead of letting Chart.js auto-range to the data extent. Without
  // this, the line's leftmost point sat exactly on the axis boundary
  // and got dropped the instant it aged out -- visible as the line
  // fraying/unraveling right at the left edge before actually
  // scrolling off, since the axis and the data trim raced each other.
  // The overflow margin means there's always a real point just past
  // the visible edge to clip the drawn line against.
  const BUFFER_S = WINDOW_S + 5;
  const RECONNECT_MS = 1000;

  const statusEl = document.getElementById("status");
  const qlcLink = document.getElementById("qlc-link");
  qlcLink.href = `http://${location.hostname}:9999/`;

  const sensitivityInput = document.getElementById("sensitivity");
  const d1Input = document.getElementById("d1");
  const d2Input = document.getElementById("d2");
  const d3Input = document.getElementById("d3");
  const resetBtn = document.getElementById("reset-defaults-btn");

  let ws = null;
  let draggingBeat = false;
  let draggingIntensity = { d1: false, d2: false, d3: false };
  // Suppress the input's own "change" handler while we're the one
  // writing its value from an incoming config broadcast.
  let applyingRemoteConfig = false;

  const beatData = [];
  const levelData = [];

  function trimOld(arr, latestT) {
    while (arr.length && latestT - arr[0].x > BUFFER_S) arr.shift();
  }

  function pinXAxis(chart, latestT) {
    chart.options.scales.x.min = latestT - WINDOW_S;
    chart.options.scales.x.max = latestT;
  }

  function clamp(v, lo, hi) {
    return Math.min(Math.max(v, lo), hi);
  }

  const beatChart = new Chart(document.getElementById("beatChart"), {
    type: "line",
    data: {
      datasets: [{
        label: "Signal (z-Score)",
        data: beatData,
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
        x: { type: "linear", min: 0, max: WINDOW_S, ticks: { display: false } },
        y: {},
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
              label: { content: "Sensitivity", display: true, position: "end" },
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
        x: { type: "linear", min: 0, max: WINDOW_S, ticks: { display: false } },
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
    // The y-axis IS sensitivity units now -- no inverse-math needed,
    // the dropped position is the value.
    const sensitivity = clamp(ann.yMin, 0.1, 10.0);
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
        const ann = beatChart.options.plugins.annotation.annotations.threshold;
        ann.yMin = cfg.sensitivity;
        ann.yMax = cfg.sensitivity;
        beatChart.update("none");
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

      const [dd1, dd2, dd3] = cfg.default_intensity_thresholds_db;
      resetBtn.title = `Setzt Sensitivity=${cfg.default_sensitivity} und ` +
        `D1/D2/D3=${dd1}/${dd2}/${dd3}`;
    } finally {
      applyingRemoteConfig = false;
    }
  }

  resetBtn.addEventListener("click", () => {
    sendMessage({ type: "reset_to_default" });
  });

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
    // z = (flux - mean) / std -- same unit sensitivity is in, see file
    // header. Only defined once mean/std exist (flux_history's ~1s
    // startup warm-up) and std > 0 (silence -> flat/zero flux history
    // early on); skip the point rather than plot garbage.
    if (m.flux !== null && m.flux !== undefined &&
        m.mean !== null && m.mean !== undefined &&
        m.std !== null && m.std !== undefined && m.std > 0) {
      const z = (m.flux - m.mean) / m.std;
      beatData.push({ x: m.t, y: z });
      trimOld(beatData, m.t);
    }

    levelData.push({ x: m.t, y: m.level_db });
    trimOld(levelData, m.t);

    pinXAxis(beatChart, m.t);
    pinXAxis(intensityChart, m.t);
    beatChart.update("none");
    intensityChart.update("none");
  }

  function setStatus(connected) {
    statusEl.textContent = connected ? "verbunden" : "getrennt";
    statusEl.className = connected ? "connected" : "disconnected";
    const disabled = !connected;
    document.getElementById("beat-controls").dataset.disabled = String(disabled);
    document.getElementById("intensity-controls").dataset.disabled = String(disabled);
    resetBtn.disabled = disabled;
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
