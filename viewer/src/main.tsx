import React from "react";
import { createRoot } from "react-dom/client";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  FileJson,
  Gauge,
  Image,
  Loader2,
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

type StepPointer = {
  screenshot: string;
  state: string;
};

type StepRecord = {
  step: number;
  action: BrowserAction;
  result: {
    ok: boolean;
    message?: string;
    error?: string | null;
  };
  before: StepPointer;
  after: StepPointer;
};

type InteractiveElement = {
  ref: string;
  role: string;
  name?: string | null;
  value?: string | null;
  disabled?: boolean | null;
};

type PageState = {
  url?: string;
  title?: string | null;
  text?: string[];
  interactive?: InteractiveElement[];
  focused_ref?: string | null;
  console_errors?: string[];
  network_errors?: string[];
  screenshot?: string;
};

type StructuralChange = {
  type: string;
  detail: string;
};

type VisualRegion = {
  kind: string;
  area_pct: number;
  element_ref?: string | null;
  element_role?: string | null;
  element_name?: string | null;
  overlap_pct: number;
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

type ReplayStepResult = {
  step: number;
  context_mode: "compact" | "full_state" | "vision_full_state";
  observation_summary: string;
  expected_next_action: BrowserAction;
  predicted_next_action: BrowserAction;
  passed: boolean;
  match_reason: string;
  rationale: string;
  confidence: number;
  route: CompactObservation["route"];
  fallback: CompactObservation["fallback"];
  tokens_estimate: number;
  baseline_tokens_estimate: number;
  reduction_pct: number;
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

type BusyAction = "compare" | null;

const numberFormatter = new Intl.NumberFormat("en-US");
const RUN_LABELS: Record<string, string> = {
  viewer_search_filter_smoke: "Fruit Finder replay",
};

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState("");
  const [detail, setDetail] = React.useState<RunDetail | null>(null);
  const [benchmarkDetails, setBenchmarkDetails] = React.useState<RunDetail[]>([]);
  const [selectedStep, setSelectedStep] = React.useState(1);
  const [predictor, setPredictor] = React.useState<"heuristic" | "llm">("heuristic");
  const [status, setStatus] = React.useState("loading");
  const [busy, setBusy] = React.useState<BusyAction>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [afterState, setAfterState] = React.useState<PageState | null>(null);

  const refreshRunList = React.useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const response = await fetch("/api/runs");
      if (!response.ok) throw new Error(`Run index returned ${response.status}`);
      const data = (await response.json()) as RunSummary;
      const nextRuns = data.runs ?? [];
      setRuns(nextRuns);
      setSelectedRun((current) => (current && nextRuns.includes(current) ? current : nextRuns[0] ?? ""));
      const loaded = await Promise.all(nextRuns.map((runId) => loadRunQuietly(runId)));
      setBenchmarkDetails(loaded.filter((run): run is RunDetail => Boolean(run)));
      setStatus("ready");
    } catch (err) {
      setRuns([]);
      setBenchmarkDetails([]);
      setStatus("api unavailable");
      setError(errorMessage(err));
    }
  }, []);

  React.useEffect(() => {
    void refreshRunList();
  }, [refreshRunList]);

  React.useEffect(() => {
    if (!selectedRun) {
      setDetail(null);
      return;
    }
    const controller = new AbortController();
    setStatus("loading run");
    setError(null);
    loadRun(selectedRun, controller.signal)
      .then((run) => {
        setDetail(run);
        setSelectedStep((current) => clampStep(current, run));
        setStatus("ready");
      })
      .catch((err) => {
        if (controller.signal.aborted) return;
        setDetail(null);
        setStatus("run unavailable");
        setError(errorMessage(err));
      });
    return () => controller.abort();
  }, [selectedRun]);

  const selectedRawStep = detail?.steps.find((step) => step.step === selectedStep) ?? null;
  const observation =
    detail?.compact_observations.find((item) => item.step === selectedStep) ?? null;
  const comparison = detail?.eval_comparison ?? null;
  const compactStep = findReplayStep(
    comparison?.compact ?? detail?.eval_report,
    selectedStep,
  );
  const baselineReport =
    comparison?.baseline ??
    detail?.eval_vision_full_state_report ??
    detail?.eval_full_state_report ??
    null;
  const baselineStep = findReplayStep(baselineReport, selectedStep);

  React.useEffect(() => {
    if (!selectedRun || !selectedRawStep) {
      setAfterState(null);
      return;
    }
    const controller = new AbortController();
    fetch(runFileUrl(selectedRun, selectedRawStep.after.state), { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`State returned ${response.status}`);
        return response.json();
      })
      .then((state) => setAfterState(state as PageState))
      .catch(() => {
        if (!controller.signal.aborted) setAfterState(null);
      });
    return () => controller.abort();
  }, [selectedRun, selectedRawStep]);

  const summary = buildSummary(detail);
  const compactTokens = compactStep?.tokens_estimate ?? summary.compactTokens;
  const baselineTokens = baselineStep?.tokens_estimate ?? summary.baselineTokens;
  const stepSavings = tokenReductionPct(baselineTokens, compactTokens);
  const currentAction = selectedRawStep?.action ?? null;
  const nextAction = compactStep?.predicted_next_action ?? baselineStep?.predicted_next_action ?? null;

  async function refreshSelectedRun() {
    if (!selectedRun) return;
    const run = await loadRun(selectedRun);
    setDetail(run);
    setBenchmarkDetails((current) =>
      current.map((item) => (item.run_id === selectedRun ? run : item)),
    );
  }

  async function runAction(kind: BusyAction, request: () => Promise<Response>) {
    if (!kind) return;
    setBusy(kind);
    setError(null);
    try {
      const response = await request();
      if (!response.ok) throw new Error((await response.text()) || response.statusText);
      await refreshSelectedRun();
      setStatus("ready");
    } catch (err) {
      setError(errorMessage(err));
      setStatus("action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Replay evaluator</p>
          <h1>BrowserDelta replay</h1>
        </div>
      </header>

      <section className="controls" aria-label="Replay setup">
        <label>
          <span>Recorded task</span>
          <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
            {runs.map((run) => (
              <option key={run} value={run}>
                {formatRunLabel(run)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Scoring method</span>
          <select
            value={predictor}
            onChange={(event) => setPredictor(event.target.value as "heuristic" | "llm")}
          >
            <option value="heuristic">Rule-based check</option>
            <option value="llm">LLM check</option>
          </select>
        </label>
        <div className="control-actions">
          <button
            type="button"
            onClick={() =>
              void runAction("compare", () =>
                fetch(
                  `/api/runs/${encodeURIComponent(
                    selectedRun,
                  )}/eval/compare?predictor=${encodeURIComponent(predictor)}`,
                  { method: "POST" },
                ),
              )
            }
            disabled={!selectedRun || busy !== null}
          >
            {busy === "compare" ? <Loader2 className="spin" size={16} /> : <Gauge size={16} />}
            Run side-by-side eval
          </button>
        </div>
      </section>

      <StatusLine status={status} error={error} detail={detail} />

      {detail ? (
        <>
          <section className="step-strip" aria-label="Recorded steps">
            {detail.steps.map((step) => {
              const result = findReplayStep(comparison?.compact ?? detail.eval_report, step.step);
              const selected = step.step === selectedStep;
              return (
                <button
                  key={step.step}
                  type="button"
                  className={selected ? "step-pill selected" : "step-pill"}
                  onClick={() => setSelectedStep(step.step)}
                >
                  <span>{step.step}</span>
                  <strong>{formatAction(step.action)}</strong>
                  <small>
                    {result ? `${formatPct(result.reduction_pct)} saved` : "recorded action"}
                  </small>
                </button>
              );
            })}
          </section>

          <section className="story-grid">
            <BrowserFrame
              runId={selectedRun}
              step={selectedRawStep}
              observation={observation}
              afterState={afterState}
            />

            <div className="comparison-panel">
              <div className="section-heading">
                <p className="eyebrow">Step {selectedStep}</p>
                <h2>
                  {currentAction ? formatAction(currentAction) : "Select a step"}
                  {nextAction ? (
                    <>
                      <ArrowRight size={18} />
                      {formatAction(nextAction)}
                    </>
                  ) : null}
                </h2>
              </div>

              <div className="payload-grid">
                <PayloadCard
                  kind="full"
                  title="Non-compact context"
                  subtitle={baselineLabel(baselineReport?.context_mode)}
                  tokens={baselineTokens}
                  step={baselineStep}
                >
                  <FullStateSummary state={afterState} step={selectedRawStep} runId={selectedRun} />
                </PayloadCard>

                <PayloadCard
                  kind="compact"
                  title="BrowserDelta context"
                  subtitle={observation?.route.replaceAll("_", " ") ?? "compact delta"}
                  tokens={compactTokens}
                  savings={stepSavings}
                  step={compactStep}
                >
                  <CompactSummary observation={observation} />
                </PayloadCard>
              </div>
            </div>
          </section>

          <section className="detail-row">
            <TokenLedger compactTokens={compactTokens} baselineTokens={baselineTokens} />
            <BenchmarkSummary runs={benchmarkDetails} />
          </section>
        </>
      ) : (
        <EmptyState status={status} />
      )}
    </main>
  );
}

function StatusLine({
  status,
  error,
  detail,
}: {
  status: string;
  error: string | null;
  detail: RunDetail | null;
}) {
  return (
    <div className={error ? "status-line error" : "status-line"}>
      {error ? <AlertCircle size={16} /> : <CheckCircle2 size={16} />}
      <span>{error ? error : `${status}${detail ? ` · ${formatRunLabel(detail.run_id)}` : ""}`}</span>
    </div>
  );
}

function BrowserFrame({
  runId,
  step,
  observation,
  afterState,
}: {
  runId: string;
  step: StepRecord | null;
  observation: CompactObservation | null;
  afterState: PageState | null;
}) {
  if (!step) {
    return (
      <section className="browser-panel">
        <EmptyState status="No step selected" />
      </section>
    );
  }

  return (
    <section className="browser-panel">
      <div className="browser-header">
        <div>
          <p className="eyebrow">Recorded browser state</p>
          <h2>{afterState?.title || "Browser after action"}</h2>
        </div>
        <span>{observation ? `${formatPct(observation.visual_changed_pct)} visual change` : ""}</span>
      </div>
      <div className="browser-window">
        <div className="window-bar">
          <span />
          <span />
          <span />
          <strong>{formatAction(step.action)}</strong>
        </div>
        <img
          src={runFileUrl(runId, step.after.screenshot)}
          alt={`Browser after step ${step.step}`}
        />
      </div>
      <p className="browser-caption">
        {observation?.summary ?? "The recorded page state after this browser action."}
      </p>
    </section>
  );
}

function PayloadCard({
  kind,
  title,
  subtitle,
  tokens,
  savings,
  step,
  children,
}: {
  kind: "full" | "compact";
  title: string;
  subtitle: string;
  tokens: number;
  savings?: number;
  step: ReplayStepResult | null;
  children: React.ReactNode;
}) {
  return (
    <article className={`payload-card ${kind}`}>
      <div className="payload-header">
        <div>
          <p className="eyebrow">{subtitle}</p>
          <h3>{title}</h3>
        </div>
        <div className="token-badge">
          <strong>{numberFormatter.format(tokens)}</strong>
          <span>tokens</span>
        </div>
      </div>

      {children}

      <div className={step?.passed ? "prediction pass" : "prediction"}>
        <span>Predicted next action</span>
        <strong>{step ? formatAction(step.predicted_next_action) : "not evaluated"}</strong>
        <small>
          {step
            ? `${step.passed ? "pass" : "miss"} · ${formatPct(step.confidence * 100)} confidence`
            : "run the side-by-side eval to score this step"}
        </small>
      </div>

      {typeof savings === "number" ? (
        <div className="savings-bar" aria-label={`${formatPct(savings)} token savings`}>
          <span style={{ width: `${Math.min(100, Math.max(0, savings))}%` }} />
        </div>
      ) : null}
    </article>
  );
}

function FullStateSummary({
  state,
  step,
  runId,
}: {
  state: PageState | null;
  step: StepRecord | null;
  runId: string;
}) {
  const textCount = state?.text?.length ?? 0;
  const interactiveCount = state?.interactive?.length ?? 0;
  return (
    <div className="payload-body">
      <div className="summary-list">
        <SummaryItem icon={<Image />} label="Screenshot" value={step?.after.screenshot ?? "missing"} />
        <SummaryItem icon={<FileJson />} label="Page state" value={step?.after.state ?? "missing"} />
        <SummaryItem label="Visible text nodes" value={String(textCount)} />
        <SummaryItem label="Interactive elements" value={String(interactiveCount)} />
      </div>
      <details>
        <summary>Show full-state contents</summary>
        <div className="detail-columns">
          <div>
            <strong>Visible text</strong>
            <ul>
              {(state?.text ?? []).slice(0, 8).map((text, index) => (
                <li key={`${text}-${index}`}>{text}</li>
              ))}
            </ul>
          </div>
          <div>
            <strong>Interactive</strong>
            <ul>
              {(state?.interactive ?? []).slice(0, 8).map((item) => (
                <li key={item.ref}>
                  {item.ref} · {item.role} · {item.name || item.value || "unnamed"}
                </li>
              ))}
            </ul>
          </div>
        </div>
        {step ? (
          <a href={runFileUrl(runId, step.after.state)} target="_blank" rel="noreferrer">
            Open raw state JSON
          </a>
        ) : null}
      </details>
    </div>
  );
}

function CompactSummary({ observation }: { observation: CompactObservation | null }) {
  if (!observation) {
    return <p className="muted">Run compaction to create a delta for this step.</p>;
  }

  const visibleChanges = observation.changed.slice(0, 4);
  return (
    <div className="payload-body">
      <p className="plain-delta">{observation.summary}</p>
      <div className="summary-list compact-list">
        <SummaryItem label="Route" value={observation.route.replaceAll("_", " ")} />
        <SummaryItem label="Fallback" value={observation.fallback} />
        <SummaryItem label="Confidence" value={formatPct(observation.confidence * 100)} />
        <SummaryItem label="Visual regions" value={String(observation.visual_regions.length)} />
      </div>
      {visibleChanges.length ? (
        <ul className="change-list">
          {visibleChanges.map((change, index) => (
            <li key={`${change.type}-${index}`}>
              <span>{change.type.replaceAll("_", " ")}</span>
              {change.detail}
            </li>
          ))}
        </ul>
      ) : null}
      <details>
        <summary>Show raw compact prompt payload</summary>
        <pre>{observation.llm_observation}</pre>
      </details>
    </div>
  );
}

function SummaryItem({
  icon,
  label,
  value,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="summary-item">
      {icon ? <span>{icon}</span> : null}
      <small>{label}</small>
      <strong>{value}</strong>
    </div>
  );
}

function TokenLedger({
  compactTokens,
  baselineTokens,
}: {
  compactTokens: number;
  baselineTokens: number;
}) {
  const saved = Math.max(0, baselineTokens - compactTokens);
  const pct = tokenReductionPct(baselineTokens, compactTokens);
  return (
    <section className="mini-panel">
      <p className="eyebrow">Payload size</p>
      <h2>{numberFormatter.format(saved)} tokens removed from this step.</h2>
      <div className="ledger-row">
        <span>Compact</span>
        <strong>{numberFormatter.format(compactTokens)}</strong>
      </div>
      <div className="ledger-row">
        <span>Non-compact</span>
        <strong>{numberFormatter.format(baselineTokens)}</strong>
      </div>
      <div className="savings-bar large">
        <span style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </div>
      <p className="muted">{formatPct(pct)} reduction for the selected step.</p>
    </section>
  );
}

function BenchmarkSummary({ runs }: { runs: RunDetail[] }) {
  const rows = runs
    .map((run) => run.eval_comparison)
    .filter((comparison): comparison is EvalComparisonReport => Boolean(comparison));
  const totals = rows.reduce(
    (acc, report) => {
      acc.evaluated += report.summary.evaluated_steps;
      acc.compact += report.summary.compact_passed_steps;
      acc.baseline += report.summary.baseline_passed_steps;
      acc.compactTokens += report.summary.compact_tokens;
      acc.baselineTokens += report.summary.baseline_tokens;
      return acc;
    },
    { evaluated: 0, compact: 0, baseline: 0, compactTokens: 0, baselineTokens: 0 },
  );
  const reduction = tokenReductionPct(totals.baselineTokens, totals.compactTokens);

  return (
    <section className="mini-panel">
      <p className="eyebrow">Saved eval output</p>
      <h2>
        {totals.evaluated} recorded steps compared
      </h2>
      <p className="muted">
        Compact passed {totals.compact}/{totals.evaluated}; full-state passed {totals.baseline}/
        {totals.evaluated}; compact payload saved {formatPct(reduction)}.
      </p>
      <div className="run-table">
        {rows.slice(0, 4).map((report) => (
          <div key={report.run_id}>
            <strong>{formatRunLabel(report.run_id)}</strong>
            <span>
              compact {report.summary.compact_passed_steps}/{report.summary.evaluated_steps} · full{" "}
              {report.summary.baseline_passed_steps}/{report.summary.evaluated_steps} ·{" "}
              {formatPct(report.summary.token_reduction_pct)} saved
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyState({ status }: { status: string }) {
  return (
    <section className="empty-state">
      <h2>No run loaded</h2>
      <p>{status}. Record or compact a run, then refresh this viewer.</p>
    </section>
  );
}

async function loadRun(runId: string, signal?: AbortSignal): Promise<RunDetail> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { signal });
  if (!response.ok) throw new Error(`Run ${runId} returned ${response.status}`);
  return (await response.json()) as RunDetail;
}

async function loadRunQuietly(runId: string): Promise<RunDetail | null> {
  try {
    return await loadRun(runId);
  } catch {
    return null;
  }
}

function buildSummary(detail: RunDetail | null) {
  const comparison = detail?.eval_comparison;
  if (comparison) {
    return {
      evaluated: comparison.summary.evaluated_steps,
      compactPassed: comparison.summary.compact_passed_steps,
      baselinePassed: comparison.summary.baseline_passed_steps,
      compactTokens: comparison.summary.compact_tokens,
      baselineTokens: comparison.summary.baseline_tokens,
      tokenReductionPct: comparison.summary.token_reduction_pct,
    };
  }

  const report = detail?.eval_report;
  const compactTokens =
    report?.compact_tokens ??
    detail?.compact_observations.reduce((total, item) => total + item.tokens_estimate, 0) ??
    0;
  const baselineTokens =
    report?.baseline_tokens ??
    detail?.compact_observations.reduce((total, item) => total + item.baseline_tokens_estimate, 0) ??
    0;
  return {
    evaluated: report?.evaluated_steps ?? Math.max(0, (detail?.steps.length ?? 1) - 1),
    compactPassed: report?.passed_steps ?? 0,
    baselinePassed: 0,
    compactTokens,
    baselineTokens,
    tokenReductionPct: tokenReductionPct(baselineTokens, compactTokens),
  };
}

function findReplayStep(report: ReplayReport | null | undefined, step: number) {
  return report?.steps.find((item) => item.step === step) ?? null;
}

function clampStep(step: number, run: RunDetail) {
  const validSteps = run.steps.map((item) => item.step);
  if (validSteps.includes(step)) return step;
  return validSteps[0] ?? 1;
}

function baselineLabel(mode?: ReplayReport["context_mode"]) {
  if (mode === "vision_full_state") return "screenshot plus full page state";
  if (mode === "full_state") return "full page state";
  return "full browser payload";
}

function formatAction(action: BrowserAction | null | undefined): string {
  if (!action) return "not available";
  if (action.type === "type") {
    const text = action.text ? ` "${action.text}"` : "";
    return `type ${action.target || "field"}${text}`;
  }
  if (action.type === "click") return `click ${action.target || "target"}`;
  if (action.type === "press") return `press ${action.key || action.target || "key"}`;
  if (action.type === "goto") return `open ${action.url || action.target || "url"}`;
  return action.type;
}

function tokenReductionPct(baseline: number, compact: number) {
  if (!baseline) return 0;
  return Math.max(0, ((baseline - compact) / baseline) * 100);
}

function formatPct(value: number) {
  return `${Number.isFinite(value) ? value.toFixed(1) : "0.0"}%`;
}

function formatRunLabel(runId: string) {
  return (
    RUN_LABELS[runId] ??
    runId
      .replace(/^viewer_/, "")
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ")
  );
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

function runFileUrl(runId: string, path: string) {
  const encodedPath = path
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `/api/runs/${encodeURIComponent(runId)}/files/${encodedPath}`;
}

createRoot(document.getElementById("root")!).render(<App />);
