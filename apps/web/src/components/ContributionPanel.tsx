import { useMemo, useState } from "react";

import type { AnalysisResponse, PositionBlock } from "../types";

type Props = {
  analysis: AnalysisResponse | null;
};

export function ContributionPanel({ analysis }: Props) {
  const [zone, setZone] = useState<"front" | "back">("front");
  const [posIdx, setPosIdx] = useState(0);

  const block: PositionBlock | undefined = useMemo(() => {
    if (!analysis) {
      return undefined;
    }
    const list = zone === "front" ? analysis.positionProbabilities.front : analysis.positionProbabilities.back;
    return list[posIdx];
  }, [analysis, zone, posIdx]);

  const top = block?.top_numbers?.[0];

  return (
    <section className="panel contribution-panel m3-card-enter" style={{ animationDelay: "40ms" }}>
      <div className="panel-title">贡献因子（Top1 号码）</div>
      <div className="contrib-toolbar">
        <select
          aria-label="zone"
          value={zone}
          onChange={(e) => {
            setZone(e.target.value as "front" | "back");
            setPosIdx(0);
          }}
        >
          <option value="front">前区</option>
          <option value="back">后区</option>
        </select>
        <select
          aria-label="position"
          value={posIdx}
          onChange={(e) => setPosIdx(Number(e.target.value))}
        >
          {(zone === "front" ? [0, 1, 2, 3, 4] : [0, 1]).map((i) => (
            <option key={i} value={i}>
              位次 {i + 1}
            </option>
          ))}
        </select>
      </div>
      {!top ? <p className="muted">无数据</p> : null}
      {top ? (
        <div className="contrib-body">
          <div className="contrib-headline">
            <span className={`ball ${zone === "front" ? "ball-red" : "ball-blue"}`}>{String(top.number).padStart(2, "0")}</span>
            <span className="prob-pill">p̂ {top.calibrated_prob.toFixed(4)}</span>
          </div>
          <ul className="factor-list">
            {(top.top_factors ?? []).map((f, i) => (
              <li key={i} className="factor-item">
                {Object.entries(f).map(([k, v]) => (
                  <span key={k}>
                    <strong>{k}</strong> × {v.toFixed(3)}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
