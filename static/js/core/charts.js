const ChartKit = (function () {
  const charts = {};

  function render(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), config);
    return charts[id];
  }

  const valueLabels = {
    id: "valueLabels",
    afterDatasetsDraw(c, _args, opts) {
      if (!opts || !opts.format) return;
      const horizontal = c.options.indexAxis === "y";
      const { ctx } = c;
      ctx.save();
      ctx.font = `11px ${APP.FONT_FAMILY}`;
      ctx.fillStyle = APP.COLORS.CHART_TEXT;
      ctx.textAlign = horizontal ? "left" : "center";
      ctx.textBaseline = horizontal ? "middle" : "alphabetic";
      c.getDatasetMeta(0).data.forEach((bar, i) => {
        const text = opts.format(c.data.datasets[0].data[i], i);
        if (!horizontal) {
          ctx.fillText(text, bar.x, bar.y - 5);
          return;
        }
        if (bar.x + 6 + ctx.measureText(text).width <= c.chartArea.right) {
          ctx.fillStyle = APP.COLORS.CHART_TEXT;
          ctx.textAlign = "left";
          ctx.fillText(text, bar.x + 6, bar.y);
        } else {
          ctx.fillStyle = "#fff";
          ctx.textAlign = "right";
          ctx.fillText(text, bar.x - 6, bar.y);
        }
      });
      ctx.restore();
    },
  };

  function hbar(id, { labels, values, colors, label, tooltip, tick, autoHeight = true }) {
    if (autoHeight) document.getElementById(id).parentElement.style.height = `${Math.max(220, labels.length * 26 + 40)}px`;
    return render(id, {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 4, maxBarThickness: 18, minBarLength: 4 }] },
      plugins: [valueLabels],
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          valueLabels: { format: label },
          tooltip: { callbacks: { title: (c) => tooltip(c[0].dataIndex)[0], label: (c) => tooltip(c.dataIndex).slice(1) } },
        },
        scales: {
          x: {
            beginAtZero: true,
            grace: "15%",
            ticks: { callback: tick, maxTicksLimit: 5, maxRotation: 0 },
            grid: { color: APP.COLORS.CHART_GRID },
          },
          y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } },
        },
      },
    });
  }

  return { render, valueLabels, hbar };
})();
