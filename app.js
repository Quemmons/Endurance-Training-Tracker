document.addEventListener('DOMContentLoaded', function () {
  if (!window.dashboardDataUrl) {
    return;
  }

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
