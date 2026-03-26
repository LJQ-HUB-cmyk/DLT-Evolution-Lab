import type { PredictionRun } from "../types";

type ControlPanelProps = {
  runs: PredictionRun[];
  targetIssue: string;
  onTargetIssueChange: (v: string) => void;
  onExperiment: () => void;
  onPublish: () => void;
  loading: boolean;
  publishing: boolean;
  apiError: string | null;
};

export function ControlPanel({
  runs,
  targetIssue,
  onTargetIssueChange,
  onExperiment,
  onPublish,
  loading,
  publishing,
  apiError,
}: ControlPanelProps) {
  const ver = runs.length ? runs[runs.length - 1].model_version : "—";
  return (
    <section className="panel control-pane m3-card-enter" style={{ animationDelay: "200ms" }}>
      <div className="panel-title">实验控制</div>
      <p className="muted">每次实验都会生成独立记录；正式发布后，该期正式预测将冻结。</p>
      <div className="control-row">
        <label className="control-label" htmlFor="target-issue-input">
          目标期号
        </label>
        <input
          id="target-issue-input"
          className="target-issue-input mono"
          value={targetIssue}
          onChange={(e) => onTargetIssueChange(e.target.value)}
          aria-label="目标期号"
        />
      </div>
      {apiError ? <div className="error-inline">{apiError}</div> : null}
      <div className="control-actions">
        <button
          className="primary-btn"
          data-testid="btn-experiment"
          disabled={loading || publishing}
          onClick={onExperiment}
          type="button"
        >
          {loading ? "计算中..." : "实验计算"}
        </button>
        <button
          className="secondary-btn"
          data-testid="btn-publish"
          disabled={loading || publishing}
          onClick={onPublish}
          type="button"
        >
          {publishing ? "发布中..." : "发布正式预测"}
        </button>
      </div>
      <div className="stats-grid">
        <div className="stat-card">
          <span>实验记录数</span>
          <strong>{runs.length}</strong>
        </div>
        <div className="stat-card">
          <span>当前模型</span>
          <strong className="mono small">{ver}</strong>
        </div>
        <div className="stat-card">
          <span>图表引擎</span>
          <strong>图形展示</strong>
        </div>
      </div>
    </section>
  );
}
