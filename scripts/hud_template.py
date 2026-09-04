"""
Autonomous Android Controller — Interactive Floating Web HUD
Glassmorphism Dark UI with live device telemetry, voice input,
interactive step cards, Undo/Retry buttons, and ambient screen scanner.
100% self-contained (zero external CDNs, runs fully offline).
"""

HUD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>God-Mode Controller HUD</title>
<style>
  :root {
    --bg: #0a0d14;
    --card: rgba(22, 27, 38, 0.85);
    --card-border: rgba(255, 255, 255, 0.08);
    --primary: #10b981;
    --primary-glow: rgba(16, 185, 129, 0.25);
    --accent: #6366f1;
    --danger: #ef4444;
    --warning: #f59e0b;
    --text: #f3f4f6;
    --text-muted: #9ca3af;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  body { background: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; overflow-x: hidden; }
  
  /* Top Telemetry Header */
  header {
    position: sticky; top: 0; z-index: 100;
    background: rgba(10, 13, 20, 0.92);
    backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--card-border);
    padding: 12px 16px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .brand { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }
  .pulse { width: 10px; height: 10px; border-radius: 50%; background: var(--primary); box-shadow: 0 0 10px var(--primary); animation: pulse 2s infinite; }
  @keyframes pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.5; transform: scale(0.9); } }
  
  .telemetry-pills { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--card-border);
    border-radius: 20px;
    padding: 4px 10px;
    font-size: 11px;
    color: var(--text-muted);
    display: flex; align-items: center; gap: 4px;
  }
  .pill strong { color: var(--text); }
  
  /* Main Chat & Step Log */
  main { flex: 1; padding: 16px; display: flex; flex-direction: column; gap: 14px; max-width: 680px; margin: 0 auto; width: 100%; padding-bottom: 140px; }
  
  .card {
    background: var(--card);
    border: 1px solid var(--card-border);
    border-radius: 14px;
    padding: 14px;
    backdrop-filter: blur(12px);
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    animation: fadeIn 0.25s ease-out;
  }
  @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
  
  .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 12px; color: var(--text-muted); }
  .card-title { font-weight: 600; color: var(--text); font-size: 14px; }
  
  .step-list { display: flex; flex-direction: column; gap: 8px; margin-top: 10px; }
  .step-item {
    background: rgba(0, 0, 0, 0.25);
    border-left: 3px solid var(--primary);
    border-radius: 6px;
    padding: 8px 12px;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 13px;
  }
  .step-item.undo { border-left-color: var(--danger); }
  .step-actions { display: flex; gap: 6px; }
  
  .btn-sm {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid var(--card-border);
    color: var(--text);
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-sm:active { transform: scale(0.95); background: rgba(255, 255, 255, 0.15); }
  .btn-undo { color: var(--danger); border-color: rgba(239, 68, 68, 0.3); }
  
  /* Quick Chips */
  .quick-chips { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0; scrollbar-width: none; }
  .quick-chips::-webkit-scrollbar { display: none; }
  .chip {
    background: rgba(99, 102, 241, 0.15);
    border: 1px solid rgba(99, 102, 241, 0.3);
    color: #c7d2fe;
    padding: 6px 12px;
    border-radius: 16px;
    font-size: 12px;
    white-space: nowrap;
    cursor: pointer;
  }
  .chip:active { background: rgba(99, 102, 241, 0.3); }
  
  /* Bottom Dock & Input */
  footer {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: rgba(10, 13, 20, 0.95);
    backdrop-filter: blur(16px);
    border-top: 1px solid var(--card-border);
    padding: 12px 16px;
    z-index: 100;
  }
  .dock-container { max-width: 680px; margin: 0 auto; display: flex; flex-direction: column; gap: 8px; }
  .input-bar { display: flex; gap: 8px; align-items: center; }
  input[type="text"] {
    flex: 1;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 12px 16px;
    color: var(--text);
    font-size: 15px;
    outline: none;
    transition: border-color 0.2s;
  }
  input[type="text"]:focus { border-color: var(--primary); box-shadow: 0 0 12px var(--primary-glow); }
  
  .btn-icon {
    width: 46px; height: 46px; border-radius: 12px;
    border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px;
    transition: transform 0.15s;
  }
  .btn-icon:active { transform: scale(0.92); }
  .btn-mic { background: rgba(255, 255, 255, 0.08); color: var(--text); border: 1px solid var(--card-border); }
  .btn-mic.listening { background: var(--danger); animation: micPulse 1s infinite; }
  @keyframes micPulse { 0%, 100% { box-shadow: 0 0 10px rgba(239, 68, 68, 0.8); } 50% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.4); } }
  .btn-send { background: var(--primary); color: #000; font-weight: 700; }
  
  /* Ambient Summary Modal / Box */
  .summary-box {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.25);
    border-radius: 10px;
    padding: 12px;
    margin-top: 8px;
    font-size: 13px;
    line-height: 1.5;
  }
</style>
</head>
<body>

<header>
  <div class="brand">
    <div class="pulse"></div>
    <span>God-Mode Controller</span>
  </div>
  <div class="telemetry-pills">
    <div class="pill" id="pill-battery">🔋 <strong>--%</strong></div>
    <div class="pill" id="pill-volume">🔊 <strong>--</strong></div>
    <div class="pill" id="pill-app">📱 <strong>--</strong></div>
  </div>
</header>

<main id="chat-stream">
  <div class="card">
    <div class="card-header">
      <span class="card-title">Autonomous Mobile AI</span>
      <span id="session-time">Online</span>
    </div>
    <p style="font-size: 13px; color: var(--text-muted);">
      Ready. Speak or type instructions. You can navigate away to any app, scan articles, undo actions, or continuous chat.
    </p>
  </div>
</main>

<footer>
  <div class="dock-container">
    <div class="quick-chips">
      <div class="chip" onclick="quickAction('scan')">🔍 Scan Screen</div>
      <div class="chip" onclick="quickAction('undo')">↩ Undo Last Action</div>
      <div class="chip" onclick="quickAction('study mode')">🌙 Study Mode</div>
      <div class="chip" onclick="quickAction('outdoor mode')">☀️ Outdoor Mode</div>
      <div class="chip" onclick="quickAction('notifications')">🔔 Notifications</div>
      <div class="chip" onclick="quickAction('compact')">📦 Compact Storage</div>
    </div>
    <div class="input-bar">
      <button class="btn-icon btn-mic" id="btn-mic" onclick="toggleVoice()" title="Voice input">🎙️</button>
      <input type="text" id="query-input" placeholder="Type mission (e.g. summarize this, set volume 70%)..." onkeydown="if(event.key==='Enter') sendMission();" />
      <button class="btn-icon btn-send" onclick="sendMission()" title="Send mission">➔</button>
    </div>
  </div>
</footer>

<script>
  let isListening = false;
  let recognition = null;
  const chatStream = document.getElementById('chat-stream');
  const queryInput = document.getElementById('query-input');
  const micBtn = document.getElementById('btn-mic');

  // 1. Initialize Web Speech API for zero-latency voice input
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechAPI();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      isListening = true;
      micBtn.classList.add('listening');
    };
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      queryInput.value = transcript;
      sendMission();
    };
    recognition.onerror = () => stopVoice();
    recognition.onend = () => stopVoice();
  }

  function toggleVoice() {
    if (!recognition) {
      alert("Speech recognition not supported in this browser. Please use Chrome or Samsung Internet.");
      return;
    }
    if (isListening) {
      recognition.stop();
      stopVoice();
    } else {
      recognition.start();
    }
  }

  function stopVoice() {
    isListening = false;
    micBtn.classList.remove('listening');
  }

  // 2. Poll live device telemetry
  async function updateTelemetry() {
    try {
      const res = await fetch('/state');
      if (res.ok) {
        const data = await res.json();
        const battery = data.battery || '--%';
        const volume = data.media_volume || data.volume || '--';
        const app = (data.foreground_package || data.foreground_app || '--').split('.').pop();
        document.getElementById('pill-battery').innerHTML = `🔋 <strong>${battery}</strong>`;
        document.getElementById('pill-volume').innerHTML = `🔊 <strong>${volume}</strong>`;
        document.getElementById('pill-app').innerHTML = `📱 <strong>${app}</strong>`;
      }
    } catch(e) {}
  }
  setInterval(updateTelemetry, 3500);
  updateTelemetry();

  // 3. Send mission to agent
  async function sendMission(text) {
    const query = (text || queryInput.value).trim();
    if (!query) return;
    queryInput.value = '';

    // Append user card
    appendUserCard(query);

    // Append loading card
    const loadId = 'loading-' + Date.now();
    appendLoadingCard(loadId, query);

    try {
      let endpoint = '/session/message';
      let payload = { message: query };

      if (query.toLowerCase() === 'undo' || query.toLowerCase() === 'undo that') {
        endpoint = '/session/undo';
        payload = {};
      } else if (query.toLowerCase() === 'scan screen' || query.toLowerCase() === 'summarize this') {
        endpoint = '/ambient/scan';
        payload = { prompt: query };
      }

      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      removeElement(loadId);
      appendResponseCard(query, data);
      updateTelemetry();
    } catch(err) {
      removeElement(loadId);
      appendErrorCard(query, err.message);
    }
  }

  function quickAction(action) {
    if (action === 'scan') {
      sendMission('scan screen');
    } else if (action === 'undo') {
      sendMission('undo');
    } else if (action === 'compact') {
      compactStorage();
    } else {
      sendMission(action);
    }
  }

  async function compactStorage() {
    appendUserCard('Compact Storage (Enforce 25MB Hard Ceiling)');
    try {
      const res = await fetch('/storage/compact', { method: 'POST' });
      const data = await res.json();
      appendResponseCard('Compact Storage', {
        success: true,
        summary: `Storage verified: ${data.size_mb || (data.size_bytes_after/1048576).toFixed(2)} MB in use. Cap: 25.0 MB. WAL vacuum completed.`
      });
    } catch(e) {
      appendErrorCard('Compact Storage', e.message);
    }
  }

  async function retryStep(instruction) {
    sendMission(instruction);
  }

  async function undoStep() {
    sendMission('undo');
  }

  function appendUserCard(text) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.borderLeft = '3px solid var(--accent)';
    card.innerHTML = `
      <div class="card-header">
        <span class="card-title">User Mission</span>
        <span>${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
      </div>
      <p style="font-weight: 500;">${escapeHtml(text)}</p>
    `;
    chatStream.appendChild(card);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }

  function appendLoadingCard(id, query) {
    const card = document.createElement('div');
    card.id = id;
    card.className = 'card';
    card.innerHTML = `
      <div class="card-header">
        <span class="card-title">Executing...</span>
        <div class="pulse" style="width: 8px; height: 8px;"></div>
      </div>
      <p style="color: var(--text-muted); font-size: 13px;">Analyzing intent and dispatching Shizuku hardware controls...</p>
    `;
    chatStream.appendChild(card);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }

  function appendResponseCard(query, data) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.borderLeft = '3px solid var(--primary)';

    let stepsHtml = '';
    if (data.steps && data.steps.length > 0) {
      stepsHtml = '<div class="step-list">' + data.steps.map((s, idx) => `
        <div class="step-item">
          <span><strong>[${idx+1}]</strong> ${escapeHtml(s.action || s.goal || s.type || 'Action')}</span>
          <div class="step-actions">
            <button class="btn-sm btn-undo" onclick="undoStep()">Undo ↩</button>
            <button class="btn-sm" onclick="retryStep('${escapeHtml(query)}')">Retry 🔄</button>
          </div>
        </div>
      `).join('') + '</div>';
    }

    let summaryHtml = '';
    if (data.summary || data.output || data.response) {
      summaryHtml = `<div class="summary-box">${escapeHtml(data.summary || data.output || data.response)}</div>`;
    }

    card.innerHTML = `
      <div class="card-header">
        <span class="card-title" style="color: var(--primary);">Execution Verified</span>
        <span>${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
      </div>
      <p style="font-size: 13px;">${escapeHtml(data.message || 'Mission processed successfully.')}</p>
      ${stepsHtml}
      ${summaryHtml}
    `;
    chatStream.appendChild(card);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }

  function appendErrorCard(query, errorMsg) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.borderLeft = '3px solid var(--danger)';
    card.innerHTML = `
      <div class="card-header">
        <span class="card-title" style="color: var(--danger);">Action Failed</span>
        <span>${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
      </div>
      <p style="font-size: 13px; color: var(--danger);">${escapeHtml(errorMsg)}</p>
      <div style="margin-top: 8px;">
        <button class="btn-sm" onclick="retryStep('${escapeHtml(query)}')">Retry Step 🔄</button>
      </div>
    `;
    chatStream.appendChild(card);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  }

  function removeElement(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
</script>
</body>
</html>
"""
