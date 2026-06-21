import React from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  Gauge,
  Image,
  RefreshCw,
  ScanLine,
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
  checked?: boolean | null;
  selected?: boolean | null;
  expanded?: boolean | null;
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

type BusyAction = "compact" | "evaluate" | "compare" | null;

const numberFormatter = new Intl.NumberFormat("en-US");

function App() {
  const [runs, setRuns] = React.useState<string[]>([]);
  const [selectedRun, setSelectedRun] = React.useState<string>("");
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
    let cancelled = false;
    setError(null);
    loadRun(selectedRun)
      .then((run) => {
        if (cancelled) return;
        setDetail(run);
        const firstStep = run.steps[0]?.step ?? run.compact_observations[0]?.step ?? 1;
        setSelectedStep((current) =>
          run.steps.some((step) => step.step === current) ||
          run.compact_observations.some((observation) => observation.step === current)
            ? current
            : firstStep,
        );
      })
      .catch((err) => {
        if (cancelled) return;
        setDetail(null);
        setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRun]);

  const selectedRawStep =
    detail?.steps.find((step) => step.step === selectedStep) ?? detail?.steps[0] ?? null;
  const selectedObservation =
    detail?.compact_observations.find((observation) => observation.step === selectedStep) ?? null;
  const compactReport = compactReplayReport(detail);
  const visionReport = visionReplayReport(detail);
  const compactReplayStep = findReplayStep(compactReport, selectedStep);
  const visionReplayStep = findReplayStep(visionReport, selectedStep);
  const stats = summarizeRun(detail);

  React.useEffect(() => {
    if (!selectedRun || !selectedRawStep?.after.state) {
      setAfterState(null);
      return;
    }
    const controller = new AbortController();
    fetch(runFileUrl(selectedRun, selectedRawStep.after.state), { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((state: PageState | null) => setAfterState(state))
      .catch((err) => {
        if ((err as Error).name !== "AbortError") setAfterState(null);
      });
    return () => controller.abort();
  }, [selectedRun, selectedRawStep?.after.state]);

  async function refreshSelectedRun(runId: string) {
    const run = await loadRun(runId);
    setDetail(run);
    setBenchmarkDetails((current) => upsertRunDetail(current, run));
  }

  async function runAction(action: Exclude<BusyAction, null>, request: () => Promise<Response>) {
    if (!selectedRun || busy) return;
    setBusy(action);
    setError(null);
    try {
      const response = await request();
      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || `${action} failed with ${response.status}`);
      }
      await refreshSelectedRun(selectedRun);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const selectedStepLabel = selectedRawStep
    ? `Step ${selectedRawStep.step}`
    : selectedObservation
      ? `Step ${selectedObservation.step}`
      : "No step";

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">BrowserDelta Demo Viewer</p>
          <h1>Vision Full State vs Compact Delta</h1>
        </div>
        <div className="status-group">
          {detail?.eval_comparison ? (
            <span className="comparison-verdict">{humanizeVerdict(detail.eval_comparison.verdict)}</span>
          ) : null}
          <div className="status-pill" data-state={status === "ready" ? "ok" : "warn"}>
            {status === "ready" ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
            <span>{status}</span>
          </div>
        </div>
      </header>

      <section className="control-strip" aria-label="Run controls">
        <label>
          Run
          <select value={selectedRun} onChange={(event) => setSelectedRun(event.target.value)}>
            {runs.length === 0 ? <option value="">No runs in runs/</option> : null}
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
        <button
          type="button"
          onClick={() =>
            runAction("compact", () =>
              fetch(`/api/runs/${encodeURIComponent(selectedRun)}/compact`, { method: "POST" }),
            )
          }
          disabled={!selectedRun || Boolean(busy)}
        >
          <RefreshCw size={15} />
          {busy === "compact" ? "Compacting" : "Compact"}
        </button>
        <button
          type="button"
          onClick={() =>
            runAction("evaluate", () =>
              fetch(
                `/api/runs/${encodeURIComponent(selectedRun)}/eval?predictor=${encodeURIComponent(
                  predictor,
                )}`,
                { method: "POST" },
              ),
            )
          }
          disabled={!selectedRun || Boolean(busy)}
        >
          <CheckCircle2 size={15} />
          {busy === "evaluate" ? "Evaluating" : "Evaluate"}
        </button>
        <button
          type="button"
          onClick={() =>
            runAction("compare", () =>
              fetch(
                `/api/runs/${encodeURIComponent(
                  selectedRun,
                )}/eval/compare?predictor=${encodeURIComponent(
                  predictor,
                )}&baseline_context_mode=vision_full_state`,
                { method: "POST" },
              ),
            )
          }
          disabled={!selectedRun || Boolean(busy)}
        >
          <Gauge size={15} />
          {busy === "compare" ? "Comparing" : "Compare"}
        </button>
        <button type="button" className="ghost-button" onClick={() => void refreshRunList()}>
          <Activity size={15} />
          Refresh
        </button>
      </section>

      {detail?.manifest ? (
        <p className="run-line">
          <span>{detail.manifest.mode ?? "unknown runtime"}</span>
          <span>{detail.manifest.start_url ?? "no start url"}</span>
        </p>
      ) : null}
      {error ? <p className="error-line">{error}</p> : null}

      <section className="metric-strip" aria-label="Run metrics">
        <Metric icon={<Activity size={17} />} label="Recorded Steps" value={String(stats.steps)} />
        <Metric icon={<Gauge size={17} />} label="Overall Savings" value={stats.overallReduction} />
        <Metric icon={<FileText size={17} />} label="Compact Tokens" value={stats.compactTokens} />
        <Metric icon={<Image size={17} />} label="Baseline Tokens" value={stats.baselineTokens} />
        <Metric icon={<CheckCircle2 size={17} />} label="Compact Score" value={stats.compactScore} />
        <Metric icon={<ScanLine size={17} />} label="Vision Score" value={stats.visionScore} />
      </section>

      <section className="step-rail" aria-label="Step selection">
        {detail?.steps.length ? (
          detail.steps.map((step) => {
            const observation = detail.compact_observations.find((item) => item.step === step.step);
            const compactStep = findReplayStep(compactReport, step.step);
            const visionStep = findReplayStep(visionReport, step.step);
            return (
              <button
                key={step.step}
                type="button"
                className="step-chip"
                data-selected={step.step === selectedStep}
                onClick={() => setSelectedStep(step.step)}
              >
                <span>{step.step}</span>
                <strong>{formatAction(step.action)}</strong>
                <small>
                  {observation ? `${formatPercent(observation.reduction_pct)} saved` : "not compacted"}
                  {compactStep || visionStep ? ` · ${scorePair(compactStep, visionStep)}` : ""}
                </small>
              </button>
            );
          })
        ) : (
          <p className="empty">No recorded steps were returned by the API.</p>
        )}
      </section>

      <section className="comparison-grid" aria-label="Selected step comparison">
        <BrowserFrame
          runId={selectedRun}
          stepLabel={selectedStepLabel}
          step={selectedRawStep}
          observation={selectedObservation}
        />
        <section className="context-stack" aria-label="AI contexts">
          <ContextCard
            tone="baseline"
            title="Vision Full State Baseline"
            eyebrow="after screenshot + full PageState"
            icon={<Image size={17} />}
            predictedStep={visionReplayStep}
            report={visionReport}
            tokenLabel={visionReplayStep ? `${formatNumber(visionReplayStep.tokens_estimate)} tokens` : "not evaluated"}
          >
            <FullStatePreview state={afterState} step={selectedRawStep} />
          </ContextCard>
          <ContextCard
            tone="compact"
            title="Compact Delta"
            eyebrow={selectedObservation ? formatRoute(selectedObservation.route) : "compact_observations.jsonl"}
            icon={<Cpu size={17} />}
            predictedStep={compactReplayStep}
            report={compactReport}
            tokenLabel={
              selectedObservation
                ? `${formatNumber(selectedObservation.tokens_estimate)} tokens · ${formatPercent(
                    selectedObservation.reduction_pct,
                  )} saved`
                : "not compacted"
            }
          >
            <CompactPreview observation={selectedObservation} />
          </ContextCard>
        </section>
      </section>

      <section className="detail-grid" aria-label="Step evidence">
        <TokenLedger observation={selectedObservation} compactStep={compactReplayStep} visionStep={visionReplayStep} />
        <ChangePanel observation={selectedObservation} />
      </section>

      <BenchmarkChart runs={benchmarkDetails} />
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

function BrowserFrame({
  runId,
  stepLabel,
  step,
  observation,
}: {
  runId: string;
  stepLabel: string;
  step: StepRecord | null;
  observation: CompactObservation | null;
}) {
  const screenshotPath = step?.after.screenshot ?? observation?.full_screenshot_path ?? "";
  return (
    <section className="browser-frame">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">{stepLabel}</p>
          <h2>Browser After State</h2>
        </div>
        <span className="screenshot-path">{screenshotPath || "no screenshot"}</span>
      </div>
      <div className="browser-toolbar" aria-hidden="true">
        <span />
        <span />
        <span />
        <strong>{step ? formatAction(step.action) : "no action"}</strong>
      </div>
      <div className="screenshot-stage">
        {runId && screenshotPath ? (
          <img src={runFileUrl(runId, screenshotPath)} alt={`${stepLabel} after screenshot`} />
        ) : (
          <div className="empty-stage">
            <Image size={24} />
            <span>No after-screenshot pointer for this step.</span>
          </div>
        )}
      </div>
      <div className="frame-footer">
        <span>{observation ? observation.summary : "Compact observation has not been generated."}</span>
        {observation ? <strong>{formatPercent(observation.visual_changed_pct)} visual delta</strong> : null}
      </div>
    </section>
  );
}

function ContextCard({
  tone,
  title,
  eyebrow,
  icon,
  predictedStep,
  report,
  tokenLabel,
  children,
}: {
  tone: "baseline" | "compact";
  title: string;
  eyebrow: string;
  icon: React.ReactNode;
  predictedStep: ReplayStepResult | null;
  report: ReplayReport | null;
  tokenLabel: string;
  children: React.ReactNode;
}) {
  return (
    <article className="context-card" data-tone={tone}>
      <div className="context-card-header">
        <div className="context-title">
          {icon}
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h2>{title}</h2>
          </div>
        </div>
        <span className="token-pill">{tokenLabel}</span>
      </div>
      <div className="context-body">{children}</div>
      <div className="prediction-box" data-state={predictionState(predictedStep)}>
        <div>
          <span>Predicted next action</span>
          <strong>{predictedStep ? formatAction(predictedStep.predicted_next_action) : predictionFallback(report)}</strong>
        </div>
        {predictedStep ? (
          <dl>
            <div>
              <dt>Result</dt>
              <dd>{predictedStep.passed ? "pass" : "fail"}</dd>
            </div>
            <div>
              <dt>Confidence</dt>
              <dd>{formatPercent(predictedStep.confidence * 100)}</dd>
            </div>
          </dl>
        ) : null}
      </div>
      {predictedStep?.rationale ? <p className="rationale">{predictedStep.rationale}</p> : null}
    </article>
  );
}

function FullStatePreview({ state, step }: { state: PageState | null; step: StepRecord | null }) {
  const text = state?.text ?? [];
  const interactive = state?.interactive ?? [];
  return (
    <div className="state-preview">
      <dl className="compact-kv">
        <div>
          <dt>Screenshot</dt>
          <dd>{step?.after.screenshot ?? "n/a"}</dd>
        </div>
        <div>
          <dt>State JSON</dt>
          <dd>{step?.after.state ?? "n/a"}</dd>
        </div>
        <div>
          <dt>URL</dt>
          <dd>{state?.url ?? "not loaded"}</dd>
        </div>
        <div>
          <dt>Title</dt>
          <dd>{state?.title || "untitled"}</dd>
        </div>
      </dl>
      <div className="state-columns">
        <div>
          <h3>Visible Text ({text.length})</h3>
          <ul>
            {text.slice(0, 5).map((line, index) => (
              <li key={`${line}-${index}`}>{line}</li>
            ))}
            {text.length > 5 ? <li>{text.length - 5} more text nodes</li> : null}
          </ul>
        </div>
        <div>
          <h3>Interactive ({interactive.length})</h3>
          <ul>
            {interactive.slice(0, 5).map((item) => (
              <li key={item.ref}>
                <code>{item.ref}</code> {item.role}: {item.name || item.value || "(unnamed)"}
              </li>
            ))}
            {interactive.length > 5 ? <li>{interactive.length - 5} more elements</li> : null}
          </ul>
        </div>
      </div>
    </div>
  );
}

function CompactPreview({ observation }: { observation: CompactObservation | null }) {
  if (!observation) {
    return <p className="empty">Run compaction to load the compact delta context for this step.</p>;
  }
  return (
    <div className="compact-preview">
      <dl className="compact-kv">
        <div>
          <dt>Route</dt>
          <dd>{formatRoute(observation.route)}</dd>
        </div>
        <div>
          <dt>Fallback</dt>
          <dd>{observation.fallback}</dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{formatPercent(observation.confidence * 100)}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{observation.route_reason}</dd>
        </div>
      </dl>
      <pre>{observation.llm_observation}</pre>
    </div>
  );
}

function TokenLedger({
  observation,
  compactStep,
  visionStep,
}: {
  observation: CompactObservation | null;
  compactStep: ReplayStepResult | null;
  visionStep: ReplayStepResult | null;
}) {
  const compactTokens = observation?.tokens_estimate ?? compactStep?.tokens_estimate ?? 0;
  const baselineTokens =
    observation?.baseline_tokens_estimate ?? visionStep?.tokens_estimate ?? compactStep?.baseline_tokens_estimate ?? 0;
  const savings = Math.max(0, baselineTokens - compactTokens);
  const pct = baselineTokens ? (savings / baselineTokens) * 100 : 0;
  return (
    <section className="ledger-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Per-step token ledger</p>
          <h2>Compact vs Vision Payload</h2>
        </div>
        <Database size={18} />
      </div>
      <dl className="ledger-grid">
        <div>
          <dt>Compact</dt>
          <dd>{formatNumber(compactTokens)}</dd>
        </div>
        <div>
          <dt>Vision Full State</dt>
          <dd>{formatNumber(baselineTokens)}</dd>
        </div>
        <div>
          <dt>Saved</dt>
          <dd>{formatNumber(savings)}</dd>
        </div>
        <div>
          <dt>Reduction</dt>
          <dd>{formatPercent(pct)}</dd>
        </div>
      </dl>
      <div className="savings-bar" aria-label={`Token reduction ${formatPercent(pct)}`}>
        <span style={{ width: `${clampPct(pct)}%` }} />
      </div>
    </section>
  );
}

function ChangePanel({ observation }: { observation: CompactObservation | null }) {
  return (
    <section className="change-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Delta evidence</p>
          <h2>Changed Surfaces</h2>
        </div>
        <BarChart3 size={18} />
      </div>
      {observation ? (
        <>
          <dl className="ledger-grid visual-metrics">
            <div>
              <dt>Filtered Pixels</dt>
              <dd>{formatPercent(observation.visual_changed_pct)}</dd>
            </div>
            <div>
              <dt>Raw Pixels</dt>
              <dd>{formatPercent(observation.visual_raw_changed_pct)}</dd>
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
          <div className="change-lists">
            <EvidenceList title="Structural" items={observation.changed.map((item) => [item.type, item.detail])} />
            <EvidenceList
              title="Visual regions"
              items={observation.visual_regions.map((region) => [
                region.kind,
                `${region.element_name || region.element_ref || "unmatched area"} · ${formatPercent(
                  region.area_pct,
                )} area`,
              ])}
            />
          </div>
        </>
      ) : (
        <p className="empty">No compact evidence is available for the selected step.</p>
      )}
    </section>
  );
}

function EvidenceList({ title, items }: { title: string; items: string[][] }) {
  return (
    <div className="evidence-list">
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.slice(0, 8).map(([kind, detail], index) => (
            <li key={`${kind}-${index}`}>
              <code>{kind}</code>
              <span>{detail}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">None recorded.</p>
      )}
    </div>
  );
}

function BenchmarkChart({ runs }: { runs: RunDetail[] }) {
  const comparedRuns = runs.filter((run) => run.eval_comparison);
  return (
    <section className="benchmark-panel" aria-label="Benchmark comparison chart">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">eval_comparison.json across runs</p>
          <h2>Benchmark Matrix</h2>
        </div>
        <BarChart3 size={18} />
      </div>
      {comparedRuns.length ? (
        <div className="benchmark-table">
          {comparedRuns.map((run) => {
            const comparison = run.eval_comparison!;
            const summary = comparison.summary;
            const baselineLabel = formatContextMode(
              summary.baseline_context_mode ?? comparison.baseline.context_mode,
            );
            return (
              <article className="benchmark-row" key={run.run_id}>
                <div className="benchmark-name">
                  <strong>{run.run_id}</strong>
                  <span>{comparison.predictor}</span>
                </div>
                <div className="bar-cell">
                  <span>Compact accuracy</span>
                  <div className="bar-track">
                    <span className="bar-compact" style={{ width: `${clampPct(summary.compact_accuracy * 100)}%` }} />
                  </div>
                  <strong>{formatPercent(summary.compact_accuracy * 100)}</strong>
                </div>
                <div className="bar-cell">
                  <span>{baselineLabel} accuracy</span>
                  <div className="bar-track">
                    <span className="bar-baseline" style={{ width: `${clampPct(summary.baseline_accuracy * 100)}%` }} />
                  </div>
                  <strong>{formatPercent(summary.baseline_accuracy * 100)}</strong>
                </div>
                <div className="bar-cell savings">
                  <span>Token reduction</span>
                  <div className="bar-track">
                    <span className="bar-savings" style={{ width: `${clampPct(summary.token_reduction_pct)}%` }} />
                  </div>
                  <strong>{formatPercent(summary.token_reduction_pct)}</strong>
                </div>
                <div className="benchmark-tokens">
                  <span>{formatNumber(summary.compact_tokens)} compact</span>
                  <span>{formatNumber(summary.baseline_tokens)} baseline</span>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="empty">
          No loaded run has `eval_comparison.json`. Use Compare after selecting a compacted run.
        </p>
      )}
    </section>
  );
}

async function loadRun(runId: string): Promise<RunDetail> {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) throw new Error(`Failed to load run ${runId}`);
  return response.json();
}

async function loadRunQuietly(runId: string): Promise<RunDetail | null> {
  try {
    return await loadRun(runId);
  } catch {
    return null;
  }
}

function upsertRunDetail(runs: RunDetail[], run: RunDetail) {
  const next = runs.filter((item) => item.run_id !== run.run_id);
  next.push(run);
  return next.sort((left, right) => left.run_id.localeCompare(right.run_id));
}

function summarizeRun(detail: RunDetail | null) {
  const observations = detail?.compact_observations ?? [];
  const compactTokens = observations.reduce((total, observation) => total + observation.tokens_estimate, 0);
  const baselineTokens = observations.reduce(
    (total, observation) => total + observation.baseline_tokens_estimate,
    0,
  );
  const comparison = detail?.eval_comparison;
  const compactReport = compactReplayReport(detail);
  const visionReport = visionReplayReport(detail);
  const savingsPct =
    comparison?.summary.token_reduction_pct ??
    (baselineTokens ? ((baselineTokens - compactTokens) / baselineTokens) * 100 : 0);
  return {
    steps: detail?.steps.length ?? 0,
    overallReduction: observations.length || comparison ? formatPercent(savingsPct) : "n/a",
    compactTokens: formatNumber(comparison?.summary.compact_tokens ?? compactTokens),
    baselineTokens: formatNumber(comparison?.summary.baseline_tokens ?? baselineTokens),
    compactScore: compactReport ? `${compactReport.passed_steps}/${compactReport.evaluated_steps}` : "n/a",
    visionScore: visionReport ? `${visionReport.passed_steps}/${visionReport.evaluated_steps}` : "n/a",
  };
}

function compactReplayReport(detail: RunDetail | null): ReplayReport | null {
  return detail?.eval_comparison?.compact ?? detail?.eval_report ?? null;
}

function visionReplayReport(detail: RunDetail | null): ReplayReport | null {
  const comparisonBaseline = detail?.eval_comparison?.baseline;
  if (comparisonBaseline?.context_mode === "vision_full_state") return comparisonBaseline;
  return detail?.eval_vision_full_state_report ?? null;
}

function findReplayStep(report: ReplayReport | null, step: number) {
  return report?.steps.find((item) => item.step === step) ?? null;
}

function scorePair(compactStep: ReplayStepResult | null, visionStep: ReplayStepResult | null) {
  const compact = compactStep ? (compactStep.passed ? "C pass" : "C fail") : "C n/a";
  const vision = visionStep ? (visionStep.passed ? "V pass" : "V fail") : "V n/a";
  return `${compact}/${vision}`;
}

function predictionState(step: ReplayStepResult | null) {
  if (!step) return "missing";
  return step.passed ? "pass" : "fail";
}

function predictionFallback(report: ReplayReport | null) {
  if (!report) return "not evaluated";
  return "no scored next action for this step";
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
  if (action.type === "type") {
    const text = action.text ? ` "${action.text}"` : "";
    return `type ${action.target ?? "target"}${text}`;
  }
  if (action.type === "click") return `click ${action.target ?? "target"}`;
  if (action.type === "press") return `press ${action.key ?? "key"}`;
  if (action.type === "goto") return `goto ${action.url ?? "url"}`;
  if (action.type === "scroll") return `scroll ${action.amount ?? ""}`.trim();
  return action.type;
}

function runFileUrl(runId: string, path: string) {
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `/api/runs/${encodeURIComponent(runId)}/files/${encodedPath}`;
}

function formatNumber(value: number) {
  if (!Number.isFinite(value)) return "0";
  return numberFormatter.format(Math.round(value));
}

function formatPercent(value: number, digits = 1) {
  if (!Number.isFinite(value)) return "n/a";
  return `${value.toFixed(digits)}%`;
}

function clampPct(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function errorMessage(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}

createRoot(document.getElementById("root")!).render(<App />);
