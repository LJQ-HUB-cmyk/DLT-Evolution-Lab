import {
  driftLevelFromBackend,
  driftLevelFromScore,
  driftLevelLabel,
  summarizeDrift,
} from "../lib/formatters";
import type { AnalysisResponse, DriftReport, ModelRegistryItem } from "../types";

type Props = {
  analysis: AnalysisResponse | null;
  loading?: boolean;
  champion: ModelRegistryItem | null;
  latestDrift: DriftReport | null | undefined;
};

export function ModelMetaPanel({ analysis, loading, champion, latestDrift }: Props) {
  const creditDisplay = (() => {
    if (!champion) {
      return null;
    }
    if (typeof champion.credit_score === "number") {
      return champion.credit_score;
    }
    if (typeof champion.credit === "number") {
      return champion.credit <= 1.5 ? champion.credit * 70 : champion.credit;
    }
    return null;
  })();

  const championStatusLabel = (status?: string) => {
    if (!status) {
      return "--";
    }
    if (status === "champion") {
      return "冠军";
    }
    if (status === "candidate") {
      return "候选";
    }
    if (status === "unstable") {
      return "不稳定";
    }
    if (status === "watch") {
      return "观察";
    }
    if (status === "deprecated") {
      return "已弃用";
    }
    return status;
  };

  const levelFromBackend = driftLevelFromBackend(latestDrift?.drift_level);
  const levelFromScore = driftLevelFromScore(latestDrift?.drift_score);
  const level = levelFromBackend !== "unknown" ? levelFromBackend : levelFromScore;
  return (
    <section className="panel model-meta-panel m3-card-enter" data-testid="model-meta-panel">
      <div className="panel-title">模型快照</div>
      <div className="model-meta-body">
        {loading ? <p className="muted">正在加载分析...</p> : null}
        {!loading && !analysis ? <p className="muted">暂无分析，请先同步足够历史期次。</p> : null}
        {analysis ? (
          <dl className="meta-grid">
            <dt>模型版本</dt>
            <dd>{analysis.modelVersion}</dd>
            <dt>快照哈希</dt>
            <dd className="mono small">{analysis.snapshotHash}</dd>
            <dt>种子提示</dt>
            <dd className="mono">{analysis.seedHint}</dd>
            <dt>目标期号</dt>
            <dd className="mono">{analysis.targetIssue}</dd>
            <dt>信用分</dt>
            <dd>{creditDisplay != null ? creditDisplay.toFixed(1) : "--"}</dd>
            <dt>状态</dt>
            <dd>{champion ? championStatusLabel(champion.status) : "--"}</dd>
            <dt>漂移等级</dt>
            <dd>
              <span className={`drift-pill drift-${level}`}>{driftLevelLabel(level)}</span>
            </dd>
            <dt>漂移摘要</dt>
            <dd className="small">{summarizeDrift(latestDrift)}</dd>
          </dl>
        ) : null}
      </div>
    </section>
  );
}
