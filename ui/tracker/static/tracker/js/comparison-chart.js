(() => {
  // One line per item, all in the viewer's currency. Dates are milliseconds on a plain number
  // axis, so prices are spaced by real time without needing Chart.js's date add-on.
  const canvas = document.getElementById("comparisonChart");
  const dataNode = document.getElementById("comparison-chart-data");
  if (!canvas || !dataNode || !window.Chart) return;

  const data = JSON.parse(dataNode.textContent);
  const colours = ["#478665", "#d07a3c", "#4f7fae", "#a65d8f", "#c2a33a", "#5aa3a0", "#8a6d4f", "#7a7fb8"];
  const DAY = 24 * 60 * 60 * 1000;
  const formatDate = (ms, withYear) => new Date(ms).toLocaleDateString(undefined,
    withYear ? { day: "numeric", month: "short", year: "numeric" } : { day: "numeric", month: "short" });
  const formatAmount = (value) => Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const datasets = data.series.map((series, index) => {
    const colour = colours[index % colours.length];
    return {
      label: series.name,
      data: series.points.map((point) => ({ x: point.x, y: Number(point.y), original: point.original })),
      borderColor: colour,
      backgroundColor: colour,
      borderWidth: 2.5,
      pointBackgroundColor: "#fff",
      pointBorderColor: colour,
      pointBorderWidth: 2,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.25,
    };
  });

  // Keep a single price (or several on one day) from collapsing the axis to a point.
  const times = data.series.flatMap((series) => series.points.map((point) => point.x));
  let min = Math.min(...times);
  let max = Math.max(...times);
  if (max - min < DAY) { min -= DAY; max += DAY; }

  new Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      parsing: true,
      interaction: { intersect: false, mode: "nearest" },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#5e6c65", font: { size: 11 } } },
        tooltip: {
          backgroundColor: "#263c31",
          padding: 11,
          callbacks: {
            title(items) { return items.length ? formatDate(items[0].parsed.x, true) : ""; },
            label(context) {
              const amount = `${formatAmount(context.parsed.y)} ${data.currency}`;
              const original = context.raw.original;
              return `${context.dataset.label}: ${original ? `${amount} (${original})` : amount}`;
            },
          },
        },
      },
      scales: {
        x: {
          type: "linear",
          min,
          max,
          grid: { display: false },
          border: { display: false },
          ticks: { color: "#99a49e", font: { size: 10 }, maxRotation: 0, maxTicksLimit: 6, callback: (value) => formatDate(value, false) },
        },
        y: { grid: { color: "#edf1ee", drawTicks: false }, border: { display: false }, ticks: { color: "#99a49e", padding: 10, font: { size: 10 } } },
      },
    },
  });
})();
