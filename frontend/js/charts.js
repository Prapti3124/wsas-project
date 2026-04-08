/* ═══════════════════════════════════════════════════════════════════════════
   WSAS – Analytics Charts (charts.js)
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
  } catch (e) { console.warn('Analytics sync failed:', e); }
}

function renderAlertChart(alerts) {
  const days = {};
  for (let i = 29; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
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
