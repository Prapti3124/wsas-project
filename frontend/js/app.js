/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Main App Logic
   Handles: Navigation, SOS, contacts, alerts, community, analytics
   ═══════════════════════════════════════════════════════════════════════════ */

let deferredPrompt;
const installBtns = [document.getElementById('heroInstallBtn'), document.getElementById('sidebarInstallBtn')];

// Listen for the PWA install prompt
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  // Show all install buttons if they meet native criteria
  installBtns.forEach(btn => {
    if (btn) {
      btn.classList.remove('d-none');
      btn.innerHTML = '<i class="fas fa-download me-2"></i>Install App';
    }
  });
});

// Fallback: If prompt doesn't fire after 3s, show a "How to Install" guide instead
// especially for iOS Safari which never fires beforeinstallprompt
setTimeout(() => {
  if (!deferredPrompt) {
    installBtns.forEach(btn => {
      if (btn) {
        btn.classList.remove('d-none');
        btn.classList.replace('btn-success', 'btn-outline-info');
        btn.innerHTML = '<i class="fas fa-info-circle me-2"></i>How to Install';
        btn.onclick = () => toast('To install: Use your browser menu and look for "Install app" or "Add to Home Screen"', 'info');
      }
    });
  }
}, 3000);

// Handle the install button click
async function triggerInstall(btn) {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  console.log(`User response to install prompt: ${outcome}`);
  deferredPrompt = null;
  // Hide all install buttons
  installBtns.forEach(btn => btn?.classList.add('d-none'));
}

// Add event listeners to install buttons after DOM loads
document.addEventListener('DOMContentLoaded', () => {
  installBtns.forEach(btn => {
    btn?.addEventListener('click', () => triggerInstall(btn));
  });
});

let currentUser = null;
let accessToken = null;
let refreshToken = null;
let currentLat = null;
let currentLon = null;
let sosHoldTimer = null;

/* ────────────────── SECTION NAVIGATION ─────────────────────────────────── */
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// Close sidebar when clicking outside on mobile
document.addEventListener('click', (e) => {
  const sidebar = document.getElementById('sidebar');
  const toggleBtn = document.querySelector('[onclick="toggleSidebar()"]');
  if (window.innerWidth <= 768 && sidebar && sidebar.classList.contains('open')) {
    if (!sidebar.contains(e.target) && (!toggleBtn || !toggleBtn.contains(e.target))) {
      sidebar.classList.remove('open');
    }
  }
});

function showSection(name) {
  document.querySelectorAll('section').forEach(s => s.classList.add('d-none'));
  const target = document.getElementById(name);
  if (target) {
    target.classList.remove('d-none');
  }

  const nav = document.querySelector('.wsas-nav');
  if (name === 'dashboard') {
    if (nav) nav.classList.add('d-none');
    initDashboard();
  } else {
    if (nav) nav.classList.remove('d-none');
  }
}

/* ────────────────── AUTH ────────────────────────────────────────────────── */
document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('loginEmail').value;
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  errEl.classList.add('d-none');

  try {
    const res = await api.post('/auth/login', { email, password });
    if (res.access_token) {
      accessToken = res.access_token;
      refreshToken = res.refresh_token;
      currentUser = res.user;
      localStorage.setItem('wsas_token', accessToken);
      localStorage.setItem('wsas_refresh', refreshToken);
      localStorage.setItem('wsas_user', JSON.stringify(currentUser));
      showSection('dashboard');
      toast('Welcome back, ' + currentUser.name + '! 💙', 'success');
    } else {
      showError(errEl, res.error || 'Login failed');
    }
  } catch (err) {
    showError(errEl, 'Network error. Check your connection.');
  }
});

document.getElementById('registerForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const errEl = document.getElementById('registerError');
  errEl.classList.add('d-none');
  const body = {
    name: document.getElementById('regName').value,
    email: document.getElementById('regEmail').value,
    password: document.getElementById('regPassword').value,
    phone: document.getElementById('regPhone').value,
  };
  try {
    const res = await api.post('/auth/register', body);
    if (res.user) {
      toast('Account created! Please login.', 'success');
      showSection('login');
    } else {
      showError(errEl, JSON.stringify(res.details || res.error));
    }
  } catch (err) {
    showError(errEl, 'Registration failed.');
  }
});

/* ────────────────── PROFILE EDITING ──────────────────────────────────────── */
let profileImageBase64 = null;

function updateAvatarIcon(id, initial, photoUrl) {
  const el = document.getElementById(id);
  if (!el) return;
  if (photoUrl) {
    el.innerHTML = `<img src="${photoUrl}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
  } else {
    el.textContent = initial.toUpperCase();
  }
}

function toggleProfileEdit() {
  const viewMode = document.getElementById('profileViewMode');
  const editMode = document.getElementById('profileEditMode');
  if (viewMode.classList.contains('d-none')) {
    viewMode.classList.remove('d-none');
    editMode.classList.add('d-none');
  } else {
    viewMode.classList.add('d-none');
    editMode.classList.remove('d-none');
    document.getElementById('editName').value = currentUser.name || '';
    document.getElementById('editPhone').value = currentUser.phone || '';
    document.getElementById('editAltPhone').value = currentUser.alternate_phone || '';
    document.getElementById('editAddress').value = currentUser.address || '';
    document.getElementById('editProfileStatus').className = 'd-none';
    profileImageBase64 = null;
    updateAvatarIcon('editPhotoPreview', currentUser.name[0], currentUser.profile_photo || null);
  }
}

document.getElementById('editPhoto')?.addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (ev) => {
    profileImageBase64 = ev.target.result;
    updateAvatarIcon('editPhotoPreview', 'U', profileImageBase64);
  };
  reader.readAsDataURL(file);
});

document.getElementById('profileEditForm')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const statusEl = document.getElementById('editProfileStatus');
  statusEl.className = 'd-none text-center small mb-3';

  const payload = {
    name: document.getElementById('editName').value,
    phone: document.getElementById('editPhone').value,
    alternate_phone: document.getElementById('editAltPhone').value,
    address: document.getElementById('editAddress').value,
    profile_photo: profileImageBase64 || currentUser.profile_photo
  };

  try {
    statusEl.textContent = "Saving...";
    statusEl.className = 'text-info text-center small mb-3';

    const res = await api.put('/auth/profile', payload);
    if (res.user) {
      toast('Profile updated successfully!', 'success');
      currentUser = res.user;
      localStorage.setItem('wsas_user', JSON.stringify(currentUser));
      initDashboard(); // Re-render Logic
      toggleProfileEdit(); // Go back to view mode
    } else {
      showError(statusEl, res.error || 'Failed to update profile');
    }
  } catch (err) {
    showError(statusEl, 'Network error saving profile');
  }
});

/* ────────────────── INIT DASHBOARD ─────────────────────────────────────── */
function initDashboard() {
  // Restore session
  if (!accessToken) {
    accessToken = localStorage.getItem('wsas_token');
    refreshToken = localStorage.getItem('wsas_refresh');
    const saved = localStorage.getItem('wsas_user');
    if (saved) currentUser = JSON.parse(saved);
  }

  if (!accessToken || !currentUser) {
    showSection('login');
    return;
  }

  // Set user display
  const pName = document.getElementById('profileName');
  if (pName) {
    pName.textContent = currentUser.name;
    document.getElementById('profileEmail').textContent = currentUser.email;
    document.getElementById('profilePhone').textContent = currentUser.phone || 'No phone set';
    document.getElementById('profileAltPhone').textContent = currentUser.alternate_phone || 'None';
    document.getElementById('profileAddress').textContent = currentUser.address || 'None';

    const photo = currentUser.profile_photo || null;
    updateAvatarIcon('profileAvatar', currentUser.name[0], photo);
    updateAvatarIcon('userAvatar', currentUser.name[0], photo);
    updateAvatarIcon('editPhotoPreview', currentUser.name[0], photo);
  }
  document.getElementById('userNameDisplay').textContent = currentUser.name;

  // Start clock
  setInterval(updateClock, 1000);
  updateClock();

  // Start GPS
  startGPS();

  // Load initial data
  loadDashboardStats();
  refreshRiskScore();

  // Auto-refresh risk score every 2 minutes
  setInterval(refreshRiskScore, 120000);

  loadTab('home');
}

function updateClock() {
  const now = new Date();
  document.getElementById('currentTime').textContent =
    now.toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' })
    + ' — ' + now.toLocaleTimeString('en-IN');
}

/* ────────────────── TAB LOADING ─────────────────────────────────────────── */
function loadTab(name) {
  document.querySelectorAll('[id^="tab-"]').forEach(el => el.classList.add('d-none'));
  const tab = document.getElementById('tab-' + name);
  if (tab) {
    tab.classList.remove('d-none');
    tab.classList.add('tab-enter');
  }
  document.getElementById('tabTitle').textContent = {
    home: 'Dashboard', map: 'Live Map', contacts: 'Emergency Contacts',
    chatbot: 'AI Safety Assistant', alerts: 'Alert History',
    community: 'Community Reports', analytics: 'Analytics',
    account: 'My Profile'
  }[name] || name;

  // Update sidebar active state
  document.querySelectorAll('.sidebar-nav a').forEach(a => a.classList.remove('active'));

  // Close sidebar automatically on mobile
  if (window.innerWidth <= 768) {
    const sb = document.getElementById('sidebar');
    if (sb) sb.classList.remove('open');
  }

  // Load tab-specific data
  if (name === 'contacts') loadContacts();
  if (name === 'alerts') loadAlerts();
  if (name === 'map') initMap();
  if (name === 'community') loadCommunity();
  if (name === 'analytics') loadAnalytics();
}

/* ────────────────── DASHBOARD STATS ────────────────────────────────────── */
async function loadDashboardStats() {
  try {
    const [alertsRes, contactsRes, zonesRes] = await Promise.all([
      api.get('/alerts/history?limit=1'),
      api.get('/alerts/contacts'),
      api.get('/location/unsafe-zones')
    ]);
    document.getElementById('stat-alerts').textContent = alertsRes.total || 0;
    document.getElementById('stat-contacts').textContent = (contactsRes.contacts || []).length;
    document.getElementById('stat-zones').textContent = (zonesRes.zones || []).length;
  } catch (e) {
    console.warn('Stats load error:', e);
  }
}

/* ────────────────── GPS ─────────────────────────────────────────────────── */
function startGPS() {
  if (!navigator.geolocation) {
    toast('📍 Geolocation is not supported by your browser.', 'danger');
    return;
  }
  navigator.geolocation.watchPosition(
    pos => {
      currentLat = pos.coords.latitude;
      currentLon = pos.coords.longitude;
      // Send location to backend every 30s (throttled)
      api.post('/location/update', {
        latitude: currentLat, longitude: currentLon,
        accuracy: pos.coords.accuracy, speed: pos.coords.speed
      }).catch(() => { });
    },
    err => {
      console.warn('GPS error:', err);
      if (err.code === 1) toast('📍 Location denied. Please enable GPS and allow browser access.', 'warning');
      else if (err.code === 2) toast('📍 Position unavailable. Ensure your GPS is enabled.', 'danger');
      else if (err.code === 3) toast('📍 GPS timeout. Using last known location.', 'info');

      if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
        toast('📍 Note: Accurate location on mobile requires HTTPS (e.g., via ngrok).', 'warning');
      }
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
  );
}

/* ────────────────── RISK SCORE ──────────────────────────────────────────── */
async function refreshRiskScore() {
  try {
    const res = await api.post('/ai/risk-score', {
      latitude: currentLat, longitude: currentLon
    });
    const score = res.score;
    const level = res.level;

    document.getElementById('gaugeScore').textContent = score;
    document.getElementById('gaugeLabel').textContent = level.toUpperCase();
    document.getElementById('stat-risk').textContent = level.charAt(0).toUpperCase() + level.slice(1);
    document.getElementById('riskLevel').textContent = level.toUpperCase();

    // Color the risk badge
    const badge = document.getElementById('riskBadge');
    badge.style.borderColor = level === 'high' ? '#ef5350' : level === 'medium' ? '#ffa726' : '#00d4aa';

    // Animate gauge
    const gaugeFill = document.getElementById('gaugeFill');
    const deg = Math.round((score / 100) * 180);
    gaugeFill.style.setProperty('--fill', deg + 'deg');
    gaugeFill.style.background = `conic-gradient(
      ${level === 'high' ? '#ef5350' : level === 'medium' ? '#ffa726' : '#00d4aa'} 0deg ${deg}deg,
      rgba(255,255,255,0.1) ${deg}deg 180deg
    )`;

    // Render factors
    if (res.factors) {
      const f = res.factors;
      document.getElementById('riskFactors').innerHTML = `
        <div class="risk-factor-row"><span>Time of day</span><span>${f.time}/100</span></div>
        <div class="factor-bar mb-2"><div class="factor-fill" style="width:${f.time}%"></div></div>
        <div class="risk-factor-row"><span>Location</span><span>${f.location}/100</span></div>
        <div class="factor-bar mb-2"><div class="factor-fill" style="width:${f.location}%"></div></div>
        <div class="risk-factor-row"><span>Community reports</span><span>${f.community}/100</span></div>
        <div class="factor-bar"><div class="factor-fill" style="width:${f.community}%"></div></div>
      `;
    }

    // Auto-alert if high risk
    if (level === 'high') {
      toast('⚠️ High risk area detected! Consider alerting contacts.', 'warning');
    }
  } catch (e) {
    console.warn('Risk score error:', e);
  }
}

/* ────────────────── SOS ─────────────────────────────────────────────────── */
async function triggerSOS(type = 'manual') {
  document.getElementById('sosOverlay').classList.remove('d-none');

  try {
    const res = await api.post('/alerts/sos', {
      latitude: currentLat,
      longitude: currentLon,
      alert_type: type,
      message: 'help me i am in danger.'
    });

    if (res.notified_contacts === 0 && res.errors && res.errors.length > 0) {
      document.getElementById('sosStatus').innerHTML =
        `<span class="badge bg-warning text-dark">⚠️ Alert recorded, but SMS/Voice failed</span>`;
      toast(`⚠️ SOS recorded! Twilio error: ${res.errors[0]}`, 'warning');
    } else {
      document.getElementById('sosStatus').innerHTML =
        `<span class="badge bg-success">✓ Alert sent to ${res.notified_contacts} contacts</span>`;
      toast(`🚨 SOS sent! ${res.notified_contacts} contacts notified.`, 'danger');
    }

    setTimeout(() => {
      document.getElementById('sosOverlay').classList.add('d-none');
    }, 5000);
  } catch (e) {
    document.getElementById('sosOverlay').classList.add('d-none');
    toast('SOS failed. Please call 112 directly.', 'danger');
  }
}

function cancelSOS() {
  document.getElementById('sosOverlay').classList.add('d-none');
  toast('SOS cancelled.', 'info');
}

/* ────────────────── CONTACTS ─────────────────────────────────────────────── */
async function loadContacts() {
  const el = document.getElementById('contactList');
  el.innerHTML = '<div class="text-muted text-center py-3">Loading...</div>';
  try {
    const res = await api.get('/alerts/contacts');
    const contacts = res.contacts || [];
    if (!contacts.length) {
      el.innerHTML = '<p class="text-muted text-center">No contacts yet. Add emergency contacts to receive SOS alerts.</p>';
      return;
    }
    el.innerHTML = contacts.map(c => `
      <div class="contact-card">
        <div class="d-flex align-items-center gap-3">
          <div class="contact-avatar">${c.name[0].toUpperCase()}</div>
          <div>
            <div class="fw-bold">${escapeHtml(c.name)}</div>
            <small class="text-muted">${escapeHtml(c.phone)} · ${escapeHtml(c.relation || 'Contact')}</small>
          </div>
        </div>
        <button class="btn btn-sm btn-outline-danger" onclick="deleteContact(${c.id})">
          <i class="fas fa-trash"></i>
        </button>
      </div>
    `).join('');
    document.getElementById('stat-contacts').textContent = contacts.length;
  } catch (e) {
    el.innerHTML = '<p class="text-danger text-center">Failed to load contacts.</p>';
  }
}

async function addContact() {
  const name = document.getElementById('contactName').value.trim();
  const code = document.getElementById('countryCode').value;
  let rawPhone = document.getElementById('contactPhone').value.trim();
  const relation = document.getElementById('contactRelation').value.trim();
  if (!name || !rawPhone) return toast('Name and phone are required.', 'warning');

  // Format the phone number dynamically and strip all whitespace
  let phone = (rawPhone.startsWith('+') ? rawPhone : code + rawPhone.replace(/^0+/, '')).replace(/\s+/g, '');

  try {
    await api.post('/alerts/contacts', { name, phone, relation });
    bootstrap.Modal.getInstance(document.getElementById('addContactModal')).hide();
    document.getElementById('contactName').value = '';
    document.getElementById('contactPhone').value = '';
    loadContacts();
    toast('Contact added successfully!', 'success');
  } catch (e) {
    toast('Failed to add contact.', 'danger');
  }
}

async function deleteContact(id) {
  if (!confirm('Remove this emergency contact?')) return;
  await api.delete('/alerts/contacts/' + id);
  loadContacts();
  toast('Contact removed.', 'info');
}

/* ────────────────── ALERTS ──────────────────────────────────────────────── */
async function loadAlerts() {
  const el = document.getElementById('alertList');
  el.innerHTML = '<div class="text-muted text-center">Loading...</div>';
  try {
    const res = await api.get('/alerts/history?limit=20');
    const alerts = res.alerts || [];
    if (!alerts.length) {
      el.innerHTML = '<p class="text-muted text-center">No alerts yet. Stay safe!</p>';
      return;
    }
    el.innerHTML = alerts.map(a => `
      <div class="alert-item">
        <div>
          <span class="alert-badge-type">${a.alert_type}</span>
          <span class="ms-2 text-muted small">${new Date(a.created_at).toLocaleString('en-IN')}</span>
          <div class="mt-1 small">${escapeHtml(a.message || '')}
            ${a.latitude ? `<a href="https://maps.google.com/?q=${a.latitude},${a.longitude}" 
              target="_blank" class="ms-2 text-pink">📍 View map</a>` : ''}
          </div>
        </div>
        <div class="text-end">
          <span class="badge ${a.status === 'active' ? 'bg-danger' : a.status === 'resolved' ? 'bg-success' : 'bg-secondary'}">
            ${a.status}
          </span>
          <div class="small text-muted mt-1">Risk: ${a.risk_score}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = '<p class="text-danger">Failed to load alerts.</p>';
  }
}

/* ────────────────── CHATBOT ─────────────────────────────────────────────── */
async function sendChat() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  appendChatMsg(msg, 'user');

  // Show typing indicator
  const typingId = appendChatMsg('⋯ typing...', 'bot', true);

  try {
    const res = await api.post('/chatbot/message', {
      message: msg,
      lat: currentLat,
      lon: currentLon
    });
    document.getElementById('msg-' + typingId)?.remove();
    appendChatMsg(res.response, 'bot', false, res.is_html || false);

    // Auto-trigger SOS if chatbot detects emergency
    if (res.trigger_sos) {
      setTimeout(() => triggerSOS('chatbot'), 1500);
    }
  } catch (e) {
    document.getElementById('msg-' + typingId)?.remove();
    appendChatMsg('Sorry, I could not process your message. Please try again.', 'bot');
  }
}

let chatMsgId = 0;
function appendChatMsg(text, role, isTemp = false, isHtml = false) {
  const id = ++chatMsgId;
  const el = document.createElement('div');
  el.className = `chat-msg ${role}`;
  el.id = 'msg-' + id;
  el.innerHTML = `<div class="msg-bubble">${isHtml ? text : escapeHtml(text)}</div>`;
  const container = document.getElementById('chatMessages');
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return id;
}

/* ────────────────── COMMUNITY ───────────────────────────────────────────── */
async function submitReport() {
  if (!currentLat) return toast('GPS location required to submit a report.', 'warning');
  const body = {
    latitude: currentLat,
    longitude: currentLon,
    category: document.getElementById('reportCategory').value,
    severity: parseInt(document.getElementById('reportSeverity').value),
    description: document.getElementById('reportDesc').value
  };
  try {
    await api.post('/community/report', body);
    toast('Report submitted! Thank you for keeping the community safe.', 'success');
    document.getElementById('reportDesc').value = '';
    loadCommunity();
  } catch (e) {
    toast('Failed to submit report.', 'danger');
  }
}

async function loadCommunity() {
  const el = document.getElementById('communityList');
  el.innerHTML = '<div class="text-muted text-center">Loading...</div>';
  try {
    const res = await api.get('/community/reports');
    const reports = res.reports || [];
    if (!reports.length) {
      el.innerHTML = '<p class="text-muted text-center">No recent reports. Area looks safe!</p>';
      return;
    }
    el.innerHTML = reports.map(r => `
      <div class="report-card">
        <div class="d-flex justify-content-between">
          <strong>${r.category}</strong>
          <span class="text-muted small">${new Date(r.created_at).toLocaleDateString('en-IN')}</span>
        </div>
        <div class="text-muted small mt-1">${escapeHtml(r.description || 'No description')} — Severity: ${'⭐'.repeat(r.severity)}</div>
      </div>
    `).join('');
  } catch (e) {
    el.innerHTML = '<p class="text-danger">Failed to load reports.</p>';
  }
}

/* ────────────────── LOGOUT ──────────────────────────────────────────────── */
function logout() {
  localStorage.clear();
  accessToken = null; currentUser = null;
  showSection('hero');
  toast('Logged out successfully.', 'info');
}

/* ────────────────── UTILITIES ───────────────────────────────────────────── */
function togglePw(id) {
  const el = document.getElementById(id);
  el.type = el.type === 'password' ? 'text' : 'password';
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove('d-none');
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function toast(msg, type = 'info') {
  const colors = {
    success: '#00d4aa', danger: '#ef5350', warning: '#ffa726', info: '#42a5f5'
  };
  const el = document.createElement('div');
  el.className = 'wsas-toast';
  el.style.borderLeftColor = colors[type] || colors.info;
  el.innerHTML = `<div style="color:${colors[type]}">${msg}</div>`;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 4000);
}

/* ────────────────── AUTO-LOGIN ON PAGE LOAD ─────────────────────────────── */
window.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('wsas_token');
  const user = localStorage.getItem('wsas_user');
  if (token && user) {
    accessToken = token;
    refreshToken = localStorage.getItem('wsas_refresh');
    currentUser = JSON.parse(user);
    showSection('dashboard');
  } else {
    showSection('hero');
  }
});
