from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


ActionType = Literal["goto", "click", "type", "press", "scroll", "wait"]
FallbackType = Literal["none", "crop", "full_screenshot"]


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


class VisualDiff(BaseModel):
    changed_pct: float
    regions: list[VisualRegion] = Field(default_factory=list)


class StructuralChange(BaseModel):
    type: str
    detail: str
    before: Any | None = None
    after: Any | None = None


class CompactObservation(BaseModel):
    step: int
    action_result: str
    summary: str
    changed: list[StructuralChange] = Field(default_factory=list)
    interactive: list[InteractiveElement] = Field(default_factory=list)
    visual_changed_pct: float = 0.0
    fallback: FallbackType = "none"
    llm_observation: str
    crop_paths: list[str] = Field(default_factory=list)
    full_screenshot_path: str | None = None
    tokens_estimate: int = 0
