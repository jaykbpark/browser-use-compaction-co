from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


ActionType = Literal["goto", "click", "type", "press", "scroll", "wait"]
FallbackType = Literal["none", "crop", "full_screenshot"]
RouteType = Literal["text_only", "crop_with_context", "full_screenshot"]
ReplayContextMode = Literal["compact", "full_state", "vision_full_state"]


class BrowserAction(BaseModel):
    type: ActionType
    target: str | None = None
    text: str | None = None
    key: str | None = None
    amount: int | None = None
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionResult(BaseModel):
    ok: bool
    message: str = ""
    error: str | None = None


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class InteractiveElement(BaseModel):
    ref: str
    role: str
    name: str = ""
    value: str | None = None
    disabled: bool | None = None
    checked: bool | None = None
    selected: bool | None = None
    expanded: bool | None = None
    bbox: BoundingBox | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class PageState(BaseModel):
    url: str
    title: str = ""
    text: list[str] = Field(default_factory=list)
    interactive: list[InteractiveElement] = Field(default_factory=list)
    focused_ref: str | None = None
    console_errors: list[str] = Field(default_factory=list)
    network_errors: list[str] = Field(default_factory=list)
    screenshot: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StatePointer(BaseModel):
    screenshot: str
    state: str


class StepRecord(BaseModel):
    step: int
    action: BrowserAction
    result: ActionResult
    before: StatePointer
    after: StatePointer


class RunManifest(BaseModel):
    run_id: str
    start_url: str
    mode: Literal["local", "browserbase"]
    steps_path: str = "steps.jsonl"
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisualRegion(BaseModel):
    bbox: BoundingBox
    kind: str = "changed_region"
    crop_path: str | None = None
    area_pct: float = 0.0
    element_ref: str | None = None
    element_role: str | None = None
    element_name: str | None = None
    overlap_pct: float = 0.0
    ocr_text: str | None = None


class VisualDiff(BaseModel):
    changed_pct: float
    regions: list[VisualRegion] = Field(default_factory=list)
    raw_changed_pct: float = 0.0
    ssim_score: float | None = None
    perceptual_hash_distance: int | None = None


class StructuralChange(BaseModel):
    type: str
    detail: str
    before: Any | None = None
    after: Any | None = None


class RouteDecision(BaseModel):
    route: RouteType = "text_only"
    fallback: FallbackType = "none"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = ""


class CompactObservation(BaseModel):
    step: int
    action_result: str
    summary: str
    changed: list[StructuralChange] = Field(default_factory=list)
    interactive: list[InteractiveElement] = Field(default_factory=list)
    visual_changed_pct: float = 0.0
    visual_raw_changed_pct: float = 0.0
    visual_ssim_score: float | None = None
    visual_phash_distance: int | None = None
    fallback: FallbackType = "none"
    route: RouteType = "text_only"
    route_reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    llm_observation: str
    crop_paths: list[str] = Field(default_factory=list)
    full_screenshot_path: str | None = None
    visual_regions: list[VisualRegion] = Field(default_factory=list)
    tokens_estimate: int = 0
    baseline_tokens_estimate: int = 0
    reduction_pct: float = 0.0


class ReplayPrediction(BaseModel):
    action: BrowserAction
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ReplayStepResult(BaseModel):
    step: int
    context_mode: ReplayContextMode = "compact"
    observation_summary: str
    expected_next_action: BrowserAction
    predicted_next_action: BrowserAction
    passed: bool
    match_reason: str
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    route: RouteType = "text_only"
    fallback: FallbackType = "none"
    tokens_estimate: int = 0
    baseline_tokens_estimate: int = 0
    reduction_pct: float = 0.0


class ReplayReport(BaseModel):
    run_id: str
    predictor: str
    context_mode: ReplayContextMode = "compact"
    evaluated_steps: int
    passed_steps: int
    next_action_accuracy: float
    compact_tokens: int
    baseline_tokens: int
    avg_reduction_pct: float
    steps: list[ReplayStepResult] = Field(default_factory=list)


class EvalComparisonSummary(BaseModel):
    run_id: str
    predictor: str
    baseline_context_mode: ReplayContextMode = "full_state"
    evaluated_steps: int
    compact_passed_steps: int
    baseline_passed_steps: int
    compact_accuracy: float
    baseline_accuracy: float
    accuracy_delta: float
    compact_tokens: int
    baseline_tokens: int
    token_savings: int
    token_reduction_pct: float


class EvalComparisonReport(BaseModel):
    run_id: str
    predictor: str
    compact: ReplayReport
    baseline: ReplayReport
    summary: EvalComparisonSummary
    verdict: str
    explanation: list[str] = Field(default_factory=list)
