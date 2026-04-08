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



