/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Admin Dashboard Logic (admin.js)
   ═══════════════════════════════════════════════════════════════════════════ */

// -- Utility Functions --
function toast(msg, type = 'info') {
    const el = document.getElementById('toastMsg');
    const container = document.getElementById('liveToast');
    
    // reset colors
    container.className = 'toast align-items-center text-white border-0';
    container.classList.add('bg-' + type);
    
    el.innerHTML = msg;
    const bsToast = new bootstrap.Toast(container, { delay: 3000 });
    bsToast.show();
}

function showAdminSection(id) {
    // Hide all sections
    document.querySelectorAll('.admin-section').forEach(el => el.classList.add('d-none'));
    
    // Show target section
    document.getElementById('section-' + id).classList.remove('d-none');
    
    // Update topbar title
    const titles = {
        'dashboard': 'Overview',
        'users': 'User Management',
        'zones': 'Unsafe Zones',
        'reports': 'Community Reports'
    };
    if (document.getElementById('tabTitle')) {
        document.getElementById('tabTitle').textContent = titles[id];
    }
    
    // Manage sidebar active states
    document.querySelectorAll('.sidebar-nav a').forEach(el => el.classList.remove('active'));
    const activeLink = document.getElementById('nav-' + id);
    if (activeLink) activeLink.classList.add('active');
    
    // Refresh data depending on section
    if (id === 'dashboard') loadDashboardStats();
    if (id === 'users') loadUsers();
    if (id === 'zones') {
        loadZones();
        setTimeout(() => { if (adminMap) adminMap.invalidateSize(); }, 200);
    }
    if (id === 'reports') loadReports();
    
    // Mobile sidebar toggle fix
    const sidebar = document.getElementById('sidebar');
    if (sidebar && sidebar.classList.contains('active')) {
        sidebar.classList.remove('active');
    }
}

/* ────────────────── 1. DASHBOARD & CHARTS ──────────────────────────────── */
let chartInstance = null;

async function loadDashboardStats() {
    try {
        const stats = await api.get('/admin/dashboard');
        document.getElementById('statTotalUsers').textContent = stats.users.total;
        document.getElementById('statTotalAlerts').textContent = stats.alerts.total;
        document.getElementById('statUnverifiedReports').textContent = stats.community_reports.unverified;
        document.getElementById('statUnsafeZones').textContent = stats.unsafe_zones;
        
        loadAlertAnalytics();
        loadRecentAlerts();
    } catch (e) {
        toast("Failed to load dashboard stats", "danger");
    }
}

async function loadRecentAlerts() {
    const tbody = document.getElementById('recentAlertsBody');
    if (!tbody) return;
    try {
        const data = await api.get('/admin/alerts?limit=10');
        if (!data.alerts || data.alerts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3 text-muted">No alerts yet.</td></tr>`;
            return;
        }
        tbody.innerHTML = data.alerts.map(a => {
            const time = new Date(a.created_at).toLocaleString('en-IN');
            const statusClass = a.status === 'active' ? 'danger' : a.status === 'resolved' ? 'success' : 'secondary';
            const riskClass   = a.risk_score >= 70 ? 'danger' : a.risk_score >= 40 ? 'warning' : 'success';
            return `<tr>
                <td><span class="fw-bold">${escHtml(a.user_name)}</span><br><small class="text-muted">${escHtml(a.user_email)}</small></td>
                <td><span class="badge bg-secondary">${a.alert_type}</span></td>
                <td><small>${escHtml(a.message || '-')}</small></td>
                <td><span class="badge bg-${riskClass}">${Math.round(a.risk_score)}</span></td>
                <td><span class="badge bg-${statusClass}">${a.status}</span></td>
                <td><small class="text-muted">${time}</small></td>
            </tr>`;
        }).join('');
    } catch (e) {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center py-3 text-muted">Could not load alerts.</td></tr>`;
        console.error('Failed to load recent alerts:', e);
    }
}

function escHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function loadAlertAnalytics() {
    try {
        const data = await api.get('/admin/analytics/alerts');
        const days = data.daily_alerts.reverse(); // Reverse to get oldest to newest
        
        const labels = days.map(d => d.date.substring(5)); // just MM-DD
        const counts = days.map(d => d.count);
        
        const ctx = document.getElementById('alertsChart').getContext('2d');
        
        if (chartInstance) {
            chartInstance.destroy();
        }
        
        chartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Daily Alerts',
                    data: counts,
                    borderColor: '#e91e63',
                    backgroundColor: 'rgba(233, 30, 99, 0.2)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#aaa', stepSize: 1 } },
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#aaa', maxTicksLimit: 10 } }
                }
            }
        });
    } catch (e) {
        console.error("Failed to load analytics", e);
    }
}

/* ────────────────── 2. USERS ───────────────────────────────────────────── */
async function loadUsers() {
    try {
        const data = await api.get('/admin/users');
        const tbody = document.getElementById('usersTableBody');
        tbody.innerHTML = '';
        
        if (data.users.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">No users found.</td></tr>`;
            return;
        }
        
        data.users.forEach(u => {
            const statusBadge = u.is_active 
                ? `<span class="badge bg-success">Active</span>` 
                : `<span class="badge bg-danger">Disabled</span>`;
            
            const actionBtn = u.is_active
                ? `<button class="btn btn-sm btn-outline-danger" onclick="toggleUser(${u.id}, false)">Disable</button>`
                : `<button class="btn btn-sm btn-outline-success" onclick="toggleUser(${u.id}, true)">Enable</button>`;
                
            tbody.innerHTML += `
                <tr>
                    <td>#${u.id}</td>
                    <td class="fw-bold">${u.name}</td>
                    <td>${u.email}</td>
                    <td>${statusBadge}</td>
                    <td>${actionBtn}</td>
                </tr>
            `;
        });
    } catch (e) {
        toast("Failed to load users", "danger");
    }
}

async function toggleUser(id, enable) {
    try {
        await api.put(`/admin/users/${id}/toggle`, {});
        toast(`User successfully ${enable ? 'enabled' : 'disabled'}`, 'success');
        loadUsers(); // refresh
    } catch (e) {
        toast("Failed to update user status", "danger");
    }
}

/* ────────────────── 3. UNSAFE ZONES ────────────────────────────────────── */
let adminMap = null;
let currentZonesLayer = null;
let newZoneMarker = null;

function initAdminMap() {
    if (adminMap) return;
    
    adminMap = L.map('adminMap', {
        zoomControl: false,
        attributionControl: false
    }).setView([19.0760, 72.8777], 11); // Mumbai default
    
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19
    }).addTo(adminMap);
    
    currentZonesLayer = L.layerGroup().addTo(adminMap);
    
    // Map click to add zone
    adminMap.on('click', function(e) {
        const lat = e.latlng.lat;
        const lon = e.latlng.lng;
        
        document.getElementById('zoneLat').value = lat;
        document.getElementById('zoneLon').value = lon;
        document.getElementById('zoneCoords').value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
        document.getElementById('btnSaveZone').disabled = false;
        
        if (newZoneMarker) adminMap.removeLayer(newZoneMarker);
        
        newZoneMarker = L.marker([lat, lon], {
            icon: L.divIcon({
                className: 'custom-div-icon',
                html: `<div style="background-color:#ff1744;width:14px;height:14px;border-radius:50%;border:2px solid white;box-shadow:0 0 10px #ff1744;"></div>`,
                iconSize: [14, 14],
                iconAnchor: [7, 7]
            })
        }).addTo(adminMap);
    });
}

async function loadZones() {
    initAdminMap();
    try {
        const data = await api.get('/location/unsafe-zones');
        currentZonesLayer.clearLayers();
        
        data.zones.forEach(z => {
            const circle = L.circle([z.latitude, z.longitude], {
                color: '#ff1744',
                fillColor: '#ff1744',
                fillOpacity: 0.2,
                weight: 1,
                radius: z.radius_meters
            }).addTo(currentZonesLayer);
            
            circle.bindPopup(`
                <div class="text-dark">
                    <h6 class="fw-bold mb-1">${z.name}</h6>
                    <div class="small mb-2">Score: ${z.crime_score}/100</div>
                    <button class="btn btn-sm btn-danger py-0 px-2" onclick="deleteZone(${z.id})">Delete Zone</button>
                </div>
            `);
        });
    } catch (e) {
        console.error("Failed to load zones", e);
    }
}

document.getElementById('addZoneForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const payload = {
        name: document.getElementById('zoneName').value,
        latitude: document.getElementById('zoneLat').value,
        longitude: document.getElementById('zoneLon').value,
        crime_score: document.getElementById('zoneScore').value,
        radius_meters: document.getElementById('zoneRadius').value,
        category: "general"
    };
    
    try {
        const btn = document.getElementById('btnSaveZone');
        btn.disabled = true;
        btn.innerHTML = 'Saving...';
        
        await api.post('/admin/unsafe-zones', payload);
        toast("Unsafe Zone added successfully!", "success");
        
        // Reset form
        document.getElementById('addZoneForm').reset();
        document.getElementById('zoneCoords').value = '';
        if (newZoneMarker) adminMap.removeLayer(newZoneMarker);
        btn.innerHTML = 'Save Zone';
        
        loadZones(); // Refresh
    } catch (err) {
        toast("Failed to add zone", "danger");
        document.getElementById('btnSaveZone').disabled = false;
        document.getElementById('btnSaveZone').innerHTML = 'Save Zone';
    }
});

async function deleteZone(id) {
    if (!confirm('Are you sure you want to delete this unsafe zone?')) return;
    try {
        await api.delete(`/admin/unsafe-zones/${id}`);
        toast("Zone deleted.", "info");
        adminMap.closePopup();
        loadZones();
    } catch (e) {
        toast("Failed to delete zone", "danger");
    }
}

/* ────────────────── 4. REPORTS ─────────────────────────────────────────── */
async function loadReports() {
    try {
        const data = await api.get('/admin/reports');
        const tbody = document.getElementById('reportsTableBody');
        tbody.innerHTML = '';
        
        if (data.reports.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4 text-muted">No reports found.</td></tr>`;
            return;
        }
        
        data.reports.forEach(r => {
            const dateStr = new Date(r.created_at).toLocaleString();
            const statusBadge = r.verified 
                ? `<span class="badge bg-success"><i class="fas fa-check-circle me-1"></i>Verified</span>` 
                : `<span class="badge bg-warning text-dark"><i class="fas fa-clock me-1"></i>Pending</span>`;
            
            const actionBtn = r.verified
                ? `<button class="btn btn-sm btn-outline-secondary" disabled>Verified</button>`
                : `<button class="btn btn-sm btn-outline-success" onclick="verifyReport(${r.id})">Verify</button>`;
                
            tbody.innerHTML += `
                <tr>
                    <td class="small text-muted">${dateStr}</td>
                    <td class="fw-bold">${r.category}</td>
                    <td><div class="text-truncate" style="max-width: 200px;" title="${r.description}">${r.description}</div></td>
                    <td><span class="badge bg-danger">Level ${r.severity}</span></td>
                    <td>${statusBadge}</td>
                    <td>${actionBtn}</td>
                </tr>
            `;
        });
    } catch (e) {
        toast("Failed to load reports", "danger");
    }
}

async function verifyReport(id) {
    try {
        await api.put(`/admin/reports/${id}/verify`, {});
        toast(`Report verified! It will now affect routing safety scores.`, 'success');
        loadReports();
    } catch (e) {
        toast("Failed to verify report", "danger");
    }
}

// Initialize
window.onload = () => {
    // Start on dashboard
    loadDashboardStats();
};
