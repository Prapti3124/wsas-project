/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Map Module (map.js)
   Uses Leaflet.js
   ═══════════════════════════════════════════════════════════════════════════ */

let leafletMap = null;
let userMarker = null;

// Layer Groups for Toggling
const layers = {
  unsafe: L.layerGroup(),
  reports: L.layerGroup(),
  trail: L.layerGroup(),
  hotspots: L.layerGroup(),
  pos: L.layerGroup()
};

async function initMap() {
  if (leafletMap) {
    updateMapMarkers();
    return;
  }

  // Dark Map Theme if preferred, but sticking to standard OSM for reliability
  leafletMap = L.map('liveMap', { zoomControl: false });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors',
    maxZoom: 19
  }).addTo(leafletMap);

  // Add all layers to map by default
  Object.values(layers).forEach(layer => layer.addTo(leafletMap));

  // Initial View
  if (currentLat && currentLon) {
    leafletMap.setView([currentLat, currentLon], 16);
  } else {
    leafletMap.setView([19.0760, 72.8777], 12); // Mumbai fallback
  }

  updateMapMarkers();
  setInterval(updateMapMarkers, 15000); // Faster refresh
}

function recenterMap() {
  if (currentLat && currentLon && leafletMap) {
    leafletMap.flyTo([currentLat, currentLon], 17, { duration: 1.5 });
    toast('📍 Map recentered', 'info');
  } else {
    toast('📍 Searching for GPS...', 'warning');
  }
}

function toggleMapLayer(type, el) {
  if (!leafletMap || !layers[type]) return;

  if (leafletMap.hasLayer(layers[type])) {
    leafletMap.removeLayer(layers[type]);
    el.classList.add('legend-hidden');
  } else {
    leafletMap.addLayer(layers[type]);
    el.classList.remove('legend-hidden');
  }
}

async function updateMapMarkers() {
  if (!leafletMap) return;

  try {
    // 1. Current Position
    if (currentLat && currentLon) {
      layers.pos.clearLayers();
      userMarker = L.circleMarker([currentLat, currentLon], {
        radius: 10, fillColor: '#00d4aa', color: '#fff', weight: 3, fillOpacity: 0.9
      }).addTo(layers.pos).bindPopup('<b>You are here</b><br>Live tracking active.');
    }

    // 2. Unsafe Zones
    const zonesRes = await api.get('/location/unsafe-zones');
    layers.unsafe.clearLayers();
    (zonesRes.zones || []).forEach(z => {
      L.circle([z.latitude, z.longitude], {
        radius: z.radius_meters,
        fillColor: '#ff1744', fillOpacity: 0.25, color: '#ff1744', weight: 1
      }).addTo(layers.unsafe).bindPopup(`<b>⚠️ ${z.name}</b><br>Risk Score: ${z.crime_score}`);
    });

    // 3. Community Reports
    const reportsRes = await api.get('/community/reports');
    layers.reports.clearLayers();
    (reportsRes.reports || []).forEach(r => {
      L.circleMarker([r.latitude, r.longitude], {
        radius: 8, fillColor: '#ff9100', color: '#fff', weight: 2, fillOpacity: 0.9
      }).addTo(layers.reports).bindPopup(`<b>Community Alert: ${r.category}</b><br>${r.description || 'No details provided'}`);
    });

    // 4. Trail
    const trailRes = await api.get('/location/history');
    const trail = (trailRes.trail || []).map(l => [l.latitude, l.longitude]);
    layers.trail.clearLayers();
    if (trail.length > 1) {
      L.polyline(trail, { color: '#2979ff', weight: 4, opacity: 0.6, dashArray: '5, 10' }).addTo(layers.trail);
    }

    // 5. Hotspots
    const hotspotsRes = await api.get('/ai/hotspots');
    layers.hotspots.clearLayers();
    (hotspotsRes.hotspots || []).forEach(h => {
      L.circleMarker([h.lat, h.lng], {
        radius: h.weight * 6, fillColor: '#e91e63', color: 'transparent', fillOpacity: 0.35
      }).addTo(layers.hotspots);
    });

  } catch (e) {
    console.warn('Map sync failed:', e);
  }
}
