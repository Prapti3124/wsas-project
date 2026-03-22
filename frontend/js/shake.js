/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Shake Detection (shake.js)
   Uses DeviceMotionEvent accelerometer API.
   ═══════════════════════════════════════════════════════════════════════════ */

let shakeEnabled = false;
let lastShakeTime = 0;
let shakeCount = 0;
const SHAKE_THRESHOLD = 15;  // m/s²
const SHAKE_NEEDED = 3;   // Shakes to trigger SOS
const SHAKE_WINDOW = 3000; // ms

function enableShakeDetection() {
  if (shakeEnabled) {
    shakeEnabled = false;
    window.removeEventListener('devicemotion', handleMotion);
    toast('Shake detection disabled.', 'info');
    return;
  }

  // iOS 13+ requires permission
  if (typeof DeviceMotionEvent.requestPermission === 'function') {
    DeviceMotionEvent.requestPermission()
      .then(perm => {
        if (perm === 'granted') attachShakeListener();
        else toast('Motion permission denied.', 'danger');
      });
  } else {
    attachShakeListener();
  }
}

function attachShakeListener() {
  shakeEnabled = true;
  window.addEventListener('devicemotion', handleMotion);
  toast('📳 Shake detection active! Shake 3× to SOS.', 'success');
}

function handleMotion(e) {
  const acc = e.accelerationIncludingGravity;
  if (!acc) return;

  const magnitude = Math.sqrt(acc.x ** 2 + acc.y ** 2 + acc.z ** 2);

  // Update visual bars
  const bx = document.getElementById('barX');
  const by = document.getElementById('barY');
  const bz = document.getElementById('barZ');
  if (bx) bx.style.height = Math.min(Math.abs(acc.x) * 3, 50) + 'px';
  if (by) by.style.height = Math.min(Math.abs(acc.y) * 3, 50) + 'px';
  if (bz) bz.style.height = Math.min(Math.abs(acc.z) * 3, 50) + 'px';

  // Send to AI backend for analysis
  if (Math.random() < 0.1) { // Sample 10% of frames to avoid spam
    api.post('/ai/motion', { x: acc.x, y: acc.y, z: acc.z })
      .then(res => {
        if (res.event === 'fall') {
          toast('⚠️ Fall detected! Triggering SOS...', 'danger');
          setTimeout(() => triggerSOS('fall'), 1000);
        }
      }).catch(() => { });
  }

  // Local shake counter
  if (magnitude > SHAKE_THRESHOLD) {
    const now = Date.now();
    if (now - lastShakeTime > 500) { // Debounce
      shakeCount++;
      lastShakeTime = now;

      if (shakeCount >= SHAKE_NEEDED) {
        shakeCount = 0;
        toast('📳 Shake SOS activated!', 'danger');
        triggerSOS('shake');
      }

      // Reset counter after window
      setTimeout(() => { shakeCount = 0; }, SHAKE_WINDOW);
    }
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Map Module (map.js)
   Uses Leaflet.js (free, no API key needed)
   ═══════════════════════════════════════════════════════════════════════════ */

let leafletMap = null;
let userMarker = null;
let trailLine = null;

async function initMap() {
  if (leafletMap) {
    // Already initialized, just update
    updateMapMarkers();
    return;
  }

  leafletMap = L.map('liveMap', { zoomControl: true });

  // OpenStreetMap tiles (free)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(leafletMap);

  // Center on user location
  if (currentLat && currentLon) {
    leafletMap.setView([currentLat, currentLon], 18);
  } else if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(pos => {
      leafletMap.setView([pos.coords.latitude, pos.coords.longitude], 18);
    }, err => console.warn(err), { enableHighAccuracy: true });
  } else {
    leafletMap.setView([19.0760, 72.8777], 12); // Mumbai fallback
  }

  // Add Recenter button
  const recenterBtn = L.control({ position: 'topright' });
  recenterBtn.onAdd = function () {
    const div = L.DomUtil.create('div', 'leaflet-bar leaflet-control leaflet-control-custom');
    div.style.backgroundColor = 'white';
    div.style.width = '34px';
    div.style.height = '34px';
    div.style.cursor = 'pointer';
    div.style.display = 'flex';
    div.style.alignItems = 'center';
    div.style.justifyContent = 'center';
    div.style.fontSize = '18px';
    div.title = 'Recenter Map';
    div.innerHTML = '🎯';
    div.onclick = function (e) {
      e.stopPropagation();
      e.preventDefault();
      if (currentLat && currentLon && leafletMap) {
        leafletMap.flyTo([currentLat, currentLon], 18);
        toast('📍 Map recentered', 'info');
      } else {
        toast('📍 Waiting for GPS location...', 'warning');
      }
    }
    return div;
  }
  recenterBtn.addTo(leafletMap);

  updateMapMarkers();
  setInterval(updateMapMarkers, 30000); // Refresh every 30s
}

async function updateMapMarkers() {
  if (!leafletMap) return;

  try {
    // User position
    if (currentLat && currentLon) {
      if (!userMarker) {
        userMarker = L.circleMarker([currentLat, currentLon], {
          radius: 10, fillColor: '#00d4aa', color: '#fff', weight: 2, fillOpacity: 0.9
        }).addTo(leafletMap).bindPopup('📍 Your Location');
      } else {
        userMarker.setLatLng([currentLat, currentLon]);
      }
    }

    // Unsafe zones
    const zonesRes = await api.get('/location/unsafe-zones');
    (zonesRes.zones || []).forEach(z => {
      L.circle([z.latitude, z.longitude], {
        radius: z.radius_meters,
        fillColor: '#ef5350', fillOpacity: 0.2, color: '#ef5350', weight: 1
      }).addTo(leafletMap)
        .bindPopup(`⚠️ ${z.name}<br>Crime Score: ${z.crime_score}`);
    });

    // Community reports
    const reportsRes = await api.get('/community/reports');
    (reportsRes.reports || []).forEach(r => {
      const marker = L.circleMarker([r.latitude, r.longitude], {
        radius: 7, fillColor: '#ffa726', color: '#fff', weight: 1, fillOpacity: 0.8
      }).addTo(leafletMap)
        .bindPopup(`⚠️ ${r.category}<br>${r.description || ''}`);
    });

    // Location trail
    const trailRes = await api.get('/location/history');
    const trail = (trailRes.trail || []).map(l => [l.latitude, l.longitude]);
    if (trail.length > 1) {
      if (trailLine) leafletMap.removeLayer(trailLine);
      trailLine = L.polyline(trail, { color: '#42a5f5', weight: 3, opacity: 0.7 }).addTo(leafletMap);
    }

    // AI Hotspots heatmap
    const hotspotsRes = await api.get('/ai/hotspots');
    (hotspotsRes.hotspots || []).forEach(h => {
      L.circleMarker([h.lat, h.lng], {
        radius: h.weight * 5, fillColor: '#e91e8c', color: 'transparent', fillOpacity: 0.3
      }).addTo(leafletMap);
    });

  } catch (e) {
    console.warn('Map update error:', e);
  }
}


/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Analytics Charts (charts.js)
   Uses Chart.js for data visualization
   ═══════════════════════════════════════════════════════════════════════════ */

let alertChartInst = null;
let typeChartInst = null;
let riskChartInst = null;

async function loadAnalytics() {
  try {
    const [histRes, riskRes] = await Promise.all([
      api.get('/alerts/history?limit=100'),
      api.get('/ai/risk-history')
    ]);

    renderAlertChart(histRes.alerts || []);
    renderTypeChart(histRes.alerts || []);
    renderRiskChart(riskRes.history || []);
  } catch (e) {
    console.warn('Analytics error:', e);
  }
}

function renderAlertChart(alerts) {
  // Group alerts by day (last 30 days)
  const days = {};
  for (let i = 29; i >= 0; i--) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    days[d.toLocaleDateString('en-IN')] = 0;
  }
  alerts.forEach(a => {
    const day = new Date(a.created_at).toLocaleDateString('en-IN');
    if (days[day] !== undefined) days[day]++;
  });

  const ctx = document.getElementById('alertChart');
  if (!ctx) return;
  if (alertChartInst) alertChartInst.destroy();

  alertChartInst = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Object.keys(days),
      datasets: [{
        label: 'Alerts',
        data: Object.values(days),
        backgroundColor: 'rgba(233,30,140,0.6)',
        borderColor: '#e91e8c',
        borderRadius: 6
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e8e8f0' } } },
      scales: {
        x: { ticks: { color: '#9090b0', maxRotation: 45 }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: '#9090b0' }, grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });
}

function renderTypeChart(alerts) {
  const types = {};
  alerts.forEach(a => { types[a.alert_type] = (types[a.alert_type] || 0) + 1; });

  const ctx = document.getElementById('typeChart');
  if (!ctx) return;
  if (typeChartInst) typeChartInst.destroy();

  typeChartInst = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: Object.keys(types),
      datasets: [{
        data: Object.values(types),
        backgroundColor: ['#e91e8c', '#ef5350', '#ffa726', '#42a5f5', '#66bb6a', '#ab47bc'],
        borderWidth: 2, borderColor: '#1e1e3a'
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e8e8f0' } } }
    }
  });
}

function renderRiskChart(history) {
  const ctx = document.getElementById('riskChart');
  if (!ctx) return;
  if (riskChartInst) riskChartInst.destroy();

  const labels = history.map(h => new Date(h.computed_at).toLocaleTimeString('en-IN')).reverse();
  const scores = history.map(h => h.score).reverse();

  riskChartInst = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Risk Score',
        data: scores,
        borderColor: '#e91e8c',
        backgroundColor: 'rgba(233,30,140,0.1)',
        fill: true,
        tension: 0.4,
        pointBackgroundColor: '#e91e8c'
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e8e8f0' } } },
      scales: {
        x: { ticks: { color: '#9090b0' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: {
          ticks: { color: '#9090b0' },
          grid: { color: 'rgba(255,255,255,0.05)' },
          min: 0, max: 100
        }
      }
    }
  });
}
