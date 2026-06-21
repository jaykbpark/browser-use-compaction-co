from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from browserdelta.config import get_settings
from browserdelta.schemas import BrowserAction, CompactObservation, ReplayPrediction


Transport = Callable[[str, dict[str, Any], dict[str, str], float], dict[str, Any]]


class LLMReplayAgent:
    """Replay predictor backed by the OpenAI Responses API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: Transport | None = None,
        artifact_root: Path | None = None,
        include_images: bool = False,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")
        self.timeout = timeout
        self.transport = transport or _post_json
        self.artifact_root = artifact_root
        self.include_images = include_images
        self.name = f"llm-vision:{self.model}" if include_images else f"llm:{self.model}"

    def predict_next_action(
        self,
        goal: str,
        observation: CompactObservation,
        previous_action: BrowserAction | None = None,
        action_history: list[BrowserAction] | None = None,
    ) -> ReplayPrediction:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required for --predictor llm")

        image_url = self._image_data_url(observation) if self.include_images else None
        context = _compact_context(
            goal,
            observation,
            previous_action,
            action_history=action_history,
            vision_image_attached=bool(image_url),
        )
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _user_content(context, image_url),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "browser_action_prediction",
                    "schema": _ACTION_SCHEMA,
                    "strict": True,
                }
            },
            "temperature": 0,
            "store": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        with _llm_prediction_span(
            model=self.model,
            context=context,
            include_images=self.include_images,
            vision_image_attached=bool(image_url),
        ) as span:
            try:
                response = self.transport(
                    f"{self.base_url}/responses",
                    payload,
                    headers,
                    self.timeout,
                )
                parsed = _LLMActionPayload.model_validate(_extract_json_payload(response))
            except Exception as exc:
                _record_span_error(span, exc)
                raise
            _record_llm_prediction(span, parsed)
        return ReplayPrediction(
            action=BrowserAction(
                type=parsed.type,
                target=parsed.target,
                text=parsed.text,
                key=parsed.key,
                amount=parsed.amount,
                url=parsed.url,
            ),
            rationale=parsed.rationale,
            confidence=parsed.confidence,
        )

    def _image_data_url(self, observation: CompactObservation) -> str | None:
        if not observation.full_screenshot_path:
            raise RuntimeError("Vision replay requires observation.full_screenshot_path.")
        if self.artifact_root is None:
            raise RuntimeError("Vision replay requires artifact_root to resolve screenshots.")

        root = self.artifact_root.resolve()
        image_path = (root / observation.full_screenshot_path).resolve()
        try:
            image_path.relative_to(root)
        except ValueError as exc:
            raise RuntimeError(
                "Vision replay screenshot path must stay inside the run folder."
            ) from exc
        if not image_path.exists():
            raise RuntimeError(
                f"Vision replay screenshot not found: {observation.full_screenshot_path}"
            )

        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"


class _LLMActionPayload(BaseModel):
    type: str
    target: str | None = None
    text: str | None = None
    key: str | None = None
    amount: int | None = None
    url: str | None = None
    rationale: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


_SYSTEM_PROMPT = """You are a browser-agent replay judge.
You receive the task goal and one compact browser observation captured after an action.
You also receive the previous action that already produced this observation.
When provided, you receive action_history_so_far: all browser actions already completed.
Predict the single next browser action that should happen after that observation.

Rules:
- Return only the structured JSON action payload.
- Use target names exactly as they appear in interactive_elements when possible.
- Do not repeat previous_action unless the observation and goal clearly require repeating it.
- For ordered tasks, use action_history_so_far to determine which requested step comes next.
- Choose one action type: goto, click, type, press, scroll, or wait.
- For type actions, include the exact text to type.
- Do not describe the current observation; predict the next action.
"""


_ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "type": {"type": "string", "enum": ["goto", "click", "type", "press", "scroll", "wait"]},
        "target": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "key": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "amount": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
        "url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["type", "target", "text", "key", "amount", "url", "rationale", "confidence"],
}


def _compact_context(
    goal: str,
    observation: CompactObservation,
    previous_action: BrowserAction | None,
    action_history: list[BrowserAction] | None = None,
    vision_image_attached: bool = False,
) -> dict[str, Any]:
    return {
        "goal": goal,
        "previous_action_already_taken": (
            previous_action.model_dump(mode="json") if previous_action else None
        ),
        "action_history_so_far": [
            action.model_dump(mode="json") for action in (action_history or [])
        ],
        "observation": {
            "step": observation.step,
            "action_result": observation.action_result,
            "summary": observation.summary,
            "llm_observation": observation.llm_observation,
            "route": observation.route,
            "fallback": observation.fallback,
            "route_reason": observation.route_reason,
            "visual_changed_pct": observation.visual_changed_pct,
            "changes": [
                {
                    "type": change.type,
                    "detail": change.detail,
                    "before": change.before,
                    "after": change.after,
                }
                for change in observation.changed
            ],
            "interactive_elements": [
                {
                    "ref": item.ref,
                    "role": item.role,
                    "name": item.name,
                    "value": item.value,
                    "disabled": item.disabled,
                }
                for item in observation.interactive
            ],
            "crop_paths": observation.crop_paths,
            "full_screenshot_path": observation.full_screenshot_path,
            "vision_image_attached": vision_image_attached,
        },
    }


def _user_content(context: dict[str, Any], image_url: str | None) -> str | list[dict[str, str]]:
    context_text = json.dumps(context)
    if not image_url:
        return context_text
    return [
        {
            "type": "input_text",
            "text": (
                context_text
                + "\n\nThe after-action browser screenshot is attached as an input_image."
            ),
        },
        {"type": "input_image", "image_url": image_url},
    ]


def _post_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    last_error: urllib.error.URLError | None = None
    for attempt in range(3):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                raise RuntimeError(
                    f"OpenAI API request failed with HTTP {exc.code}: {error_body}"
                ) from exc
            time.sleep(0.5 * (attempt + 1))
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.5 * (attempt + 1))

    reason = last_error.reason if last_error else "unknown error"
    raise RuntimeError(f"OpenAI API request failed: {reason}")


@contextmanager
def _llm_prediction_span(
    *,
    model: str,
    context: dict[str, Any],
    include_images: bool,
    vision_image_attached: bool,
):
    try:
        from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
        from opentelemetry import trace
    except ImportError:
        yield None
        return

    tracer = trace.get_tracer("browserdelta.eval.llm")
    with tracer.start_as_current_span("browserdelta.llm.predict_next_action") as span:
        span.set_attribute(
            SpanAttributes.OPENINFERENCE_SPAN_KIND,
            OpenInferenceSpanKindValues.LLM.value,
        )
        span.set_attribute(SpanAttributes.INPUT_VALUE, json.dumps(context, ensure_ascii=True))
        span.set_attribute("llm.provider", "openai")
        span.set_attribute("llm.model_name", model)
        span.set_attribute("browserdelta.include_images", include_images)
        span.set_attribute("browserdelta.vision_image_attached", vision_image_attached)
        yield span


def _record_llm_prediction(span, parsed: _LLMActionPayload) -> None:
    if span is None:
        return
    output = {
        "type": parsed.type,
        "target": parsed.target,
        "text": parsed.text,
        "key": parsed.key,
        "amount": parsed.amount,
        "url": parsed.url,
        "rationale": parsed.rationale,
        "confidence": parsed.confidence,
    }
    span.set_attribute("output.value", json.dumps(output, ensure_ascii=True, sort_keys=True))
    span.set_attribute("browserdelta.predicted_action.type", parsed.type)
    span.set_attribute("browserdelta.predicted_action.target", parsed.target or "")
    span.set_attribute("browserdelta.confidence", parsed.confidence)
    _set_span_status(span, ok=True)


def _record_span_error(span, exc: Exception) -> None:
    if span is None:
        return
    record_exception = getattr(span, "record_exception", None)
    if callable(record_exception):
        record_exception(exc)
    _set_span_status(span, ok=False, description=str(exc))


def _set_span_status(span, ok: bool, description: str = "") -> None:
    try:
        from opentelemetry.trace import Status, StatusCode
    except ImportError:
        return
    if ok:
        span.set_status(Status(StatusCode.OK))
    else:
        span.set_status(Status(StatusCode.ERROR, description))


def _extract_json_payload(response: dict[str, Any]) -> dict[str, Any]:
    if response.get("status") == "incomplete":
        reason = (response.get("incomplete_details") or {}).get("reason", "unknown")
        raise RuntimeError(f"OpenAI response was incomplete: {reason}")

    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _loads_json_object(output_text)

    for item in response.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                raise RuntimeError("OpenAI model refused to produce an action prediction.")
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return _loads_json_object(text)

    raise RuntimeError("OpenAI response did not contain output_text JSON.")


def _loads_json_object(value: str) -> dict[str, Any]:
    cleaned = _strip_code_fence(value.strip())
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("LLM response JSON must be an object.")
    return data


def _strip_code_fence(value: str) -> str:
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.DOTALL)
    return match.group(1) if match else value
