// Apply goal progress bar widths from data-progress attributes.
// (Kept separate from the chart-loading listener below so it always runs,
// even when there's no dashboardDataUrl for the charts.)
document.addEventListener('DOMContentLoaded', function () {
  document.querySelectorAll('.progress-bar[data-progress]').forEach(function (el) {
    el.style.width = el.dataset.progress + '%';
  });
});

// Shuffle button for the dashboard's Milestones (fun facts) card.
document.addEventListener('DOMContentLoaded', function () {
  const shuffleBtn = document.getElementById('shuffle-milestones-btn');
  const list = document.getElementById('milestones-list');
  if (!shuffleBtn || !list) {
    return;
  }

  shuffleBtn.addEventListener('click', function () {
    shuffleBtn.disabled = true;
    fetch('/dashboard/milestones/shuffle')
      .then(response => response.json())
      .then(data => {
        list.innerHTML = data.stats.map(stat => `
          <div class="border rounded p-3 mb-3">
            <h6 class="text-muted mb-2">${stat.title}</h6>
            <p class="fw-bold fs-5 mb-2">${stat.value}</p>
            <p class="small text-muted mb-0">${stat.detail}</p>
          </div>
        `).join('');
      })
      .finally(() => {
        shuffleBtn.disabled = false;
      });
  });
});

// Wait for the page to finish loading before drawing the dashboard charts.
document.addEventListener('DOMContentLoaded', function () {
  // The page provides a JSON endpoint for chart data. If it is missing, stop here.
  if (!window.dashboardDataUrl) {
    return;
  }

  // Load the dashboard data and render each chart with the returned values.
  fetch(window.dashboardDataUrl)
    .then(response => response.json())
    .then(data => {
      const weeklyCtx = document.getElementById('weeklyChart');
      const monthlyCtx = document.getElementById('monthlyChart');
      const distributionCtx = document.getElementById('distributionChart');

      if (weeklyCtx) {
        new Chart(weeklyCtx, {
          type: 'bar',
          data: {
            labels: data.weekly.map(item => item.label),
            datasets: [{
              label: 'Weekly mileage',
              data: data.weekly.map(item => item.distance),
              backgroundColor: '#0d6efd'
            }]
          },
          options: {
            responsive: true,
            scales: {
              y: { beginAtZero: true }
            }
          }
        });
      }

      if (monthlyCtx) {
        new Chart(monthlyCtx, {
          type: 'line',
          data: {
            labels: data.monthly.map(item => item.label),
            datasets: [{
              label: 'Monthly mileage',
              data: data.monthly.map(item => item.distance),
              borderColor: '#198754',
              backgroundColor: 'rgba(25, 135, 84, 0.15)',
              fill: true,
              tension: 0.3
            }]
          },
          options: {
            responsive: true,
            scales: {
              y: { beginAtZero: true }
            }
          }
        });
      }

      if (distributionCtx) {
        new Chart(distributionCtx, {
          type: 'doughnut',
          data: {
            labels: data.distribution.map(item => item.type),
            datasets: [{
              data: data.distribution.map(item => item.distance),
              backgroundColor: ['#0d6efd', '#198754', '#ffc107']
            }]
          },
          options: {
            responsive: true,
            plugins: {
              legend: { position: 'bottom' }
            }
          }
        });
      }
    });
});