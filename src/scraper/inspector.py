"""Page inspector — detects interactive elements and WebSocket connections."""
import asyncio
from dataclasses import dataclass, field

from playwright.async_api import async_playwright


@dataclass
class DetectedInput:
    selector: str
    tag: str  # "input", "textarea", "div[contenteditable]"
    type: str  # "text", "search", "number", etc.
    placeholder: str = ""
    tabindex: int | None = None
    name: str = ""
    aria_label: str = ""


@dataclass
class DetectedButton:
    selector: str
    text: str
    type: str = ""  # "submit", "button"
    aria_label: str = ""


@dataclass
class DetectedSelect:
    selector: str
    name: str = ""
    options_count: int = 0
    aria_label: str = ""


@dataclass
class DetectedWebSocket:
    url: str
    message_count: int = 0
    sample_messages: list[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    url: str
    inputs: list[DetectedInput] = field(default_factory=list)
    buttons: list[DetectedButton] = field(default_factory=list)
    selects: list[DetectedSelect] = field(default_factory=list)
    websockets: list[DetectedWebSocket] = field(default_factory=list)


class PageInspector:
    """Launches a visible browser, scans a page, and reports findings."""

    async def inspect(self, url: str, wait_seconds: int = 10) -> InspectionResult:
        result = InspectionResult(url=url)

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=False)  # visible
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Track WebSocket connections
        ws_tracker: dict[str, DetectedWebSocket] = {}

        def on_ws(ws):
            dws = DetectedWebSocket(url=ws.url)
            ws_tracker[ws.url] = dws

            def on_frame(data):
                dws.message_count += 1
                if len(dws.sample_messages) < 5:
                    dws.sample_messages.append(str(data)[:200])

            ws.on("framereceived", on_frame)

        page.on("websocket", on_ws)

        await page.goto(url, wait_until="domcontentloaded")
        # Wait for page to fully load and WS connections to establish
        await asyncio.sleep(wait_seconds)

        # Detect inputs
        inputs = await page.query_selector_all("input, textarea, [contenteditable='true']")
        for el in inputs:
            tag = await el.evaluate("el => el.tagName.toLowerCase()")
            input_type = await el.get_attribute("type") or ""
            placeholder = await el.get_attribute("placeholder") or ""
            name = await el.get_attribute("name") or ""
            tabindex = await el.get_attribute("tabindex")
            aria = await el.get_attribute("aria-label") or ""
            # Build a unique CSS selector
            selector = await el.evaluate(  # noqa: E501
                """el => {
                if (el.id) return `#${el.id}`;
                let s = el.tagName.toLowerCase();
                if (el.name) s += `[name="${el.name}"]`;
                else if (el.placeholder) s += `[placeholder="${el.placeholder}"]`;
                const aria = el.getAttribute('aria-label');
                if (!el.name && !el.placeholder && aria) s += `[aria-label="${aria}"]`;
                else if (el.tabIndex > 0) s += `[tabindex="${el.tabIndex}"]`;
                return s;
            }"""
            )
            result.inputs.append(
                DetectedInput(
                    selector=selector,
                    tag=tag,
                    type=input_type,
                    placeholder=placeholder,
                    name=name,
                    aria_label=aria,
                    tabindex=int(tabindex) if tabindex else None,
                )
            )

        # Detect buttons
        buttons = await page.query_selector_all("button, [role='button'], input[type='submit']")
        for el in buttons:
            text = (await el.inner_text()).strip()[:50]
            btn_type = await el.get_attribute("type") or ""
            aria = await el.get_attribute("aria-label") or ""
            selector = await el.evaluate(
                """el => {
                if (el.id) return `#${el.id}`;
                let s = el.tagName.toLowerCase();
                const text = el.innerText?.trim().substring(0, 30);
                if (text) s += `:has-text("${text}")`;
                return s;
            }"""
            )
            result.buttons.append(
                DetectedButton(
                    selector=selector,
                    text=text,
                    type=btn_type,
                    aria_label=aria,
                )
            )

        # Detect selects
        selects = await page.query_selector_all("select")
        for el in selects:
            name = await el.get_attribute("name") or ""
            aria = await el.get_attribute("aria-label") or ""
            opts = await el.evaluate("el => el.options.length")
            selector = await el.evaluate(
                """el => {
                if (el.id) return `#${el.id}`;
                let s = 'select';
                if (el.name) s += `[name="${el.name}"]`;
                return s;
            }"""
            )
            result.selects.append(
                DetectedSelect(
                    selector=selector,
                    name=name,
                    options_count=opts,
                    aria_label=aria,
                )
            )

        # Collect WebSocket results
        result.websockets = list(ws_tracker.values())

        await browser.close()
        await pw.stop()

        return result
