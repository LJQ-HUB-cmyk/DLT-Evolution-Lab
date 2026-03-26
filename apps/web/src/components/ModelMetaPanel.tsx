import { driftLevelFromScore, driftLevelLabel, summarizeDrift } from "../lib/formatters";
import type { AnalysisResponse, DriftReport, ModelRegistryItem } from "../types";

type Props = {
  analysis: AnalysisResponse | null;
  loading?: boolean;
  champion: ModelRegistryItem | null;
  latestDrift: DriftReport | null | undefined;
};

export function ModelMetaPanel({ analysis, loading, champion, latestDrift }: Props) {
  const level = driftLevelFromScore(latestDrift?.drift_score);
  return (
    <section className="panel model-meta-panel m3-card-enter" data-testid="model-meta-panel">
      <div className="panel-title">模型与快照</div>
      <div className="model-meta-body">
        {loading ? <p className="muted">加载分析数据...</p> : null}
        {!loading && !analysis ? <p className="muted">暂无分析（请先同步历史数据）</p> : null}
        {analysis ? (
          <dl className="meta-grid">
            <dt>model_version</dt>
            <dd>{analysis.modelVersion}</dd>
            <dt>snapshot_hash</dt>
            <dd className="mono small">{analysis.snapshotHash}</dd>
            <dt>seed_hint</dt>
            <dd className="mono">{analysis.seedHint}</dd>
            <dt>target_issue</dt>
            <dd className="mono">{analysis.targetIssue}</dd>
            <dt>信用分 credit</dt>
            <dd>{champion != null ? champion.credit.toFixed(3) : "—"}</dd>
            <dt>冠军状态</dt>
            <dd>{champion ? `${champion.status}` : "—"}</dd>
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
