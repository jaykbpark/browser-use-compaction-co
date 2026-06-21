from __future__ import annotations

import json
from typing import Any

import pytest

from browserdelta.eval.llm_agent import LLMReplayAgent
from browserdelta.schemas import BrowserAction, CompactObservation, InteractiveElement


def test_llm_replay_agent_posts_structured_responses_request():
    captured: dict[str, Any] = {}

    def fake_transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "status": "completed",
            "output_text": (
                '{"type":"type","target":"Email","text":"jay@example.com",'
                '"key":null,"amount":null,"url":null,'
                '"rationale":"The validation message asks for an email.",'
                '"confidence":0.91}'
            ),
        }

    agent = LLMReplayAgent(
        api_key="test-key",
        model="test-model",
        base_url="https://api.test/v1",
        transport=fake_transport,
    )
    observation = CompactObservation(
        step=1,
        action_result="success",
        summary="New text appeared: Email is required",
        llm_observation="Email is required. Current interactive elements: e1 textbox: Email",
        interactive=[InteractiveElement(ref="e1", role="textbox", name="Email")],
        tokens_estimate=10,
        baseline_tokens_estimate=100,
        reduction_pct=90,
    )

    prediction = agent.predict_next_action(
        "Use jay@example.com as the email.",
        observation,
        previous_action=None,
        action_history=[BrowserAction(type="click", target="Continue")],
    )

    assert prediction.action.type == "type"
    assert prediction.action.target == "Email"
    assert prediction.action.text == "jay@example.com"
    assert prediction.confidence == 0.91
    assert captured["url"] == "https://api.test/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["store"] is False
    assert captured["payload"]["text"]["format"]["type"] == "json_schema"
    assert captured["payload"]["text"]["format"]["strict"] is True
    assert captured["payload"]["text"]["format"]["schema"]["additionalProperties"] is False
    context = json.loads(captured["payload"]["input"][1]["content"])
    assert "previous_action_already_taken" in context
    assert context["action_history_so_far"] == [
        {
            "type": "click",
            "target": "Continue",
            "text": None,
            "key": None,
            "amount": None,
            "url": None,
            "metadata": {},
        }
    ]


def test_llm_replay_agent_can_attach_full_screenshot_as_input_image(tmp_path):
    captured: dict[str, Any] = {}

    def fake_transport(
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> dict[str, Any]:
        captured["payload"] = payload
        return {
            "status": "completed",
            "output_text": (
                '{"type":"click","target":"Continue","text":null,'
                '"key":null,"amount":null,"url":null,'
                '"rationale":"The screenshot shows the Continue button.",'
                '"confidence":0.83}'
            ),
        }

    screenshot = tmp_path / "steps" / "step_001_after.png"
    screenshot.parent.mkdir(parents=True)
    screenshot.write_bytes(b"fake image bytes")
    observation = CompactObservation(
        step=1,
        action_result="success",
        summary="Full browser state after click.",
        llm_observation="FULL STATE BASELINE CONTEXT\nScreenshot: steps/step_001_after.png",
        full_screenshot_path="steps/step_001_after.png",
        interactive=[InteractiveElement(ref="e1", role="button", name="Continue")],
    )

    agent = LLMReplayAgent(
        api_key="test-key",
        model="test-model",
        transport=fake_transport,
        artifact_root=tmp_path,
        include_images=True,
    )

    prediction = agent.predict_next_action("Continue.", observation)

    assert prediction.action.type == "click"
    assert agent.name == "llm-vision:test-model"
    content = captured["payload"]["input"][1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "input_text"
    assert json.loads(content[0]["text"].split("\n\n", 1)[0])["observation"][
        "vision_image_attached"
    ]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/png;base64,")


def test_llm_replay_agent_requires_api_key():
    agent = LLMReplayAgent(api_key="", model="test-model", transport=_unused_transport)
    observation = CompactObservation(
        step=1,
        action_result="success",
        summary="Ready",
        llm_observation="Ready",
    )

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        agent.predict_next_action("Do the task.", observation)


def _unused_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    raise AssertionError("transport should not be called")
