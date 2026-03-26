import { driftLevelFromScore, driftLevelLabel, summarizeDrift } from "../lib/formatters";
import type { AnalysisResponse, DriftReport, ModelRegistryItem } from "../types";

type Props = {
  analysis: AnalysisResponse | null;
  loading?: boolean;
  champion: ModelRegistryItem | null;
  latestDrift: DriftReport | null | undefined;
};

export function ModelMetaPanel({ analysis, loading, champion, latestDrift }: Props) {
  const championStatusLabel = (status?: string) => {
    if (!status) {
      return "—";
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
    return status;
  };

  const level = driftLevelFromScore(latestDrift?.drift_score);
  return (
    <section className="panel model-meta-panel m3-card-enter" data-testid="model-meta-panel">
      <div className="panel-title">模型与快照</div>
      <div className="model-meta-body">
        {loading ? <p className="muted">加载分析数据...</p> : null}
        {!loading && !analysis ? <p className="muted">暂无分析，请先同步历史数据。</p> : null}
        {analysis ? (
          <dl className="meta-grid">
            <dt>模型版本</dt>
            <dd>{analysis.modelVersion}</dd>
            <dt>快照哈希</dt>
            <dd className="mono small">{analysis.snapshotHash}</dd>
            <dt>随机种子</dt>
            <dd className="mono">{analysis.seedHint}</dd>
            <dt>目标期号</dt>
            <dd className="mono">{analysis.targetIssue}</dd>
            <dt>信用分</dt>
            <dd>{champion != null ? champion.credit.toFixed(3) : "—"}</dd>
            <dt>冠军状态</dt>
            <dd>{champion ? championStatusLabel(champion.status) : "—"}</dd>
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
