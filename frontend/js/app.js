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
let currentAcc = null;
let sosHoldTimer = null;

// Persistent Login Check on Load
document.addEventListener('DOMContentLoaded', async () => {
  const savedUser = localStorage.getItem('wsas_user');
  const savedToken = localStorage.getItem('wsas_token');
  const savedRefresh = localStorage.getItem('wsas_refresh');

  if (savedUser && savedToken) {
    try {
      currentUser = JSON.parse(savedUser);
      accessToken = savedToken;
      refreshToken = savedRefresh;
      
      // Optional: Verify token with profile request
      // If it fails, we'll stay on landing/login
      const profile = await api.get('/auth/profile').catch(() => null);
      
      if (profile) {
        currentUser = profile; // Update with latest info
        showSection('dashboard');
        toast('Logged in automatically', 'success');
      } else {
        // Token might be expired, clear and show login
        // logout(); 
      }
    } catch (e) {
      console.error('Auto-login failed:', e);
    }
  }
});

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
let otpEmail = '';

document.getElementById('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const email = document.getElementById('loginEmail').value;
  const password = document.getElementById('loginPassword').value;
  const errEl = document.getElementById('loginError');
  errEl.classList.add('d-none');

  try {
    const res = await api.post('/auth/login', { email, password });
    if (res.access_token) {
      handleAuthSuccess(res);
    } else if (res.needs_verification) {
      startOTPFlow(res.email);
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
    if (res.access_token) {
      handleAuthSuccess(res);
    } else if (res.email) {
      startOTPFlow(res.email);
      toast('OTP sent to your email!', 'info');
    } else {
      if (res.details) {
        showError(errEl, Object.values(res.details).join(' • '));
      } else {
        showError(errEl, res.error || 'Registration failed.');
      }
    }
  } catch (err) {
    showError(errEl, 'Registration failed.');
  }
});

/* ────────────────── GOOGLE AUTH ────────────────────────────────────────── */
async function handleGoogleResponse(response) {
  try {
    const res = await api.post('/auth/google-login', { credential: response.credential });
    if (res.access_token) {
      handleAuthSuccess(res);
    } else if (res.email) {
      startOTPFlow(res.email);
      toast('Verification code sent to your Google email.', 'info');
    } else {
      toast(res.error || 'Google login failed', 'danger');
    }
  } catch (err) {
    toast('Google authentication failed.', 'danger');
  }
}

/* ────────────────── OTP FLOW ───────────────────────────────────────────── */
function startOTPFlow(email) {
  otpEmail = email;
  document.getElementById('otpEmailDisplay').textContent = email;
  showSection('otp-verify');
  
  // Clear previous values
  document.querySelectorAll('.otp-dot').forEach(input => input.value = '');
}

// Auto-focus next OTP input
document.querySelectorAll('.otp-dot').forEach((input, index, inputs) => {
  input.addEventListener('input', () => {
    if (input.value && index < inputs.length - 1) {
      inputs[index + 1].focus();
    }
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && index > 0) {
      inputs[index - 1].focus();
    }
  });
});

document.getElementById('otpForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const dots = document.querySelectorAll('.otp-dot');
  const otp = Array.from(dots).map(d => d.value).join('');
  const errEl = document.getElementById('otpError');
  errEl.classList.add('d-none');

  if (otp.length !== 6) return showError(errEl, 'Please enter all 6 digits');

  try {
    const res = await api.post('/auth/verify-otp', { email: otpEmail, otp });
    if (res.access_token) {
      handleAuthSuccess(res);
      toast('Verification successful!', 'success');
    } else {
      showError(errEl, res.error || 'Verification failed');
    }
  } catch (err) {
    showError(errEl, 'Error verifying OTP');
  }
});

async function resendOTP() {
  if (!otpEmail) return;
  try {
    toast('Resending code...', 'info');
    await api.post('/auth/register', { email: otpEmail, resend: true });
    toast('New code sent!', 'success');
  } catch (e) {
    toast('Failed to resend code.', 'danger');
  }
}

function handleAuthSuccess(res) {
  accessToken = res.access_token;
  refreshToken = res.refresh_token;
  currentUser = res.user;
  localStorage.setItem('wsas_token', accessToken);
  localStorage.setItem('wsas_refresh', refreshToken);
  localStorage.setItem('wsas_user', JSON.stringify(currentUser));
  showSection('dashboard');
  toast('Welcome back, ' + currentUser.name + '! 💙', 'success');
}



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

  // Set basic topbar user display
  if (currentUser) {
    const photo = currentUser.profile_photo || null;
    updateAvatarIcon('userAvatar', currentUser.name[0], photo);
    document.getElementById('userNameDisplay').textContent = currentUser.name;
  }

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
  if (name === 'account') loadProfileTab();
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

/* ────────────────── PROFILE TAB ────────────────────────────────────────── */
async function loadProfileTab() {
  if (!currentUser) return;

  // 1. Basic Info
  document.getElementById('profileName').textContent = currentUser.name;
  document.getElementById('profileEmail').textContent = currentUser.email;
  document.getElementById('profileInfoName').textContent = currentUser.name;
  document.getElementById('profileInfoEmail').textContent = currentUser.email;
  document.getElementById('profileInfoPhone').textContent = currentUser.phone || 'None';
  
  if (currentUser.alternate_phone) {
    document.getElementById('profileInfoAltPhone').textContent = currentUser.alternate_phone;
    document.getElementById('profileInfoAltPhone').classList.remove('text-muted', 'fw-normal', 'fst-italic');
    document.getElementById('profileInfoAltPhone').classList.add('text-light');
  }

  const photo = currentUser.profile_photo || null;
  updateAvatarIcon('profileAvatar', currentUser.name[0], photo);
  updateAvatarIcon('editPhotoPreview', currentUser.name[0], photo);

  // 2. Address Split Logic & Form pre-fill
  const fullAddress = currentUser.address || '';
  document.getElementById('editAddress').value = fullAddress; // for edit mode
  
  if (fullAddress) {
    const parts = fullAddress.split(',').map(s => s.trim());
    document.getElementById('profileAddrStreet').textContent = parts[0] || '-';
    document.getElementById('profileAddrArea').textContent = parts[1] || '-';
    document.getElementById('profileAddrCity').textContent = parts[2] || '-';
    document.getElementById('profileAddrPin').textContent = parts[3] || '-';
    
    document.getElementById('profileCityBadge').textContent = parts[2] ? `${parts[2]}, India` : 'India';
  } else {
    document.getElementById('profileAddrStreet').textContent = 'Not set';
    document.getElementById('profileAddrArea').textContent = '-';
    document.getElementById('profileAddrCity').textContent = '-';
    document.getElementById('profileAddrPin').textContent = '-';
  }

  // 3. Stats & Risk Level
  try {
    const contactsRes = await api.get('/alerts/contacts');
    const alertsRes = await api.get('/alerts/history');
    
    const numContacts = (contactsRes.contacts || []).length;
    const numAlerts = alertsRes.total || 0;
    
    document.getElementById('profileStatContacts').textContent = numContacts;
    document.getElementById('profileStatAlerts').textContent = numAlerts;
    
    // Fallback static counts for reports/score since there's no direct route yet for user totals
    document.getElementById('profileStatReports').textContent = numAlerts > 0 ? 1 : 0; 
    
    // Determine risk level based on score
    const riskBadge = document.getElementById('riskBadge');
    let riskLevel = 'Low Risk';
    let safetyScoreInt = 100;
    
    if (riskBadge && riskBadge.textContent.includes('High')) {
       riskLevel = 'High Risk';
       safetyScoreInt = 35;
    } else if (riskBadge && riskBadge.textContent.includes('Medium')) {
       riskLevel = 'Medium Risk';
       safetyScoreInt = 70;
    }

    document.getElementById('profileStatusRisk').textContent = riskLevel;
    document.getElementById('profileStatScore').textContent = safetyScoreInt;
    document.getElementById('profileStatusScore').textContent = safetyScoreInt;
    document.getElementById('profileStatusBar').style.width = safetyScoreInt + '%';
    
    const label = safetyScoreInt >= 80 ? 'Excellent' : safetyScoreInt >= 50 ? 'Moderate' : 'Critical';
    document.getElementById('profileStatusLabel').textContent = label;

    // Render contacts in the smaller tile format for the profile
    const cList = document.getElementById('profileContactsList');
    if (numContacts === 0) {
      cList.innerHTML = '<p class="text-muted small">No emergency contacts set.</p>';
    } else {
      cList.innerHTML = contactsRes.contacts.map(c => `
        <div class="profile-contact-tile">
          <div class="avatar-circle me-3 flex-shrink-0" style="width:36px;height:36px;font-size:14px;background-color:rgba(233,30,140,0.2);color:#e91e63;">
            ${c.name[0].toUpperCase()}
          </div>
          <div class="flex-grow-1">
            <div class="fw-bold text-light small">${escapeHtml(c.name)}</div>
            <div class="text-muted" style="font-size:0.7rem;">${escapeHtml(c.relation || 'Contact')}</div>
          </div>
          <div class="text-muted small">${escapeHtml(c.phone)}</div>
        </div>
      `).join('');
    }

  } catch (e) {
    console.warn('Failed to load profile stats:', e);
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
      currentAcc = pos.coords.accuracy || 0;
      const acc = currentAcc;

      // Accuracy Warning: If error margin is > 100 meters
      if (acc > 100) {
        toast(`📍 Low GPS accuracy (${Math.round(acc)}m). Move to a clearer area if possible.`, 'warning');
      }

      // Send location to backend every 30s (throttled)
      api.post('/location/update', {
        latitude: currentLat, longitude: currentLon,
        accuracy: acc, speed: pos.coords.speed
      }).catch(() => { });
    },
    err => {
      console.warn('GPS error:', err);
      if (err.code === 1) toast('📍 Location denied. Please enable GPS and allow browser access.', 'warning');
      else if (err.code === 2) toast('📍 Position unavailable. Ensure your GPS is enabled.', 'danger');
      else if (err.code === 3) toast('📍 GPS timeout. Using last known location.', 'info');
    },
    { enableHighAccuracy: true, timeout: 30000, maximumAge: 0 }
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
  const overlay = document.getElementById('sosOverlay');
  const statusEl = document.getElementById('sosStatus');

  overlay.classList.remove('d-none');

  // ── OFFLINE CHECK ────────────────────────────────────────────────────────
  if (!navigator.onLine) {
    triggerOfflineSOS();
    return;
  }

  statusEl.innerHTML = `<span class="badge bg-info"><i class="fas fa-satellite-dish fa-spin me-2"></i>Seeking precise location...</span>`;

  const MAX_GPS_WAIT = 3000;
  let sosSent = false;

  const performSOS = async () => {
    if (sosSent) return;
    sosSent = true;

    try {
      const res = await api.post('/alerts/sos', {
        latitude: currentLat,
        longitude: currentLon,
        accuracy: currentAcc,
        alert_type: type,
        message: 'help me i am in danger.'
      });

      if (res.notified_contacts === 0 && res.errors && res.errors.length > 0) {
        statusEl.innerHTML = `<span class="badge bg-warning text-dark">⚠️ Alert recorded, but SMS/Voice failed</span>`;
        toast(`⚠️ SOS record created, but notification failed.`, 'warning');
      } else {
        const count = res.notified_contacts || 0;
        statusEl.innerHTML = `<span class="badge bg-success">✓ Alert sent to ${count} contacts</span>`;
        toast(`🚨 SOS sent! ${count} contacts notified.`, 'danger');
      }

      setTimeout(() => overlay.classList.add('d-none'), 5000);
    } catch (e) {
      // If the API fails mid-request, try offline SMS as fallback
      console.warn('SOS API failed, trying offline fallback:', e);
      triggerOfflineSOS();
    }
  };

  if (currentLat && currentLon) {
    performSOS();
  } else {
    setTimeout(performSOS, MAX_GPS_WAIT);
  }
}

/**
 * OFFLINE SOS: Opens native SMS app with all cached emergency contacts
 * and the user's GPS coordinates pre-filled in the message body.
 * Also queues the SOS in localStorage for background sync replay.
 */
function triggerOfflineSOS() {
  const overlay  = document.getElementById('sosOverlay');
  const statusEl = document.getElementById('sosStatus');

  overlay.classList.remove('d-none');

  // Build location string
  let locationStr = '⚠️ Location unavailable';
  let mapsUrl     = '';
  if (currentLat && currentLon) {
    const lat7 = currentLat.toFixed(7);
    const lon7 = currentLon.toFixed(7);
    mapsUrl     = `https://maps.google.com/?q=${lat7},${lon7}`;
    locationStr = mapsUrl;
  }

  const now     = new Date();
  const timeStr = now.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  const userName = currentUser?.name || 'SAKHI User';
  const smsBody = `🆘 SOS! ${userName} is in danger!\nLocation: ${locationStr}\nTime: ${timeStr}\nMsg: help me i am in danger.`;

  // Load cached contacts
  const cachedContacts = getCachedContacts();

  if (cachedContacts.length > 0) {
    // Build multi-recipient SMS URI (works natively on Android/iOS)
    const phones = cachedContacts.map(c => c.phone).join(';');
    const smsUri = `sms:${phones}?body=${encodeURIComponent(smsBody)}`;
    window.open(smsUri, '_blank');
    statusEl.innerHTML = `
      <div class="offline-sos-state">
        <i class="fas fa-mobile-alt fa-2x mb-2"></i>
        <div class="fw-bold">📴 OFFLINE – SMS App Opened</div>
        <div class="small opacity-75 mt-1">Send the pre-filled message to ${cachedContacts.length} contact${cachedContacts.length > 1 ? 's' : ''}</div>
      </div>`;
    toast('📴 Offline SOS: SMS app opened with pre-filled message!', 'warning');
  } else {
    // No cached contacts – provide direct call option
    statusEl.innerHTML = `
      <div class="offline-sos-state">
        <i class="fas fa-exclamation-circle fa-2x mb-2"></i>
        <div class="fw-bold">📴 OFFLINE – No cached contacts</div>
        <div class="small opacity-75 mt-1">Please call emergency services directly</div>
        <a href="tel:112" class="btn btn-light btn-sm mt-2">📞 Call 112</a>
      </div>`;
    toast('📴 Offline – No cached contacts. Call 112!', 'danger');
  }

  // Queue the SOS for background sync when connection returns
  queueOfflineAlert({ lat: currentLat, lon: currentLon, time: now.toISOString(), user: userName });

  setTimeout(() => overlay.classList.add('d-none'), 10000);
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

    // ── Cache contacts for offline SOS ──────────────────────────────────────
    cacheContactsLocally(contacts);

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

/* ────────────────── OFFLINE SOS HELPERS ─────────────────────────────────── */
/**
 * Persist emergency contacts to localStorage so they are available when offline.
 */
function cacheContactsLocally(contacts) {
  try {
    localStorage.setItem('wsas_offline_contacts', JSON.stringify(contacts));
  } catch (e) {
    console.warn('Failed to cache contacts:', e);
  }
}

/**
 * Retrieve the cached contacts list.
 */
function getCachedContacts() {
  try {
    return JSON.parse(localStorage.getItem('wsas_offline_contacts') || '[]');
  } catch {
    return [];
  }
}

/**
 * Store a pending SOS alert in localStorage for background sync replay.
 */
function queueOfflineAlert(data) {
  try {
    const queue = JSON.parse(localStorage.getItem('wsas_pending_sos') || '[]');
    queue.push(data);
    localStorage.setItem('wsas_pending_sos', JSON.stringify(queue));
    // Register background sync if supported
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
      navigator.serviceWorker.ready.then(reg => {
        reg.sync.register('sos-pending').catch(err => console.warn('Sync reg failed:', err));
      });
    }
  } catch (e) {
    console.warn('Failed to queue offline alert:', e);
  }
}

/**
 * Replay any queued offline SOS alerts once connectivity is restored.
 * Called automatically on the 'online' event.
 */
async function replayQueuedAlerts() {
  const queue = JSON.parse(localStorage.getItem('wsas_pending_sos') || '[]');
  if (!queue.length) return;

  toast(`🔄 Replaying ${queue.length} offline alert(s)...`, 'info');
  const remaining = [];

  for (const item of queue) {
    try {
      await api.post('/alerts/sos', {
        latitude:   item.lat,
        longitude:  item.lon,
        alert_type: 'offline_sos',
        message:    `[OFFLINE SOS – queued at ${item.time}] help me i am in danger.`
      });
      toast('✅ Queued offline SOS sent!', 'success');
    } catch (e) {
      remaining.push(item); // keep for next attempt
    }
  }

  localStorage.setItem('wsas_pending_sos', JSON.stringify(remaining));
}

// Show/hide offline banner and replay queued alerts on connectivity change
window.addEventListener('online',  () => {
  document.getElementById('offlineBanner')?.classList.add('d-none');
  toast('🌐 Back online!', 'success');
  replayQueuedAlerts();
});
window.addEventListener('offline', () => {
  document.getElementById('offlineBanner')?.classList.remove('d-none');
  toast('📴 No internet connection. Offline SOS is ready.', 'warning');
});

// Show banner immediately if already offline on load
document.addEventListener('DOMContentLoaded', () => {
  if (!navigator.onLine) {
    document.getElementById('offlineBanner')?.classList.remove('d-none');
  }
});

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
            ${a.latitude ? `<a href="https://www.google.com/maps/search/?api=1&query=${a.latitude},${a.longitude}" 
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
  localStorage.removeItem('wsas_token');
  localStorage.removeItem('wsas_refresh');
  localStorage.removeItem('wsas_user');
  accessToken = null;
  refreshToken = null;
  currentUser = null;
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
