import React from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Coins,
  Crop,
  FileText,
  Image,
  Layers,
  Camera,
  MousePointerClick,
  RefreshCw,
  ScanLine,
  Sparkles,
  TrendingDown,
  Trophy,
  X,
  XCircle,
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

type Route = "text_only" | "crop_with_context" | "full_screenshot";

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
  route: Route;
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

const ROUTE_META: Record<
  Route,
  { label: string; blurb: string; icon: React.ReactNode }
> = {
  text_only: {
    label: "Text only",
    blurb: "Change explained in words — no image sent",
    icon: <FileText size={14} />,
  },
  crop_with_context: {
    label: "Crop + context",
    blurb: "Small cropped regions sent alongside text",
    icon: <Crop size={14} />,
  },
  full_screenshot: {
    label: "Full screenshot",
    blurb: "Whole page image sent — most expensive",
    icon: <Camera size={14} />,
  },
};

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState<string>("");
  const [detail, setDetail] = React.useState<RunDetail | null>(null);
  const [selectedStep, setSelectedStep] = React.useState(1);
  const [predictor, setPredictor] = React.useState<"heuristic" | "llm">("heuristic");
  const [status, setStatus] = React.useState("loading");
  const [busy, setBusy] = React.useState<null | string>(null);

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

  async function runAction(label: string, url: string) {
    if (!selectedRun) return;
    setBusy(label);
    try {
      await fetch(url, { method: "POST" });
      setDetail(await loadRun(selectedRun));
    } finally {
      setBusy(null);
    }
  }

  const compact = () =>
    runAction("compact", `/api/runs/${encodeURIComponent(selectedRun)}/compact`);
  const evaluate = () =>
    runAction(
      "evaluate",
      `/api/runs/${encodeURIComponent(selectedRun)}/eval?predictor=${encodeURIComponent(predictor)}`,
    );
  const compare = () =>
    runAction(
      "compare",
      `/api/runs/${encodeURIComponent(selectedRun)}/eval/compare?predictor=${encodeURIComponent(
        predictor,
      )}&baseline_context_mode=vision_full_state`,
    );

  return (
    <main className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Layers size={20} />
          </div>
          <div>
            <h1>BrowserDelta</h1>
            <p>Same agent decisions, a fraction of the tokens.</p>
          </div>
        </div>
        <div className="topbar-right">
          <div className="field">
            <label htmlFor="run">Run</label>
            <select
              id="run"
              value={selectedRun}
              onChange={(event) => setSelectedRun(event.target.value)}
            >
              {runs.length === 0 ? <option>No runs</option> : null}
              {runs.map((run) => (
                <option key={run} value={run}>
                  {run}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="predictor">Predictor</label>
            <select
              id="predictor"
              value={predictor}
              onChange={(event) => setPredictor(event.target.value as "heuristic" | "llm")}
            >
              <option value="heuristic">heuristic</option>
              <option value="llm">llm</option>
            </select>
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn"
              onClick={compact}
              disabled={!selectedRun || busy !== null}
            >
              <RefreshCw size={15} className={busy === "compact" ? "spin" : ""} />
              Compact
            </button>
            <button
              type="button"
              className="btn"
              onClick={evaluate}
              disabled={!selectedRun || busy !== null}
            >
              <CheckCircle2 size={15} className={busy === "evaluate" ? "spin" : ""} />
              Evaluate
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={compare}
              disabled={!selectedRun || busy !== null}
            >
              <Trophy size={15} className={busy === "compare" ? "spin" : ""} />
              Compare
            </button>
          </div>
          <span className="status" data-state={status === "ready" ? "ok" : "warn"}>
            {status}
          </span>
        </div>
      </header>

      {detail?.manifest ? (
        <p className="run-meta">
          <span className="chip">{detail.manifest.mode ?? "unknown"}</span>
          <span>{detail.manifest.start_url ?? "no start url"}</span>
        </p>
      ) : null}

      {detail?.eval_comparison ? (
        <VerdictBanner comparison={detail.eval_comparison} />
      ) : (
        <Intro hasDetail={Boolean(detail)} hasCompact={Boolean(detail?.compact_observations.length)} />
      )}

      <section className="kpis" aria-label="Run metrics">
        <Kpi label="Steps" value={String(stats.steps)} icon={<Layers size={16} />} />
        <Kpi
          label="Avg tokens saved"
          value={`${stats.avgReduction}%`}
          icon={<TrendingDown size={16} />}
          tone="good"
        />
        <Kpi label="Compact tokens" value={stats.compact.toLocaleString()} icon={<Coins size={16} />} />
        <Kpi
          label="Image fallbacks"
          value={String(stats.fallbacks)}
          icon={<Image size={16} />}
          tone={stats.fallbacks > 0 ? "warn" : undefined}
        />
        <Kpi
          label="Next-action score"
          value={stats.replayScore}
          icon={<CheckCircle2 size={16} />}
        />
        <Kpi label="Predictor" value={stats.predictor} icon={<Sparkles size={16} />} />
      </section>

      <section className="workspace">
        <aside className="steps">
          <div className="panel-head">
            <span className="panel-title">
              <MousePointerClick size={15} /> Steps
            </span>
            <RouteLegend />
          </div>
          {detail?.compact_observations.length ? (
            <ol className="step-list">
              {detail.compact_observations.map((observation) => {
                const replay = detail.eval_report?.steps.find(
                  (step) => step.step === observation.step,
                );
                const raw = detail.steps.find((step) => step.step === observation.step);
                return (
                  <li key={observation.step}>
                    <button
                      type="button"
                      className="step-row"
                      data-selected={observation.step === selectedStep}
                      onClick={() => setSelectedStep(observation.step)}
                    >
                      <span className="step-index">{observation.step}</span>
                      <span className="step-body">
                        <span className="step-top">
                          <ActionChip action={raw?.action} compact />
                          {replay ? <PassDot passed={replay.passed} /> : null}
                        </span>
                        <span className="step-summary">{observation.summary}</span>
                        <span className="step-foot">
                          <RouteBadge route={observation.route} small />
                          <span className="saved" data-zero={observation.reduction_pct <= 0}>
                            <TrendingDown size={12} /> {observation.reduction_pct.toFixed(0)}% saved
                          </span>
                        </span>
                      </span>
                      <ChevronRight size={16} className="step-caret" />
                    </button>
                  </li>
                );
              })}
            </ol>
          ) : (
            <p className="empty">
              No compact observations yet. Pick a run and press <strong>Compact</strong>.
            </p>
          )}
        </aside>

        <section className="detail">
          {selectedObservation ? (
            <StepDetail
              runId={selectedRun}
              observation={selectedObservation}
              rawStep={selectedRawStep}
              replayStep={selectedReplayStep}
            />
          ) : (
            <p className="empty">Select a step to inspect what the agent saw and decided.</p>
          )}
        </section>
      </section>
    </main>
  );
}

function Intro({ hasDetail, hasCompact }: { hasDetail: boolean; hasCompact: boolean }) {
  return (
    <section className="intro">
      <p className="intro-lead">
        BrowserDelta replaces full page screenshots with compact, text-first observations of
        <em> what changed</em> after each action. This view proves the agent still picks the right
        next action — while spending far fewer tokens.
      </p>
      <ol className="intro-steps">
        <li data-done={hasDetail}>
          <span className="intro-num">1</span> Pick a run
        </li>
        <li data-done={hasCompact}>
          <span className="intro-num">2</span> <strong>Compact</strong> it into observations
        </li>
        <li>
          <span className="intro-num">3</span> <strong>Compare</strong> against the screenshot baseline
        </li>
      </ol>
    </section>
  );
}

function VerdictBanner({ comparison }: { comparison: EvalComparisonReport }) {
  const summary = comparison.summary;
  const baselineLabel = formatContextMode(
    summary.baseline_context_mode ?? comparison.baseline.context_mode,
  );
  const tone = verdictTone(comparison.verdict);
  return (
    <section className={`verdict tone-${tone}`} aria-label="Eval verdict">
      <div className="verdict-main">
        <span className="verdict-eyebrow">
          <Trophy size={14} /> Eval verdict
        </span>
        <h2>{humanizeVerdict(comparison.verdict)}</h2>
        <p>
          Compact context picked the right next action{" "}
          <strong>
            {summary.compact_passed_steps}/{summary.evaluated_steps}
          </strong>{" "}
          times — matching the {baselineLabel.toLowerCase()} baseline (
          {summary.baseline_passed_steps}/{summary.evaluated_steps}) while using{" "}
          <strong>{summary.token_reduction_pct.toFixed(1)}% fewer tokens</strong>.
        </p>
      </div>

      <div className="verdict-stats">
        <div className="vstat">
          <span className="vstat-label">Accuracy parity</span>
          <span className="vstat-value">
            {pct(summary.compact_accuracy)}
            <span className="vstat-vs">vs {pct(summary.baseline_accuracy)}</span>
          </span>
        </div>
        <div className="vstat highlight">
          <span className="vstat-label">Tokens saved</span>
          <span className="vstat-value">
            {summary.token_reduction_pct.toFixed(1)}%
            <span className="vstat-vs">{summary.token_savings.toLocaleString()} tokens</span>
          </span>
        </div>
      </div>

      <div className="verdict-bars">
        <TokenBar
          label="Compact"
          tokens={summary.compact_tokens}
          max={Math.max(summary.compact_tokens, summary.baseline_tokens)}
          tone="compact"
        />
        <TokenBar
          label={baselineLabel}
          tokens={summary.baseline_tokens}
          max={Math.max(summary.compact_tokens, summary.baseline_tokens)}
          tone="baseline"
        />
      </div>
    </section>
  );
}

function TokenBar({
  label,
  tokens,
  max,
  tone,
}: {
  label: string;
  tokens: number;
  max: number;
  tone: "compact" | "baseline";
}) {
  const width = max > 0 ? Math.max((tokens / max) * 100, 2) : 0;
  return (
    <div className="token-bar">
      <span className="token-bar-label">{label}</span>
      <div className="token-track">
        <div className={`token-fill ${tone}`} style={{ width: `${width}%` }} />
      </div>
      <span className="token-bar-value">{tokens.toLocaleString()}</span>
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone?: "good" | "warn";
}) {
  return (
    <article className={`kpi${tone ? ` kpi-${tone}` : ""}`}>
      <span className="kpi-icon">{icon}</span>
      <span className="kpi-label">{label}</span>
      <strong className="kpi-value">{value}</strong>
    </article>
  );
}

function RouteLegend() {
  return (
    <div className="legend">
      {(Object.keys(ROUTE_META) as Route[]).map((route) => (
        <span key={route} className="legend-item" title={ROUTE_META[route].blurb}>
          <span className={`legend-dot route-${route}`} />
          {ROUTE_META[route].label}
        </span>
      ))}
    </div>
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
      <div className="detail-head">
        <div>
          <span className="eyebrow">Step {observation.step}</span>
          <h2>{observation.summary}</h2>
          <div className="detail-action">
            <span className="muted">Action taken</span>
            <ActionChip action={rawStep?.action} />
          </div>
        </div>
        <RouteBadge route={observation.route} />
      </div>

      {replayStep ? <DecisionCard replay={replayStep} /> : null}

      <section className="card">
        <h3 className="card-title">
          <Coins size={15} /> Compaction
        </h3>
        <p className="card-note">{observation.route_reason}</p>
        <div className="token-compare">
          <TokenBar
            label="Compact"
            tokens={observation.tokens_estimate}
            max={Math.max(observation.tokens_estimate, observation.baseline_tokens_estimate)}
            tone="compact"
          />
          <TokenBar
            label="Baseline"
            tokens={observation.baseline_tokens_estimate}
            max={Math.max(observation.tokens_estimate, observation.baseline_tokens_estimate)}
            tone="baseline"
          />
          <span className="token-saved-pill">
            <TrendingDown size={13} /> {observation.reduction_pct.toFixed(1)}% saved
          </span>
        </div>
        <dl className="metric-row">
          <Metric label="Confidence" value={`${Math.round(observation.confidence * 100)}%`} />
          <Metric label="Visual change" value={`${observation.visual_changed_pct}%`} />
          <Metric label="SSIM" value={observation.visual_ssim_score?.toFixed(3) ?? "n/a"} />
          <Metric label="pHash" value={observation.visual_phash_distance?.toString() ?? "n/a"} />
        </dl>
      </section>

      <section className="card">
        <h3 className="card-title">
          <ScanLine size={15} /> What the model read
        </h3>
        <pre className="observation">{observation.llm_observation}</pre>
      </section>

      {observation.changed.length ? (
        <section className="card">
          <h3 className="card-title">
            <Sparkles size={15} /> Detected changes
          </h3>
          <ul className="change-list">
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
        <section className="card">
          <h3 className="card-title">
            <Crop size={15} /> Visual regions
          </h3>
          <ul className="change-list">
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
        <section className="card">
          <h3 className="card-title">
            <Image size={15} /> Evidence sent to the model
          </h3>
          <div className="evidence-grid">
            {evidencePaths.map((path) => (
              <figure key={path}>
                <img src={runFileUrl(runId, path)} alt={path} loading="lazy" />
                <figcaption>{path}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}

function DecisionCard({ replay }: { replay: ReplayStepResult }) {
  return (
    <section className={`card decision ${replay.passed ? "pass" : "fail"}`}>
      <div className="decision-head">
        <h3 className="card-title">
          {replay.passed ? <Check size={15} /> : <X size={15} />} Next-action prediction
        </h3>
        <span className="verdict-pill">
          {replay.passed ? (
            <>
              <CheckCircle2 size={14} /> Match
            </>
          ) : (
            <>
              <XCircle size={14} /> Mismatch
            </>
          )}
        </span>
      </div>
      <div className="decision-compare">
        <div className="decision-col">
          <span className="muted">Expected</span>
          <ActionChip action={replay.expected_next_action} />
        </div>
        <ArrowRight size={18} className="decision-arrow" />
        <div className="decision-col">
          <span className="muted">Predicted from compact context</span>
          <ActionChip action={replay.predicted_next_action} />
        </div>
      </div>
      <p className="decision-rationale">{replay.rationale}</p>
      <p className="decision-meta">
        {replay.match_reason} · model confidence {Math.round(replay.confidence * 100)}%
      </p>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function RouteBadge({ route, small }: { route: Route; small?: boolean }) {
  const meta = ROUTE_META[route];
  return (
    <span className={`route-badge route-${route}${small ? " small" : ""}`} title={meta.blurb}>
      {meta.icon}
      {meta.label}
    </span>
  );
}

function PassDot({ passed }: { passed: boolean }) {
  return (
    <span className={`pass-dot ${passed ? "pass" : "fail"}`} title={passed ? "Match" : "Mismatch"}>
      {passed ? <Check size={11} /> : <X size={11} />}
    </span>
  );
}

function ActionChip({ action, compact }: { action?: BrowserAction | null; compact?: boolean }) {
  if (!action) return <span className="action-chip">unknown</span>;
  const target = action.target ?? action.key ?? action.url ?? "";
  return (
    <span className={`action-chip${compact ? " action-chip-sm" : ""}`}>
      <span className={`verb verb-${action.type}`}>{action.type}</span>
      {target ? <span className="action-target">{target}</span> : null}
      {action.type === "type" && action.text ? (
        <span className="action-text">“{action.text}”</span>
      ) : null}
    </span>
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
    predictor: detail?.eval_comparison?.predictor ?? detail?.eval_report?.predictor ?? "n/a",
  };
}

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function verdictTone(verdict: string): "good" | "bad" | "neutral" {
  if (verdict.includes("loses")) return "bad";
  if (verdict.includes("matches") || verdict.includes("beats")) return "good";
  return "neutral";
}

function humanizeVerdict(verdict: string) {
  if (verdict === "compact_matches_or_beats_baseline") return "Compact matches or beats the baseline";
  if (verdict === "compact_matches_baseline_accuracy") return "Compact matches baseline accuracy";
  if (verdict === "compact_loses_accuracy") return "Compact loses accuracy";
  return verdict.replaceAll("_", " ");
}

function formatContextMode(mode: ReplayReport["context_mode"]) {
  if (mode === "vision_full_state") return "Vision full-state";
  if (mode === "full_state") return "Full-state";
  return "Compact";
}

function runFileUrl(runId: string, path: string) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `/api/runs/${encodeURIComponent(runId)}/files/${encodedPath}`;
}

createRoot(document.getElementById("root")!).render(<App />);
