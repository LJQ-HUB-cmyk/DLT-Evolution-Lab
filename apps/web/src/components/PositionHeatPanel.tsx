import { HeatmapChart } from "echarts/charts";
import { GridComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import type { AnalysisResponse } from "../types";

type Props = {
  analysis: AnalysisResponse | null;
};

use([HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer]);

export function PositionHeatPanel({ analysis }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const isJsdom = typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent);

  useEffect(() => {
    if (isJsdom) {
      return;
    }
    const el = ref.current;
    if (!el || !analysis) {
      return;
    }

    const chart = init(el);
    const data: [number, number, number][] = [];
    analysis.positionProbabilities.front.forEach((block, pi) => {
      block.top_numbers.slice(0, 8).forEach((t, ri) => {
        data.push([pi, ri, t.calibrated_prob]);
      });
    });
    analysis.positionProbabilities.back.forEach((block, pi) => {
      block.top_numbers.slice(0, 6).forEach((t, ri) => {
        data.push([pi + 5, ri, t.calibrated_prob]);
      });
    });

    chart.setOption({
      animationDurationUpdate: 280,
      grid: { left: 48, right: 12, top: 28, bottom: 28 },
      tooltip: { position: "top" },
      xAxis: {
        type: "category",
        data: ["F1", "F2", "F3", "F4", "F5", "B1", "B2"],
        splitArea: { show: true },
      },
      yAxis: {
        type: "category",
        data: ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"].slice(0, 8),
        splitArea: { show: true },
      },
      visualMap: {
        min: 0,
        max: 0.35,
        calculable: false,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        inRange: { color: ["#e8f0ff", "#1f58b8"] },
      },
      series: [
        {
          name: "calibrated_prob",
          type: "heatmap",
          data,
          label: { show: false },
          emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.25)" } },
        },
      ],
    });

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [analysis, isJsdom]);

  return (
    <section className="panel position-heat-panel m3-card-enter" style={{ animationDelay: "80ms" }}>
      <div className="panel-title">Position Heatmap (ECharts)</div>
      <div className="heat-chart-wrap">
        {!analysis ? <p className="muted pad">No analysis data.</p> : null}
        {analysis && !isJsdom ? <div ref={ref} className="heat-chart" /> : null}
        {analysis && isJsdom ? <p className="muted pad">Heatmap skipped in test runtime.</p> : null}
      </div>
    </section>
  );
}

