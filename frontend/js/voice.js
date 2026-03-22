/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Voice SOS Module (voice.js)
   Uses Browser SpeechRecognition API for keyword detection.
   No external API needed — runs entirely client-side.
   ═══════════════════════════════════════════════════════════════════════════ */

let recognition       = null;
let isListening       = false;
let voiceSOSTriggered = false;

// Keywords that trigger automatic SOS
const TRIGGER_KEYWORDS = ['help me', 'help', 'sos', 'emergency', 'save me', 'danger', 'bachao'];

function toggleVoiceDetection() {
  if (isListening) {
    stopVoiceDetection();
  } else {
    startVoiceDetection();
  }
}

function startVoiceDetection() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    toast('Voice recognition not supported in this browser. Use Chrome/Edge.', 'warning');
    return;
  }

  recognition = new SpeechRecognition();
  recognition.continuous    = true;   // Keep listening
  recognition.interimResults = true;  // Process partial results
  recognition.lang           = 'en-IN';
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    isListening = true;
    voiceSOSTriggered = false;
    updateVoiceUI(true);
    toast('🎤 Voice SOS active. Say "Help Me" to send alert.', 'info');
  };

  recognition.onresult = (event) => {
    let transcript = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      transcript += event.results[i][0].transcript.toLowerCase();
    }

    // Check for trigger keywords
    const detected = TRIGGER_KEYWORDS.find(kw => transcript.includes(kw));
    if (detected && !voiceSOSTriggered) {
      voiceSOSTriggered = true; // Prevent duplicate triggers
      handleVoiceTrigger(transcript, detected);
    }
  };

  recognition.onerror = (event) => {
    console.warn('Speech recognition error:', event.error);
    if (event.error !== 'no-speech') {
      toast('Voice recognition error: ' + event.error, 'warning');
    }
    // Restart on error (for continuous monitoring)
    if (event.error === 'no-speech' || event.error === 'audio-capture') {
      setTimeout(() => { if (isListening) recognition.start(); }, 1000);
    }
  };

  recognition.onend = () => {
    // Auto-restart for continuous listening
    if (isListening) {
      setTimeout(() => {
        try { recognition.start(); } catch (_) {}
      }, 500);
    }
  };

  try {
    recognition.start();
  } catch (e) {
    toast('Could not start microphone. Allow mic permission.', 'danger');
  }
}

function stopVoiceDetection() {
  isListening = false;
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  updateVoiceUI(false);
  toast('Voice detection disabled.', 'info');
}

function handleVoiceTrigger(transcript, keyword) {
  toast(`🎤 Keyword detected: "${keyword}" — Triggering SOS!`, 'danger');
  
  // Visual feedback
  const statusEl = document.getElementById('voiceStatus');
  if (statusEl) {
    statusEl.innerHTML = `
      <i class="fas fa-microphone fa-2x" style="color:#ef5350;animation:voice-pulse 0.5s infinite"></i>
      <p class="mt-2" style="color:#ef5350">🚨 KEYWORD DETECTED! SOS ACTIVATING...</p>
    `;
  }

  // Trigger SOS after 2s (allows cancellation)
  setTimeout(() => {
    triggerSOS('voice');
    voiceSOSTriggered = false; // Reset for next use
  }, 2000);
}

function updateVoiceUI(active) {
  const btn    = document.getElementById('voiceToggle');
  const status = document.getElementById('voiceStatus');
  
  if (btn) {
    btn.innerHTML = active
      ? '<i class="fas fa-microphone-slash me-2"></i>Disable Voice SOS'
      : '<i class="fas fa-microphone me-2"></i>Enable Voice SOS';
    btn.style.background = active ? '#ef5350' : '';
  }
  
  if (status) {
    status.innerHTML = active
      ? `<i class="fas fa-microphone fa-2x text-pink voice-active"></i>
         <p class="mt-2 text-success">🎤 Listening for keywords...</p>
         <small class="text-muted">Say: "Help Me", "SOS", "Emergency"</small>`
      : `<i class="fas fa-microphone-slash text-muted fa-2x"></i>
         <p class="mt-2 text-muted">Voice detection inactive</p>`;
  }
}
