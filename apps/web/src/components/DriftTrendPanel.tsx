import { GridComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import { init, use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useMemo, useRef } from "react";

import type { PredictionRun } from "../types";

use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

type Props = {
  runs: PredictionRun[];
};

export function DriftTrendPanel({ runs }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const isJsdom = typeof navigator !== "undefined" && /jsdom/i.test(navigator.userAgent);

  const series = useMemo(() => {
    return runs
      .filter((r) => r.drift && typeof r.drift.drift_score === "number")
      .map((r, i) => ({
        idx: i + 1,
        score: r.drift!.drift_score,
        run_id: r.run_id,
      }));
  }, [runs]);

  useEffect(() => {
    if (isJsdom || series.length === 0) {
      return;
    }
    const el = ref.current;
    if (!el) {
      return;
    }
    const chart = init(el);
    chart.setOption({
      animationDurationUpdate: 200,
      grid: { left: 48, right: 16, top: 24, bottom: 28 },
      tooltip: { trigger: "axis" },
      xAxis: { type: "category", data: series.map((s) => String(s.idx)) },
      yAxis: { type: "value", name: "drift" },
      series: [
        {
          name: "drift_score",
          type: "line",
          smooth: true,
          data: series.map((s) => s.score),
        },
      ],
    });
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [isJsdom, series]);

  return (
    <section className="panel drift-trend-panel m3-card-enter" style={{ animationDelay: "100ms" }}>
      <div className="panel-title">漂移趋势（实验 run）</div>
      <div className="heat-chart-wrap">
        {series.length === 0 ? (
          <p className="muted pad">暂无漂移序列（当前引擎 run 未写入 drift 或样本不足）</p>
        ) : null}
        {series.length > 0 && !isJsdom ? <div ref={ref} className="heat-chart drift-chart" /> : null}
        {series.length > 0 && isJsdom ? <p className="muted pad">图表在测试环境跳过渲染</p> : null}
      </div>
    </section>
  );
}
