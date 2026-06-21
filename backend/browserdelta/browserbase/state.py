from __future__ import annotations

from pathlib import Path

from playwright.async_api import Page

from browserdelta.schemas import BoundingBox, InteractiveElement, PageState


async def capture_state(
    page: Page,
    screenshot_path: Path,
    screenshot_ref: str | None = None,
    console_errors: list[str] | None = None,
    network_errors: list[str] | None = None,
) -> PageState:
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(path=str(screenshot_path), full_page=False)

    payload = await page.evaluate(_STATE_CAPTURE_SCRIPT)
    interactive = [
        InteractiveElement(
            ref=item["ref"],
            role=item["role"],
            name=item.get("name", ""),
            value=item.get("value"),
            disabled=item.get("disabled"),
            checked=item.get("checked"),
            selected=item.get("selected"),
            expanded=item.get("expanded"),
            bbox=BoundingBox(**item["bbox"]) if item.get("bbox") else None,
            attributes=item.get("attributes", {}),
        )
        for item in payload["interactive"]
    ]

    return PageState(
        url=page.url,
        title=await page.title(),
        text=payload["text"],
        interactive=interactive,
        focused_ref=payload.get("focused_ref"),
        console_errors=console_errors or [],
        network_errors=network_errors or [],
        screenshot=screenshot_ref or str(screenshot_path),
        metadata={"capture_version": 1},
    )


_STATE_CAPTURE_SCRIPT = r"""
() => {
  const visible = (el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.visibility !== 'hidden' && style.display !== 'none' &&
      rect.width > 0 && rect.height > 0;
  };

  const roleFor = (el) => {
    if (el.getAttribute('role')) return el.getAttribute('role');
    const tag = el.tagName.toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return 'link';
    if (tag === 'input') {
      const type = (el.getAttribute('type') || 'text').toLowerCase();
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'submit' || type === 'button') return 'button';
      return 'textbox';
    }
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return 'combobox';
    if (tag === 'canvas') return 'canvas';
    if (tag === 'svg') return 'svg';
    if (tag === 'img') return 'img';
    return tag;
  };

  const nameFor = (el) => {
    const explicitLabel = el.id
      ? Array.from(document.querySelectorAll('label')).find((label) => label.htmlFor === el.id)?.innerText
      : '';
    return (
      explicitLabel ||
      el.getAttribute('data-browserdelta-label') ||
      el.getAttribute('title') ||
      el.getAttribute('aria-labelledby') && document.getElementById(el.getAttribute('aria-labelledby'))?.innerText ||
      el.getAttribute('aria-label') ||
      el.getAttribute('placeholder') ||
      el.getAttribute('name') ||
      el.getAttribute('alt') ||
      el.innerText ||
      el.value ||
      el.textContent ||
      ''
    ).trim().replace(/\s+/g, ' ').slice(0, 160);
  };

  const selector = [
    'button',
    'a',
    'input',
    'textarea',
    'select',
    '[role]',
    '[contenteditable="true"]',
    'canvas',
    'svg',
    'img',
    '[data-browserdelta-visual]'
  ].join(',');
  const nodes = Array.from(document.querySelectorAll(selector)).filter(visible).slice(0, 120);
  const interactive = nodes.map((el, index) => {
    const rect = el.getBoundingClientRect();
    const ref = `e${index + 1}`;
    el.setAttribute('data-browserdelta-ref', ref);
    return {
      ref,
      role: roleFor(el),
      name: nameFor(el),
      value: 'value' in el ? String(el.value).slice(0, 160) : null,
      disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      checked: 'checked' in el ? Boolean(el.checked) : null,
      selected: 'selected' in el ? Boolean(el.selected) : null,
      expanded: el.getAttribute('aria-expanded') === null ? null : el.getAttribute('aria-expanded') === 'true',
      bbox: {x: rect.x, y: rect.y, width: rect.width, height: rect.height},
      attributes: {
        id: el.id || null,
        name: el.getAttribute('name'),
        'aria-label': el.getAttribute('aria-label'),
        'data-testid': el.getAttribute('data-testid'),
        'data-test': el.getAttribute('data-test'),
        'data-browserdelta-label': el.getAttribute('data-browserdelta-label'),
        'data-browserdelta-visual': el.getAttribute('data-browserdelta-visual'),
        type: el.getAttribute('type'),
        href: el.getAttribute('href'),
      }
    };
  });

  let focused_ref = null;
  if (document.activeElement) {
    focused_ref = document.activeElement.getAttribute('data-browserdelta-ref');
  }

  const bodyText = (document.body?.innerText || '')
    .split('\n')
    .map((line) => line.trim().replace(/\s+/g, ' '))
    .filter(Boolean)
    .slice(0, 80);

  return {interactive, focused_ref, text: bodyText};
}
"""
