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
        data: ["前1", "前2", "前3", "前4", "前5", "后1", "后2"],
        splitArea: { show: true },
      },
      yAxis: {
        type: "category",
        data: ["候选1", "候选2", "候选3", "候选4", "候选5", "候选6", "候选7", "候选8"].slice(0, 8),
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
          name: "概率热力",
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
      <div className="panel-title">位置概率热力图</div>
      <div className="heat-chart-wrap">
        {!analysis ? <p className="muted pad">暂无分析数据。</p> : null}
        {analysis && !isJsdom ? <div ref={ref} className="heat-chart" /> : null}
        {analysis && isJsdom ? <p className="muted pad">测试环境跳过图表渲染。</p> : null}
      </div>
    </section>
  );
}
