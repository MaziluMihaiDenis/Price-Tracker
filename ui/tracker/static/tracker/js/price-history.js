(() => {
  const canvas = document.getElementById("priceHistoryChart");
  const dataNode = document.getElementById("chart-data");
  if (!canvas || !dataNode || !window.Chart) return;

  const history = JSON.parse(dataNode.textContent);
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, "rgba(72, 139, 98, .18)");
  gradient.addColorStop(1, "rgba(72, 139, 98, 0)");

  new Chart(canvas, {
    type: "line",
    data: {
      labels: history.labels,
      datasets: [{
        label: "Saved price",
        data: history.values,
        borderColor: "#478665",
        backgroundColor: gradient,
        borderWidth: 2.5,
        pointBackgroundColor: "#fff",
        pointBorderColor: "#478665",
        pointBorderWidth: 2,
        pointRadius: 4,
        pointHoverRadius: 6,
        fill: true,
        tension: .34,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { intersect: false, mode: "index" },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#263c31",
          padding: 11,
          displayColors: false,
          callbacks: {
            label(context) {
              const currency = history.currencies[context.dataIndex] || "";
              return `${Number(context.raw).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${currency}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, border: { display: false }, ticks: { color: "#99a49e", font: { size: 10 }, maxRotation: 0 } },
        y: { grid: { color: "#edf1ee", drawTicks: false }, border: { display: false, dash: [3, 4] }, ticks: { color: "#99a49e", padding: 10, font: { size: 10 } } },
      },
    },
  });
})();
