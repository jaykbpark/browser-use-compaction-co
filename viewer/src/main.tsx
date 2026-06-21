import React from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  FileText,
  Gauge,
  Image,
  MousePointerClick,
  RefreshCw,
} from "lucide-react";
import "./styles.css";

type RunSummary = {
  runs: string[];
};

type BrowserAction = {
  type: string;
  target?: string | null;
  text?: string | null;
  key?: string | null;
  amount?: number | null;
  url?: string | null;
};

type StepRecord = {
  step: number;
  action: BrowserAction;
  result: {
    ok: boolean;
    message?: string;
    error?: string | null;
  };
};

type StructuralChange = {
  type: string;
  detail: string;
};

type CompactObservation = {
  step: number;
  action_result: string;
  summary: string;
  changed: StructuralChange[];
  visual_changed_pct: number;
  visual_raw_changed_pct: number;
  visual_ssim_score?: number | null;
  visual_phash_distance?: number | null;
  fallback: "none" | "crop" | "full_screenshot";
  route: "text_only" | "crop_with_context" | "full_screenshot";
  route_reason: string;
  confidence: number;
  llm_observation: string;
  crop_paths: string[];
  full_screenshot_path?: string | null;
  visual_regions: VisualRegion[];
  tokens_estimate: number;
  baseline_tokens_estimate: number;
  reduction_pct: number;
};

type VisualRegion = {
  bbox: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  kind: string;
  crop_path?: string | null;
  area_pct: number;
  element_ref?: string | null;
  element_role?: string | null;
  element_name?: string | null;
  overlap_pct: number;
  ocr_text?: string | null;
};

type ReplayStepResult = {
  step: number;
  expected_next_action: BrowserAction;
  predicted_next_action: BrowserAction;
  passed: boolean;
  match_reason: string;
  rationale: string;
  confidence: number;
};

type ReplayReport = {
  context_mode: "compact" | "full_state" | "vision_full_state";
  predictor: string;
  evaluated_steps: number;
  passed_steps: number;
  next_action_accuracy: number;
  compact_tokens: number;
  baseline_tokens: number;
  avg_reduction_pct: number;
  steps: ReplayStepResult[];
};

type EvalComparisonSummary = {
  baseline_context_mode?: "compact" | "full_state" | "vision_full_state";
  evaluated_steps: number;
  compact_passed_steps: number;
  baseline_passed_steps: number;
  compact_accuracy: number;
  baseline_accuracy: number;
  accuracy_delta: number;
  compact_tokens: number;
  baseline_tokens: number;
  token_savings: number;
  token_reduction_pct: number;
};

type EvalComparisonReport = {
  run_id: string;
  predictor: string;
  compact: ReplayReport;
  baseline: ReplayReport;
  summary: EvalComparisonSummary;
  verdict: string;
  explanation: string[];
};

type RunDetail = {
  run_id: string;
  manifest: {
    start_url?: string;
    mode?: string;
  } | null;
  steps: StepRecord[];
  compact_observations: CompactObservation[];
  eval_report?: ReplayReport | null;
  eval_full_state_report?: ReplayReport | null;
  eval_vision_full_state_report?: ReplayReport | null;
  eval_comparison?: EvalComparisonReport | null;
};

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState<string>("");
  const [detail, setDetail] = React.useState<RunDetail | null>(null);
  const [selectedStep, setSelectedStep] = React.useState(1);
  const [predictor, setPredictor] = React.useState<"heuristic" | "llm">("heuristic");
  const [status, setStatus] = React.useState("loading");
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    fetch("/api/runs")
      .then((response) => response.json())
      .then((data: RunSummary) => {
        const nextRuns = data.runs ?? [];
        setRuns(nextRuns);
        setSelectedRun((current) => current || nextRuns[0] || "");
        setStatus("ready");
      })
      .catch(() => setStatus("api unavailable"));
  }, []);

  React.useEffect(() => {
    if (!selectedRun) {
      setDetail(null);
      return;
    }
    loadRun(selectedRun).then((run) => {
      setDetail(run);
      setSelectedStep(run.compact_observations[0]?.step ?? run.steps[0]?.step ?? 1);
    });
  }, [selectedRun]);

  const selectedObservation =
    detail?.compact_observations.find((observation) => observation.step === selectedStep) ?? null;
  const selectedRawStep = detail?.steps.find((step) => step.step === selectedStep) ?? null;
  const selectedReplayStep =
    detail?.eval_report?.steps.find((step) => step.step === selectedStep) ?? null;
  const stats = summarizeRun(detail);

  async function compactSelectedRun() {
    if (!selectedRun) return;
    setBusy(true);
    try {
      await fetch(`/api/runs/${encodeURIComponent(selectedRun)}/compact`, { method: "POST" });
      setDetail(await loadRun(selectedRun));
    } finally {
      setBusy(false);
    }
  }

  async function evaluateSelectedRun() {
    if (!selectedRun) return;
    setBusy(true);
    try {
      await fetch(
        `/api/runs/${encodeURIComponent(selectedRun)}/eval?predictor=${encodeURIComponent(predictor)}`,
        { method: "POST" },
      );
      setDetail(await loadRun(selectedRun));
    } finally {
      setBusy(false);
    }
  }

  async function compareSelectedRun() {
    if (!selectedRun) return;
    setBusy(true);
    try {
      await fetch(
        `/api/runs/${encodeURIComponent(selectedRun)}/eval/compare?predictor=${encodeURIComponent(
          predictor,
        )}&baseline_context_mode=vision_full_state`,
        { method: "POST" },
      );
      setDetail(await loadRun(selectedRun));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">BrowserDelta</p>
          <h1>Run Inspector</h1>
        </div>
        <div className="status-pill" data-state={status === "ready" ? "ok" : "warn"}>
          {status === "ready" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{status}</span>
        </div>
      </header>

      <section className="toolbar" aria-label="Run controls">
        <label>
          Run
          <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
            {runs.length === 0 ? <option>No runs</option> : null}
            {runs.map((run) => (
              <option key={run} value={run}>
                {run}
              </option>
            ))}
          </select>
        </label>
        <label>
          Predictor
          <select
            value={predictor}
            onChange={(event) => setPredictor(event.target.value as "heuristic" | "llm")}
          >
            <option value="heuristic">heuristic</option>
            <option value="llm">llm</option>
          </select>
        </label>
        <button type="button" onClick={compactSelectedRun} disabled={!selectedRun || busy}>
          <RefreshCw size={16} />
          {busy ? "Compacting" : "Compact"}
        </button>
        <button type="button" onClick={evaluateSelectedRun} disabled={!selectedRun || busy}>
          <CheckCircle2 size={16} />
          Evaluate
        </button>
        <button type="button" onClick={compareSelectedRun} disabled={!selectedRun || busy}>
          <Gauge size={16} />
          Compare
        </button>
        {detail?.manifest ? (
          <p className="run-meta">
            {detail.manifest.mode ?? "unknown"} · {detail.manifest.start_url ?? "no start url"}
          </p>
        ) : null}
      </section>

      <section className="stats-grid" aria-label="Run metrics">
        <Metric icon={<Activity size={18} />} label="Steps" value={String(stats.steps)} />
        <Metric icon={<Gauge size={18} />} label="Avg Saved" value={`${stats.avgReduction}%`} />
        <Metric icon={<FileText size={18} />} label="Compact Tokens" value={String(stats.compact)} />
        <Metric icon={<Image size={18} />} label="Image Fallbacks" value={String(stats.fallbacks)} />
        <Metric icon={<CheckCircle2 size={18} />} label="Next Action" value={stats.replayScore} />
        <Metric icon={<Gauge size={18} />} label="Vs Baseline" value={stats.comparisonScore} />
        <Metric icon={<Gauge size={18} />} label="Predictor" value={stats.predictor} />
      </section>

      {detail?.eval_comparison ? <ComparisonPanel comparison={detail.eval_comparison} /> : null}

      <section className="workspace">
        <aside className="step-list" aria-label="Steps">
          <div className="section-heading">
            <MousePointerClick size={16} />
            <h2>Steps</h2>
          </div>
          {detail?.compact_observations.length ? (
            detail.compact_observations.map((observation) => (
              <button
                key={observation.step}
                type="button"
                className="step-row"
                data-selected={observation.step === selectedStep}
                onClick={() => setSelectedStep(observation.step)}
              >
                <span className="step-number">{observation.step}</span>
                <span>
                  <span className={`route route-${observation.route}`}>
                    {formatRoute(observation.route)}
                  </span>
                  <strong>{observation.summary}</strong>
                </span>
              </button>
            ))
          ) : (
            <p className="empty">No compact observations yet. Run compact to generate them.</p>
          )}
        </aside>

        <section className="detail-pane" aria-label="Selected step detail">
          {selectedObservation ? (
            <StepDetail
              runId={selectedRun}
              observation={selectedObservation}
              rawStep={selectedRawStep}
              replayStep={selectedReplayStep}
            />
          ) : (
            <p className="empty">Select a run and compact it to inspect observations.</p>
          )}
        </section>
      </section>
    </main>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <article className="metric">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ComparisonPanel({ comparison }: { comparison: EvalComparisonReport }) {
  const summary = comparison.summary;
  const baselineLabel = formatContextMode(
    summary.baseline_context_mode ?? comparison.baseline.context_mode,
  );
  return (
    <section className="comparison-panel" aria-label="Compact versus baseline eval">
      <div className="comparison-result">
        <p className="eyebrow">Eval Comparison</p>
        <h2>{humanizeVerdict(comparison.verdict)}</h2>
        <p>
          Compact got {summary.compact_passed_steps}/{summary.evaluated_steps}; {baselineLabel} got{" "}
          {summary.baseline_passed_steps}/{summary.evaluated_steps}. Compact saved{" "}
          {summary.token_reduction_pct.toFixed(2)}% estimated tokens.
        </p>
      </div>
      <dl className="comparison-metrics">
        <div>
          <dt>Compact</dt>
          <dd>
            {summary.compact_passed_steps}/{summary.evaluated_steps}
          </dd>
        </div>
        <div>
          <dt>{baselineLabel}</dt>
          <dd>
            {summary.baseline_passed_steps}/{summary.evaluated_steps}
          </dd>
        </div>
        <div>
          <dt>Saved</dt>
          <dd>{summary.token_reduction_pct.toFixed(2)}%</dd>
        </div>
        <div>
          <dt>Tokens</dt>
          <dd>
            {summary.compact_tokens} / {summary.baseline_tokens}
          </dd>
        </div>
      </dl>
      <ul className="comparison-explanation">
        {comparison.explanation.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

function StepDetail({
  runId,
  observation,
  rawStep,
  replayStep,
}: {
  runId: string;
  observation: CompactObservation;
  rawStep: StepRecord | null;
  replayStep: ReplayStepResult | null;
}) {
  const evidencePaths = observation.crop_paths.length
    ? observation.crop_paths
    : observation.full_screenshot_path
      ? [observation.full_screenshot_path]
      : [];

  return (
    <>
      <div className="detail-header">
        <div>
          <p className="eyebrow">Step {observation.step}</p>
          <h2>{observation.summary}</h2>
        </div>
        <span className={`route route-${observation.route}`}>{formatRoute(observation.route)}</span>
      </div>

      <dl className="kv-grid">
        <div>
          <dt>Action</dt>
          <dd>{formatAction(rawStep?.action)}</dd>
        </div>
        <div>
          <dt>Saved</dt>
          <dd>{observation.reduction_pct}%</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{Math.round(observation.confidence * 100)}%</dd>
        </div>
        <div>
          <dt>Visual Change</dt>
          <dd>{observation.visual_changed_pct}%</dd>
        </div>
        <div>
          <dt>SSIM</dt>
          <dd>{observation.visual_ssim_score?.toFixed(3) ?? "n/a"}</dd>
        </div>
        <div>
          <dt>pHash</dt>
          <dd>{observation.visual_phash_distance ?? "n/a"}</dd>
        </div>
      </dl>

      <section className="observation-block">
        <div className="section-heading">
          <FileText size={16} />
          <h3>LLM Observation</h3>
        </div>
        <pre>{observation.llm_observation}</pre>
      </section>

      {replayStep ? (
        <section className="replay-block" data-state={replayStep.passed ? "pass" : "fail"}>
          <div className="section-heading">
            {replayStep.passed ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <h3>Replay Eval</h3>
          </div>
          <dl className="replay-grid">
            <div>
              <dt>Expected Next</dt>
              <dd>{formatAction(replayStep.expected_next_action)}</dd>
            </div>
            <div>
              <dt>Predicted Next</dt>
              <dd>{formatAction(replayStep.predicted_next_action)}</dd>
            </div>
            <div>
              <dt>Score</dt>
              <dd>{replayStep.passed ? "Pass" : "Fail"}</dd>
            </div>
            <div>
              <dt>Replay Confidence</dt>
              <dd>{Math.round(replayStep.confidence * 100)}%</dd>
            </div>
          </dl>
          <p>{replayStep.rationale}</p>
          <p className="match-reason">{replayStep.match_reason}</p>
        </section>
      ) : null}

      {observation.changed.length ? (
        <section className="change-list">
          <div className="section-heading">
            <Activity size={16} />
            <h3>Detected Changes</h3>
          </div>
          <ul>
            {observation.changed.slice(0, 12).map((change, index) => (
              <li key={`${change.type}-${index}`}>
                <code>{change.type}</code>
                <span>{change.detail}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {observation.visual_regions?.length ? (
        <section className="visual-region-list">
          <div className="section-heading">
            <Image size={16} />
            <h3>Visual Regions</h3>
          </div>
          <ul>
            {observation.visual_regions.slice(0, 8).map((region, index) => (
              <li key={`${region.kind}-${index}`}>
                <code>{region.kind}</code>
                <span>
                  {region.element_name || region.element_ref || "unmatched area"}
                  {region.element_role ? ` · ${region.element_role}` : ""} · {region.area_pct}% area
                  {region.overlap_pct ? ` · ${Math.round(region.overlap_pct)}% overlap` : ""}
                  {region.ocr_text ? ` · OCR: ${region.ocr_text}` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {evidencePaths.length ? (
        <section className="evidence">
          <div className="section-heading">
            <Image size={16} />
            <h3>Evidence</h3>
          </div>
          <div className="evidence-grid">
            {evidencePaths.map((path) => (
              <figure key={path}>
                <img src={runFileUrl(runId, path)} alt={path} />
                <figcaption>{path}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

async function loadRun(runId: string): Promise<RunDetail> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new Error(`Failed to load run ${runId}`);
  return response.json();
}

function summarizeRun(detail: RunDetail | null) {
  const observations = detail?.compact_observations ?? [];
  const compact = observations.reduce((total, observation) => total + observation.tokens_estimate, 0);
  const avgReduction = observations.length
    ? observations.reduce((total, observation) => total + observation.reduction_pct, 0) /
      observations.length
    : 0;
  return {
    steps: detail?.steps.length ?? 0,
    avgReduction: avgReduction.toFixed(1),
    compact,
    fallbacks: observations.filter((observation) => observation.fallback !== "none").length,
    replayScore: detail?.eval_report
      ? `${detail.eval_report.passed_steps}/${detail.eval_report.evaluated_steps}`
      : "n/a",
    comparisonScore: detail?.eval_comparison
      ? `${detail.eval_comparison.summary.compact_passed_steps}/${detail.eval_comparison.summary.baseline_passed_steps}`
      : "n/a",
    predictor:
      detail?.eval_comparison?.predictor ?? detail?.eval_report?.predictor ?? "n/a",
  };
}

function humanizeVerdict(verdict: string) {
  if (verdict === "compact_matches_or_beats_baseline") return "Compact matches or beats baseline";
  if (verdict === "compact_matches_baseline_accuracy") return "Compact matches baseline accuracy";
  if (verdict === "compact_loses_accuracy") return "Compact loses accuracy";
  return verdict.replaceAll("_", " ");
}

function formatContextMode(mode: ReplayReport["context_mode"]) {
  if (mode === "vision_full_state") return "Vision full state";
  if (mode === "full_state") return "Full state";
  return "Compact";
}

function formatRoute(route: CompactObservation["route"]) {
  return route.replaceAll("_", " ");
}

function formatAction(action?: BrowserAction | null) {
  if (!action) return "unknown";
  if (action.type === "type") return `type ${action.target ?? ""}`;
  if (action.type === "click") return `click ${action.target ?? ""}`;
  if (action.type === "press") return `press ${action.key ?? ""}`;
  if (action.type === "goto") return `goto ${action.url ?? ""}`;
  return action.type;
}

function runFileUrl(runId: string, path: string) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `/api/runs/${encodeURIComponent(runId)}/files/${encodedPath}`;
}

createRoot(document.getElementById("root")!).render(<App />);
