from __future__ import annotations

import re

from browserdelta.schemas import (
    BrowserAction,
    CompactObservation,
    InteractiveElement,
    ReplayPrediction,
)


class HeuristicReplayAgent:
    """Small deterministic agent for offline eval plumbing.

    This intentionally does not claim to be a smart browser agent. It is a
    repeatable smoke-test predictor that consumes the same compact observation
    an LLM would receive, so the replay pipeline can be tested without an API key.
    """

    name = "heuristic"

    def predict_next_action(
        self,
        goal: str,
        observation: CompactObservation,
        previous_action: BrowserAction | None = None,
        action_history: list[BrowserAction] | None = None,
    ) -> ReplayPrediction:
        text = _normalized_context(goal, observation)

        if _contains_any(text, ("required", "invalid", "validation error")):
            textbox = _first_enabled_interactive(observation, {"textbox", "searchbox"})
            if textbox:
                return ReplayPrediction(
                    action=BrowserAction(
                        type="type",
                        target=_target_label(textbox),
                        text=_email_from_goal(goal) or "test@example.com",
                    ),
                    rationale="Validation text appeared, so fill the first available textbox.",
                    confidence=0.82,
                )

        if "value changed" in text and "refresh chart" in text:
            return ReplayPrediction(
                action=BrowserAction(type="click", target="Refresh chart"),
                rationale="The field is filled and the task asks for the visual chart transition.",
                confidence=0.8,
            )

        if "visual state changed" in text or observation.fallback in {"crop", "full_screenshot"}:
            continue_button = _find_interactive(observation, role="button", name="Continue")
            if continue_button:
                return ReplayPrediction(
                    action=BrowserAction(type="click", target=_target_label(continue_button)),
                    rationale="The visual-only step completed; continue the checkout flow.",
                    confidence=0.74,
                )

        if "modal" in text or "dialog" in text:
            confirm = _find_interactive(observation, role="button", name="Confirm")
            if confirm:
                return ReplayPrediction(
                    action=BrowserAction(type="click", target=_target_label(confirm)),
                    rationale="A confirmation dialog is open.",
                    confidence=0.74,
                )

        button = _first_enabled_interactive(observation, {"button", "link"})
        if button:
            return ReplayPrediction(
                action=BrowserAction(type="click", target=_target_label(button)),
                rationale="Fallback to the first enabled command.",
                confidence=0.45,
            )

        return ReplayPrediction(
            action=BrowserAction(type="wait", amount=500),
            rationale="No obvious next control was available.",
            confidence=0.25,
        )


def actions_match(predicted: BrowserAction, expected: BrowserAction) -> tuple[bool, str]:
    if predicted.type != expected.type:
        return False, f"type mismatch: predicted {predicted.type}, expected {expected.type}"

    match predicted.type:
        case "type":
            target_match = _target_matches(predicted.target, expected.target)
            text_match = (predicted.text or "") == (expected.text or "")
            if target_match and text_match:
                return True, "type action target and text matched"
            return (
                False,
                "type mismatch: "
                f"predicted target/text {predicted.target!r}/{predicted.text!r}, "
                f"expected {expected.target!r}/{expected.text!r}",
            )
        case "click":
            if _target_matches(predicted.target, expected.target):
                return True, "click target matched"
            return (
                False,
                f"click target mismatch: predicted {predicted.target!r}, expected {expected.target!r}",
            )
        case "press":
            if (predicted.key or "") == (expected.key or ""):
                return True, "key matched"
            return False, f"key mismatch: predicted {predicted.key!r}, expected {expected.key!r}"
        case "scroll":
            return True, "scroll type matched"
        case "wait":
            return True, "wait type matched"
        case "goto":
            if (predicted.url or "") == (expected.url or ""):
                return True, "url matched"
            return False, f"url mismatch: predicted {predicted.url!r}, expected {expected.url!r}"

    return True, "action type matched"


def _normalized_context(goal: str, observation: CompactObservation) -> str:
    change_text = " ".join(change.detail for change in observation.changed)
    interactive_text = " ".join(
        f"{item.role} {item.name} {item.value or ''}" for item in observation.interactive
    )
    return _normalize(
        " ".join(
            [
                goal,
                observation.summary,
                observation.llm_observation,
                change_text,
                interactive_text,
            ]
        )
    )


def _contains_any(value: str, needles: tuple[str, ...]) -> bool:
    return any(needle in value for needle in needles)


def _first_enabled_interactive(
    observation: CompactObservation,
    roles: set[str],
) -> InteractiveElement | None:
    for item in observation.interactive:
        if _normalize(item.role) in roles and not item.disabled:
            return item
    return None


def _find_interactive(
    observation: CompactObservation,
    role: str,
    name: str,
) -> InteractiveElement | None:
    expected_role = _normalize(role)
    expected_name = _normalize(name)
    for item in observation.interactive:
        if _normalize(item.role) != expected_role or item.disabled:
            continue
        label = _normalize(_target_label(item))
        if expected_name in label:
            return item
    return None


def _target_label(item: InteractiveElement) -> str:
    attrs = item.attributes or {}
    return (
        item.name
        or str(attrs.get("aria-label") or "")
        or str(attrs.get("name") or "")
        or str(attrs.get("id") or "")
        or item.ref
    )


def _target_matches(predicted: str | None, expected: str | None) -> bool:
    predicted_norm = _normalize(predicted)
    expected_norm = _normalize(expected)
    if predicted_norm == expected_norm:
        return True
    if not predicted_norm or not expected_norm:
        return False
    return predicted_norm in expected_norm or expected_norm in predicted_norm


def _email_from_goal(goal: str) -> str | None:
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", goal)
    return match.group(0) if match else None


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().lower()
