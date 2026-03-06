"""Config-driven Playwright browser instance."""
import asyncio
import random
import re
import uuid

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from src.config import settings
from src.database.models import Pipeline
from src.scraper.fetch_parser import FetchResponseParser
from src.scraper.websocket_parser import ParsedResponse, WebSocketParser


class ScrapeInstance:
    """Generic browser instance driven by a Pipeline config."""

    def __init__(self, pipeline: Pipeline):
        self.id = f"instance-{uuid.uuid4().hex[:8]}"
        self.pipeline = pipeline
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ready = False
        self._busy = False
        self._rate_limited = False
        self._ws_parser: WebSocketParser | None = None
        self._fetch_parser: FetchResponseParser | None = None
        self._log_callback = None

    async def start(self) -> None:
        """Launch browser, navigate to target, complete onboarding."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=settings.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )

        ua = self.pipeline.user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=ua,
        )
        self._page = await self._context.new_page()

        # Attach capture listeners based on pipeline config
        if self.pipeline.capture_method == "websocket":
            self._page.on("websocket", self._on_websocket)
        elif self.pipeline.capture_method == "fetch":
            # Use async handler directly — Playwright async API supports this
            self._page.on("response", self._on_fetch_response)

        await self._navigate()
        await self._run_onboarding()
        self._ready = True

    async def _navigate(self) -> None:
        """Navigate to the target page — either directly or via Google search."""
        if self.pipeline.use_google_search and self.pipeline.google_search_term:
            await self._log("Navigating via Google search", step="navigate")
            await self._page.goto("https://www.google.com", wait_until="domcontentloaded")
            search_input = self._page.locator('textarea[name="q"], input[name="q"]')
            await search_input.fill(self.pipeline.google_search_term)
            await search_input.press("Enter")
            await self._page.wait_for_load_state("domcontentloaded")

            # Click the first matching result
            domain = (
                self.pipeline.entry_url.replace("https://", "")
                .replace("http://", "")
                .split("/")[0]
            )
            link = self._page.locator(f'a[href*="{domain}"]').first
            await link.click()
            await self._page.wait_for_load_state("domcontentloaded")
        else:
            await self._log(f"Navigating to {self.pipeline.entry_url}", step="navigate")
            await self._page.goto(
                self.pipeline.entry_url, wait_until="domcontentloaded", timeout=60000
            )

        await asyncio.sleep(4)

    async def _run_onboarding(self) -> None:
        """Execute onboarding steps from pipeline config."""
        steps = self.pipeline.onboarding_steps or []
        for i, step in enumerate(steps):
            action = step.get("action")
            selector = step.get("selector", "")
            value = step.get("value", "")
            optional = step.get("optional", False)
            timeout = step.get("timeout_ms", 5000)

            await self._log(f"Onboarding step {i + 1}: {action} {selector}", step="onboarding")
            try:
                # Actions that don't need an element
                if action == "wait":
                    ms = int(value) if value else 1000
                    await asyncio.sleep(ms / 1000)
                    await self._log(f"Step {i + 1} complete (waited {ms}ms)", step="onboarding")
                    continue
                elif action == "press":
                    await self._page.keyboard.press(value)
                    await self._log(f"Step {i + 1} complete (pressed {value})", step="onboarding")
                    continue
                elif action == "type":
                    await self._page.keyboard.type(value, delay=50)
                    await self._log(f"Step {i + 1} complete (typed)", step="onboarding")
                    continue
                elif action == "js_eval":
                    await self._page.evaluate(value)
                    await self._log(f"Step {i + 1} complete (js_eval)", step="onboarding")
                    continue

                # Actions that need a DOM element
                el = self._page.locator(selector).first
                await el.wait_for(timeout=timeout)

                if action == "click":
                    await el.click()
                elif action == "fill":
                    # Support "random_year:1995-2002" syntax
                    if value.startswith("random_year:"):
                        low, high = value.split(":")[1].split("-")
                        value = str(random.randint(int(low), int(high)))
                    await el.fill(value)
                elif action == "select":
                    if value.startswith("random_int:"):
                        low, high = value.split(":")[1].split("-")
                        value = str(random.randint(int(low), int(high)))
                    await el.select_option(value=value)

                await self._log(f"Step {i + 1} complete", step="onboarding")
                await asyncio.sleep(0.5)  # Brief settle between steps
            except Exception as e:
                if optional:
                    await self._log(
                        f"Step {i + 1} skipped (optional): {e}", step="onboarding"
                    )
                else:
                    raise RuntimeError(f"Onboarding step {i + 1} failed: {e}")

        await asyncio.sleep(2)

    def _on_websocket(self, ws) -> None:
        """Attach listener if WS URL matches pipeline's ws_url_pattern."""
        if self.pipeline.ws_url_pattern:
            if not re.search(self.pipeline.ws_url_pattern, ws.url):
                return  # Ignore WS connections that don't match
        ws.on("framereceived", lambda data: self._on_ws_frame(data))

    def _on_ws_frame(self, data: str | bytes) -> None:
        """Handle raw WebSocket frame data (bytes or str from Playwright)."""
        if self._ws_parser:
            self._ws_parser.on_message(data)

    async def _on_fetch_response(self, response) -> None:
        """Handle HTTP responses for fetch-based capture."""
        if self._fetch_parser:
            await self._fetch_parser.on_response(response)

    async def _capture_dom_response(
        self, selector: str, timeout: float, pre_submit_count: int
    ) -> ParsedResponse:
        """Poll the DOM for response text until it stabilizes."""
        await self._log(
            f"Waiting for DOM response ({selector}, pre={pre_submit_count})", step="capture"
        )
        start = asyncio.get_event_loop().time()
        last_text = ""
        stable_count = 0
        first_text_time = None
        min_wait = 5.0  # Minimum seconds to wait after first text appears

        while asyncio.get_event_loop().time() - start < timeout:
            try:
                count = await self._page.locator(selector).count()
                if count <= pre_submit_count:
                    # No new response element yet
                    await asyncio.sleep(0.5)
                    continue

                # Get text from the LAST matching element (newest response)
                el = self._page.locator(selector).last
                current_text = (await el.inner_text()).strip()

                # Ignore very short text (loading indicators, etc.)
                if len(current_text) < 3:
                    await asyncio.sleep(0.5)
                    continue

                # Track when first meaningful text appeared
                if first_text_time is None:
                    first_text_time = asyncio.get_event_loop().time()

                if current_text != last_text:
                    last_text = current_text
                    stable_count = 0
                else:
                    stable_count += 1
                    elapsed_since_first = asyncio.get_event_loop().time() - first_text_time
                    # Only accept stable text after minimum wait period
                    if stable_count >= 4 and elapsed_since_first >= min_wait:
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        cleaned = self._clean_response_text(last_text)
        return ParsedResponse(
            text=cleaned,
            markdown=cleaned,
            complete=bool(cleaned),
        )

    @staticmethod
    def _clean_response_text(text: str) -> str:
        """Remove 'Thought for N seconds' prefix and 'Sources' suffix from response."""
        lines = text.split("\n")

        # Strip leading "Thought for ..." lines (may span multiple lines)
        start = 0
        for i, line in enumerate(lines):
            stripped = line.strip().lower()
            if re.match(r"^thought for \d+\s*(second|sec|s)", stripped):
                start = i + 1
                continue
            # Skip blank lines immediately after the thought line
            if i == start and stripped == "":
                start = i + 1
                continue
            break
        lines = lines[start:]

        # Strip trailing "Sources" section
        end = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            stripped = lines[i].strip().lower()
            if stripped == "sources" or stripped == "sources:":
                end = i
                break
            # Stop searching if we hit substantial content
            if len(stripped) > 50:
                break
        lines = lines[:end]

        # Remove trailing blank lines
        while lines and lines[-1].strip() == "":
            lines.pop()

        return "\n".join(lines).strip()

    # Phrases that indicate the instance hit a rate limit
    RATE_LIMIT_PHRASES = [
        "maximum messages limit",
        "you've reached the limit",
        "rate limit",
        "try again later",
        "too many requests",
        "usage limit",
    ]

    async def submit_prompt(self, prompt: str, timeout: float = 30.0) -> ParsedResponse:
        """Submit a prompt using pipeline-configured input selector and capture method."""
        if not self._ready:
            raise RuntimeError(f"Instance {self.id} is not ready")
        if self._rate_limited:
            raise RuntimeError(f"Instance {self.id} is rate-limited — needs recycling")

        self._busy = True
        try:
            return await self._do_submit(prompt, timeout)
        finally:
            self._busy = False

    async def _do_submit(self, prompt: str, timeout: float) -> ParsedResponse:
        await self._log(f"Submitting: {prompt[:50]}...", step="prompt")

        # Set up the response parser based on capture method
        if self.pipeline.capture_method == "fetch":
            self._fetch_parser = FetchResponseParser(
                url_pattern=self.pipeline.ws_url_pattern,
                idle_timeout=5.0,
            )
            self._fetch_parser.start()
        elif self.pipeline.capture_method == "websocket":
            self._ws_parser = WebSocketParser(
                decode_base64=self.pipeline.ws_decode_base64,
                ignore_pattern=self.pipeline.ws_ignore_pattern,
                completion_signal=self.pipeline.ws_completion_signal,
            )

        # Snapshot DOM element count BEFORE submit (for dom capture)
        dom_selector = self.pipeline.dom_response_selector or "[class*='message']"
        pre_submit_count = 0
        if self.pipeline.capture_method == "dom":
            pre_submit_count = await self._page.locator(dom_selector).count()

        # Fill input using pipeline's configured selector
        input_el = self._page.locator(self.pipeline.input_selector).first
        await input_el.wait_for(state="visible", timeout=30000)
        await input_el.fill(prompt)

        # Submit using configured method
        if self.pipeline.submit_method == "click" and self.pipeline.submit_selector:
            btn = self._page.locator(self.pipeline.submit_selector).first
            await btn.wait_for(state="visible", timeout=10000)
            await btn.click()
        else:
            await input_el.press("Enter")

        # Wait for response using the appropriate capture method
        if self.pipeline.capture_method == "dom":
            result = await self._capture_dom_response(dom_selector, timeout, pre_submit_count)
        elif self.pipeline.capture_method == "fetch":
            result = await self._fetch_parser.wait_for_completion(timeout=timeout)
            self._fetch_parser = None
        else:
            result = await self._ws_parser.wait_for_completion(timeout=timeout)
            self._ws_parser = None

        # Check for rate-limit messages in the response
        lower_text = result.text.lower()
        for phrase in self.RATE_LIMIT_PHRASES:
            if phrase in lower_text:
                self._rate_limited = True
                await self._log(
                    f"Rate limited detected: {result.text[:100]}", level="WARN", step="rate_limit"
                )
                raise RuntimeError(f"Instance {self.id} rate-limited: {result.text[:80]}")

        await self._log(f"Response: {len(result.text)} chars", step="response")
        return result

    async def refresh(self) -> None:
        """Full browser restart — close context, open fresh one, re-navigate and onboard."""
        await self._log("Refreshing instance (full browser context reset)", step="refresh")
        self._rate_limited = False
        self._ready = False
        self._busy = True
        try:
            # Close existing context (clears cookies/session)
            if self._context:
                await self._context.close()

            # Create a fresh browser context + page
            ua = self.pipeline.user_agent or (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=ua,
            )
            self._page = await self._context.new_page()

            # Re-attach capture listeners
            if self.pipeline.capture_method == "websocket":
                self._page.on("websocket", self._on_websocket)
            elif self.pipeline.capture_method == "fetch":
                self._page.on("response", self._on_fetch_response)

            await self._navigate()
            await self._run_onboarding()
            self._ready = True
            await self._log("Instance refreshed and ready", step="refresh")
        except Exception as e:
            self._ready = False
            await self._log(f"Refresh failed: {e}", level="ERROR", step="refresh")
            raise
        finally:
            self._busy = False

    async def stop(self) -> None:
        self._ready = False
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        await self._log("Instance stopped", step="shutdown")

    async def _log(self, message: str, step: str = "") -> None:
        if self._log_callback:
            await self._log_callback(self.id, message, step=step)

    @property
    def is_ready(self) -> bool:
        return self._ready and not self._busy and not self._rate_limited

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limited
