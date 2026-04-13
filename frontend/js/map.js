/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Map Module (map.js)
   Uses Leaflet.js. Adds Safe Route Navigation feature.
   ═══════════════════════════════════════════════════════════════════════════ */

let leafletMap = null;
let userMarker = null;
let routeLayers = []; // Active route polylines for cleanup

// Layer Groups for Toggling
const layers = {
  unsafe: L.layerGroup(),
  reports: L.layerGroup(),
  trail: L.layerGroup(),
  hotspots: L.layerGroup(),
  pos: L.layerGroup(),
  routes: L.layerGroup()
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

  const labels = {
    unsafe: 'High Risk Zones',
    reports: 'Community Reports',
    trail: 'Tracking Trail',
    pos: 'Current Position',
    routes: 'Safe Routes'
  };

  const isHiding = leafletMap.hasLayer(layers[type]);
  const layerSize = layers[type].getLayers().length;

  if (isHiding) {
    leafletMap.removeLayer(layers[type]);
    el.classList.add('legend-hidden');
    toast(`🙈 Hidden: ${labels[type] || type}`, 'info');
  } else {
    leafletMap.addLayer(layers[type]);
    el.classList.remove('legend-hidden');

    if (layerSize === 0 && type !== 'pos') {
      toast(`ℹ️ ${labels[type] || type} layer is active, but has no data yet.`, 'warning');
    } else {
      toast(`👁️ Showing: ${labels[type] || type}`, 'success');
    }
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


/* ═══════════════════════════════════════════════════════════════════════════
   SAFE ROUTE NAVIGATION
   ═══════════════════════════════════════════════════════════════════════════ */

const ROUTE_COLORS = {
  low:    { color: '#00e676', dashArray: null,     weight: 6 },   // green – safest
  medium: { color: '#ffa726', dashArray: '8, 8',   weight: 5 },   // amber – caution
  high:   { color: '#ff1744', dashArray: '6, 10',  weight: 5 },   // red – avoid
};

/**
 * Geocode an address string using Nominatim (free, no key required).
 * Returns { lat, lon, display_name } or null.
 */
async function geocodeAddress(address) {
  try {
    const encoded = encodeURIComponent(address);
    const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encoded}&limit=1`;
    const res = await fetch(url, { headers: { 'Accept-Language': 'en', 'User-Agent': 'SAKHI-SafetyApp' } });
    const data = await res.json();
    if (data && data.length > 0) {
      return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon), display_name: data[0].display_name };
    }
  } catch (e) {
    console.warn('Geocoding failed:', e);
  }
  return null;
}

/**
 * Main route planner triggered by the UI "Plan Safe Route" button.
 */
async function planSafeRoute() {
  const destInput = document.getElementById('routeDestInput');
  const routeResults = document.getElementById('routeResults');
  const planBtn = document.getElementById('planRouteBtn');

  const destText = destInput?.value?.trim();
  if (!destText) {
    toast('Please enter a destination address.', 'warning');
    return;
  }
  if (!currentLat || !currentLon) {
    toast('📍 GPS not ready. Enable location access and wait a moment.', 'warning');
    return;
  }

  // Show loading state
  planBtn.disabled = true;
  planBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Planning...';
  routeResults.innerHTML = `
    <div class="text-center py-3">
      <div class="spinner-border text-pink" style="width: 1.5rem; height: 1.5rem;"></div>
      <div class="text-muted small mt-2">Geocoding destination & fetching safe routes...</div>
    </div>`;

  try {
    // 1. Geocode the destination
    const dest = await geocodeAddress(destText);
    if (!dest) {
      routeResults.innerHTML = `<div class="text-danger small mt-2">❌ Could not find that address. Try a more specific location.</div>`;
      return;
    }

    // 2. Place destination marker
    layers.routes.clearLayers();
    L.marker([dest.lat, dest.lon], {
      icon: L.divIcon({
        className: '',
        html: '<div style="background:#e91e8c;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-size:1rem;box-shadow:0 2px 8px rgba(0,0,0,0.5)">🏁</div>',
        iconAnchor: [16, 16]
      })
    }).addTo(layers.routes).bindPopup(`<b>Destination</b><br>${dest.display_name}`).openPopup();

    // 3. Call backend for scored routes
    const res = await api.post('/location/safe-route', {
      origin_lat: currentLat, origin_lon: currentLon,
      dest_lat: dest.lat,    dest_lon: dest.lon
    });

    if (res.error) {
      routeResults.innerHTML = `<div class="text-warning small mt-2">⚠️ ${res.error}</div>`;
      return;
    }

    const routes = res.routes || [];
    if (!routes.length) {
      routeResults.innerHTML = `<div class="text-muted small mt-2">No routes found.</div>`;
      return;
    }

    // Helper to format minutes into a human-readable string (Xh Ym)
    const formatDuration = (min) => {
      const h = Math.floor(min / 60);
      const m = Math.round(min % 60);
      return h > 0 ? `${h}h ${m}m` : `${m} min`;
    };

    // Helper to get icon & label for profile
    const getModeInfo = (profile) => {
      const map = {
        'walking': { icon: 'fa-walking', label: 'Walking' },
        'driving': { icon: 'fa-car',     label: 'Driving' },
        'bus':     { icon: 'fa-bus',     label: 'Bus' },
        'train':   { icon: 'fa-train',   label: 'Train' },
        'plane':   { icon: 'fa-plane',   label: 'Flight' }
      };
      return map[profile] || { icon: 'fa-route', label: profile };
    };

    // 4. Draw routes on map
    routes.forEach((route, idx) => {
      const style = ROUTE_COLORS[route.risk_level] || ROUTE_COLORS.medium;
      const latlngs = route.geometry; 
      const mode = getModeInfo(route.profile);
      const duration = formatDuration(route.duration_min);

      const polyline = L.polyline(latlngs, {
        color: style.color,
        weight: idx === 0 ? style.weight + 2 : style.weight,
        opacity: idx === 0 ? 1 : 0.55,
        dashArray: idx === 0 ? null : style.dashArray
      }).addTo(layers.routes);

      polyline.bindPopup(`
        <b>${route.label}</b><br>
        <i class="fas ${mode.icon} me-1"></i> ${mode.label}<br>
        📏 ${route.distance_km} km &nbsp;|&nbsp; ⏱ ${duration}<br>
        🛡️ Safety: ${100 - route.risk_score}/100
      `);

      if (idx === 0) polyline.openPopup();
    });

    // Fit map
    if (routes[0]?.geometry?.length) {
      const allPoints = routes.flatMap(r => r.geometry);
      leafletMap.fitBounds(L.latLngBounds(allPoints), { padding: [40, 40] });
    }

    // 5. Render route cards
    const safetyBadge = (level, score) => {
      const color = level === 'low' ? '#00e676' : level === 'medium' ? '#ffa726' : '#ff1744';
      const label = level === 'low' ? 'Safe' : level === 'medium' ? 'Moderate Risk' : 'High Risk';
      return `<span style="background:${color}20;color:${color};border:1px solid ${color}40;
        border-radius:20px;padding:2px 10px;font-size:0.75rem;font-weight:600;">${label} (${Number(score).toFixed(1)}/100)</span>`;
    };

    routeResults.innerHTML = `
      <div class="route-results-header">
        <i class="fas fa-route text-pink me-2"></i>
        <span class="fw-bold">${routes.length} Option${routes.length > 1 ? 's' : ''} to ${dest.display_name.split(',')[0]}</span>
      </div>
      ${routes.map((r, i) => {
        const mode = getModeInfo(r.profile);
        const duration = formatDuration(r.duration_min);
        return `
        <div class="route-card ${i === 0 ? 'route-card-recommended' : ''}" onclick="focusRoute(${i})">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <div>
              <div class="fw-semibold small">${r.label}</div>
              <div class="text-muted" style="font-size:0.75rem;">
                <i class="fas ${mode.icon} me-1" style="width:14px; text-align:center;"></i> ${mode.label} &nbsp;·&nbsp;
                📏 ${r.distance_km} km &nbsp;·&nbsp; ⏱ ${duration}
              </div>
            </div>
            ${safetyBadge(r.risk_level, r.risk_score)}
          </div>
          ${i === 0 ? '<div class="route-recommended-badge"><i class="fas fa-shield-alt me-1"></i>SAFEST OPTION</div>' : ''}
        </div>`;
      }).join('')}`;

    // Store routes for focus function
    window._plannedRoutes = routes;

  } catch (err) {
    console.error('Route planning error:', err);
    routeResults.innerHTML = `<div class="text-danger small mt-2">❌ Route planning failed. Check connection.</div>`;
  } finally {
    planBtn.disabled = false;
    planBtn.innerHTML = '<i class="fas fa-route me-2"></i>Plan Safe Route';
  }
}

/**
 * Pan map to focus on a specific route when its card is clicked.
 */
function focusRoute(idx) {
  if (!leafletMap || !window._plannedRoutes || !window._plannedRoutes[idx]) return;
  const route = window._plannedRoutes[idx];
  if (route.geometry && route.geometry.length) {
    leafletMap.fitBounds(L.latLngBounds(route.geometry), { padding: [40, 40] });
  }
}

/**
 * Clear all planned routes from the map and reset the UI.
 */
function clearRoutes() {
  layers.routes.clearLayers();
  window._plannedRoutes = null;
  const routeResults = document.getElementById('routeResults');
  if (routeResults) routeResults.innerHTML = '';
  const destInput = document.getElementById('routeDestInput');
  if (destInput) destInput.value = '';
  toast('Routes cleared.', 'info');
}

/* ═══════════════════════════════════════════════════════════════════════════
   LIVE LOCATION SHARING (FOLLOW ME)
   ═══════════════════════════════════════════════════════════════════════════ */

let activeTrackingToken = null;

async function checkTrackingStatus() {
  try {
    const res = await api.get('/location/tracking/status');
    if (res.is_active && res.token) {
      activeTrackingToken = res.token;
      showTrackingActiveState(res.token);
      
      // Force an immediate location update to ensure the public viewer has data
      if (currentLat && currentLon) {
        api.post('/location/update', { 
            latitude: currentLat, longitude: currentLon, 
            accuracy: currentAcc, speed: 0 
        }).catch(() => {});
      }
    } else {
      showTrackingInactiveState();
    }
  } catch(e) { console.warn("Failed to check tracking status"); }
}

async function startLiveTracking() {
  const duration = document.getElementById('trackingDuration').value;
  document.getElementById('trackingStatusBadge').textContent = 'Starting...';
  document.getElementById('trackingStatusBadge').className = 'badge bg-warning text-dark';
  
  try {
    const res = await api.post('/location/tracking/start', { duration: parseInt(duration) });
    console.log('Tracking Start Response:', res);
    
    if (res.token) {
      activeTrackingToken = res.token;
      showTrackingActiveState(res.token);
      toast('Live Tracking started successfully.', 'success');
      
      // Force an immediate location update so data is available for anyone opening the link instantly
      if (currentLat && currentLon) {
        await api.post('/location/update', { 
            latitude: currentLat, longitude: currentLon, 
            accuracy: currentAcc, speed: 0 
        }).catch(() => {});
      }

      if (!watchId) startGPS();
    } else {
      console.error('Tracking Error:', res.error);
      toast('Error starting tracking: ' + (res.error || 'Unknown error'), 'danger');
      showTrackingInactiveState();
    }
  } catch (err) {
    console.error('Tracking Network Error:', err);
    toast('Network error starting tracking.', 'danger');
    showTrackingInactiveState();
  }
}

async function stopLiveTracking() {
  document.getElementById('trackingStatusBadge').textContent = 'Stopping...';
  try {
    await api.post('/location/tracking/stop', {});
    activeTrackingToken = null;
    showTrackingInactiveState();
    toast('Live Tracking stopped. Your location is no longer shared.', 'info');
  } catch (err) {
    toast('Error stopping tracking.', 'danger');
  }
}

function showTrackingActiveState(token) {
  // Add a cache-busting timestamp to force laptop browsers to reload the fresh link
  const link = `${window.location.origin}/track.html?token=${token}&ts=${Date.now()}`;
  document.getElementById('trackingLinkInput').value = link;
  
  document.getElementById('trackingSetupBox').classList.add('d-none');
  document.getElementById('trackingActiveBox').classList.remove('d-none');
  
  document.getElementById('trackingStatusBadge').textContent = 'Live & Sharing';
  document.getElementById('trackingStatusBadge').className = 'badge bg-success pulse';

  // Setup WhatsApp link
  const waBtn = document.getElementById('whatsappShareBtn');
  waBtn.href = `https://api.whatsapp.com/send?text=Follow%20my%20live%20location%20on%20SAKHI%20safely:%20${encodeURIComponent(link)}`;
}

function showTrackingInactiveState() {
  document.getElementById('trackingSetupBox').classList.remove('d-none');
  document.getElementById('trackingActiveBox').classList.add('d-none');
  
  document.getElementById('trackingStatusBadge').textContent = 'Inactive';
  document.getElementById('trackingStatusBadge').className = 'badge bg-secondary';
}

function copyTrackingLink() {
  const val = document.getElementById('trackingLinkInput');
  val.select();
  document.execCommand("copy");
  toast('Tracking link copied to clipboard!', 'success');
}

// Hook it into the Map Load logic if we're entering Map Tab
document.addEventListener('DOMContentLoaded', () => {
    // Only verify status once on load if logged in
    setTimeout(() => { if (accessToken) checkTrackingStatus(); }, 2000);
});
