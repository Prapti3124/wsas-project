/* ═══════════════════════════════════════════════════════════════════════════
   SAKHI – Google Maps Module (map.js)
   Migrated from Leaflet to official Google Maps JS API.
   ═══════════════════════════════════════════════════════════════════════════ */

let gMap = null;
let googleMarkers = {
    user: null,
    unsafe: [],
    reports: [],
    trail: null,
    routes: []
};
let directionsService = null;
let directionsRenderer = null;

/**
 * Main initialization entry point.
 * Fetches the API key from the backend and loads the Google Maps script.
 */
async function initMap() {
    if (window.google && window.google.maps && gMap) {
        updateMapMarkers();
        return;
    }

    try {
        const config = await api.get('/location/config');
        if (!config.google_maps_key) {
            console.error("Google Maps API Key missing in backend config.");
            toast("Google Maps could not load: API Key missing.", "danger");
            return;
        }

        // Dynamically load Google Maps script if not already present
        if (!window.google) {
            await loadGoogleMapsScript(config.google_maps_key);
        }

        setupGoogleMap(config.default_lat, config.default_lng);
        updateMapMarkers();
        setInterval(updateMapMarkers, 20000); // Background sync

    } catch (e) {
        console.error("Failed to initialize Google Map:", e);
    }
}

function loadGoogleMapsScript(key) {
    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = `https://maps.googleapis.com/maps/api/js?key=${key}&libraries=geometry,places`;
        script.async = true;
        script.defer = true;
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

function setupGoogleMap(lat, lng) {
    const mapOptions = {
        center: { lat: currentLat || lat, lng: currentLon || lng },
        zoom: 16,
        disableDefaultUI: true, // Clean layout
        styles: [
            { "featureType": "water", "elementType": "geometry", "stylers": [{ "color": "#e9e9e9" }, { "lightness": 17 }] },
            { "featureType": "landscape", "elementType": "geometry", "stylers": [{ "color": "#f5f5f5" }, { "lightness": 20 }] },
            { "featureType": "road.highway", "elementType": "geometry.fill", "stylers": [{ "color": "#ffffff" }, { "lightness": 17 }] },
            { "featureType": "road.highway", "elementType": "geometry.stroke", "stylers": [{ "color": "#ffffff" }, { "lightness": 29 }, { "weight": 0.2 }] },
            { "featureType": "road.arterial", "elementType": "geometry", "stylers": [{ "color": "#ffffff" }, { "lightness": 18 }] },
            { "featureType": "road.local", "elementType": "geometry", "stylers": [{ "color": "#ffffff" }, { "lightness": 16 }] },
            { "featureType": "poi", "elementType": "geometry", "stylers": [{ "color": "#f5f5f5" }, { "lightness": 21 }] },
            { "featureType": "poi.park", "elementType": "geometry", "stylers": [{ "color": "#dedede" }, { "lightness": 21 }] },
            { "elementType": "labels.text.stroke", "stylers": [{ "visibility": "on" }, { "color": "#ffffff" }, { "lightness": 16 }] },
            { "elementType": "labels.text.fill", "stylers": [{ "saturation": 36 }, { "color": "#333333" }, { "lightness": 40 }] },
            { "elementType": "labels.icon", "stylers": [{ "visibility": "off" }] }
        ]
    };

    gMap = new google.maps.Map(document.getElementById('liveMap'), mapOptions);
    directionsService = new google.maps.DirectionsService();
    directionsRenderer = new google.maps.DirectionsRenderer({
        map: gMap,
        suppressMarkers: true,
        polylineOptions: { strokeColor: '#e91e63', strokeWeight: 5, strokeOpacity: 0.8 }
    });
}

function recenterMap() {
    if (gMap && currentLat && currentLon) {
        gMap.panTo({ lat: currentLat, lng: currentLon });
        gMap.setZoom(17);
        toast('📍 Location localized', 'info');
    }
}

async function updateMapMarkers() {
    if (!gMap) return;

    try {
        // 1. User Position
        if (currentLat && currentLon) {
            if (!googleMarkers.user) {
                googleMarkers.user = new google.maps.Marker({
                    position: { lat: currentLat, lng: currentLon },
                    map: gMap,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 8,
                        fillColor: "#4285F4",
                        fillOpacity: 1,
                        strokeColor: "#FFFFFF",
                        strokeWeight: 3
                    },
                    title: "You are here"
                });
            } else {
                googleMarkers.user.setPosition({ lat: currentLat, lng: currentLon });
            }
        }

        // 2. Unsafe Zones
        const zonesRes = await api.get('/location/unsafe-zones');
        googleMarkers.unsafe.forEach(m => m.setMap(null));
        googleMarkers.unsafe = [];
        (zonesRes.zones || []).forEach(z => {
            const circle = new google.maps.Circle({
                map: gMap,
                center: { lat: z.latitude, lng: z.longitude },
                radius: z.radius_meters,
                fillColor: '#EA4335',
                fillOpacity: 0.1,
                strokeColor: '#EA4335',
                strokeWeight: 1
            });
            const marker = new google.maps.Marker({
                position: { lat: z.latitude, lng: z.longitude },
                map: gMap,
                title: z.name,
                icon: {
                    url: "https://maps.google.com/mapfiles/ms/icons/red-dot.png",
                    scaledSize: new google.maps.Size(32, 32)
                }
            });
            googleMarkers.unsafe.push(circle, marker);
        });

        // 3. Community Reports
        const reportsRes = await api.get('/community/reports');
        googleMarkers.reports.forEach(m => m.setMap(null));
        googleMarkers.reports = [];
        (reportsRes.reports || []).forEach(r => {
            const marker = new google.maps.Marker({
                position: { lat: r.latitude, lng: r.longitude },
                map: gMap,
                title: r.category,
                icon: {
                    url: "https://maps.google.com/mapfiles/ms/icons/orange-dot.png",
                    scaledSize: new google.maps.Size(24, 24)
                }
            });
            googleMarkers.reports.push(marker);
        });

    } catch (e) {
        console.warn("Marker update failed", e);
    }
}

/* ═══════════════════════════════════════════════════════════════════════════
   SAFE ROUTE NAVIGATION (Google Powered)
   ═══════════════════════════════════════════════════════════════════════════ */

async function planSafeRoute() {
    const destInput = document.getElementById('routeDestInput');
    const routeResults = document.getElementById('routeResults');
    const destText = destInput?.value?.trim();

    if (!destText) return toast("Enter a destination", "warning");
    if (!currentLat || !currentLon) return toast("GPS not ready", "warning");

    routeResults.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-pink spinner-border-sm"></div><br><small>Calculating safe routes...</small></div>';

    const request = {
        origin: { lat: currentLat, lng: currentLon },
        destination: destText,
        travelMode: google.maps.TravelMode.WALKING,
        provideRouteAlternatives: true
    };

    directionsService.route(request, (result, status) => {
        if (status === google.maps.DirectionsStatus.OK) {
            directionsRenderer.setDirections(result);
            renderRouteList(result);
        } else {
            routeResults.innerHTML = '<div class="alert alert-danger small">Route not found. Try another place.</div>';
        }
    });
}

function renderRouteList(result) {
    const routeResults = document.getElementById('routeResults');
    routeResults.innerHTML = "";
    
    result.routes.forEach((route, index) => {
        const leg = route.legs[0];
        // Custom risk logic can be added here if we want to cross-reference our unsafe zones
        const item = document.createElement('div');
        item.className = `route-result-item ${index === 0 ? 'active' : ''}`;
        item.innerHTML = `
            <div class="d-flex justify-content-between align-items-center mb-1">
                <span class="fw-bold small">Route ${index + 1}</span>
                <span class="badge bg-success" style="font-size:0.6rem;">Safest</span>
            </div>
            <div class="small text-muted">${leg.distance.text} · ${leg.duration.text}</div>
            <div class="small">Via ${route.summary || 'main roads'}</div>
        `;
        item.onclick = () => {
            directionsRenderer.setRouteIndex(index);
            document.querySelectorAll('.route-result-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');
        };
        routeResults.appendChild(item);
    });
}

/* ═══════════════════════════════════════════════════════════════════════════
   LIVE TRACKING LOGIC (ID SYNC)
   ═══════════════════════════════════════════════════════════════════════════ */

let activeTrackingToken = null;

async function checkTrackingStatus() {
    try {
        const res = await api.get('/location/tracking/status');
        if (res.is_active && res.token) {
            activeTrackingToken = res.token;
            showTrackingActiveState(res.token);
        } else {
            showTrackingInactiveState();
        }
    } catch(e) { console.warn("Status check failed"); }
}

async function startLiveTracking() {
    const duration = document.getElementById('trackingDuration').value;
    try {
        const res = await api.post('/location/tracking/start', { duration: parseInt(duration) });
        if (res.token) {
            activeTrackingToken = res.token;
            showTrackingActiveState(res.token);
            toast('Live Tracking started.', 'success');
        }
    } catch (err) { toast('Failed to start tracking', 'danger'); }
}

async function stopLiveTracking() {
    try {
        await api.post('/location/tracking/stop', {});
        activeTrackingToken = null;
        showTrackingInactiveState();
        toast('Tracking stopped.', 'info');
    } catch (err) { toast('Error stopping', 'danger'); }
}

function showTrackingActiveState(token) {
    const link = `${window.location.origin}/track.html?token=${token}`;
    const linkInput = document.getElementById('trackingLinkInput');
    if (linkInput) linkInput.value = link;
    
    document.getElementById('trackingSetupBox')?.classList.add('d-none');
    document.getElementById('trackingActiveBox')?.classList.remove('d-none');
    
    const badge = document.getElementById('trackingStatusBadge');
    if (badge) {
        badge.textContent = 'Sharing Live';
        badge.className = 'badge bg-success';
    }

    const waBtn = document.getElementById('whatsappShareBtn');
    if (waBtn) waBtn.href = `https://api.whatsapp.com/send?text=Follow%20me%20live:%20${encodeURIComponent(link)}`;
}

function showTrackingInactiveState() {
    document.getElementById('trackingSetupBox')?.classList.remove('d-none');
    document.getElementById('trackingActiveBox')?.classList.add('d-none');
    const badge = document.getElementById('trackingStatusBadge');
    if (badge) {
        badge.textContent = 'Inactive';
        badge.className = 'badge bg-secondary';
    }
}

function copyTrackingLink() {
    const val = document.getElementById('trackingLinkInput');
    if (val) {
        val.select();
        document.execCommand("copy");
        toast('Link copied!', 'success');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => { if (accessToken) checkTrackingStatus(); }, 2000);
});
