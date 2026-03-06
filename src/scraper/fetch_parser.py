"""HTTP response interception parser for fetch/GraphQL-based capture."""
import asyncio
import json
import re

from src.scraper.websocket_parser import ParsedResponse


class FetchResponseParser:
    """Collects and parses HTTP responses matching a URL pattern."""

    def __init__(
        self,
        url_pattern: str | None = None,
        idle_timeout: float = 5.0,
    ):
        self._url_re = re.compile(url_pattern) if url_pattern else None
        self._idle_timeout = idle_timeout
        self._responses: list[dict] = []
        self._text_parts: list[str] = []
        self._sources: list[dict] = []
        self._complete_event = asyncio.Event()
        self._timer_task: asyncio.Task | None = None
        self._collecting = False

    def start(self):
        """Begin collecting responses."""
        self._collecting = True

    async def on_response(self, response) -> None:
        """Called for each HTTP response from Playwright."""
        if not self._collecting:
            return

        url = response.url
        if self._url_re and not self._url_re.search(url):
            return

        # Only process successful JSON responses
        status = response.status
        if status < 200 or status >= 400:
            return

        try:
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type and "text" not in content_type:
                return

            body = await response.body()
            text = body.decode("utf-8", errors="replace")

            # Try SSE/streaming format first
            if "text/event-stream" in content_type:
                self._handle_streaming_text(text)
            else:
                # Try JSON
                try:
                    data = json.loads(text)
                    self._responses.append(data)
                    self._extract_text(data)
                except json.JSONDecodeError:
                    self._handle_streaming_text(text)

            # Reset idle timer (completion detected by silence)
            if self._timer_task:
                self._timer_task.cancel()
            self._timer_task = asyncio.create_task(self._idle_timer())

        except Exception:
            pass

    def _extract_text(self, data, depth: int = 0) -> None:
        """Recursively extract text from JSON response structures."""
        if depth > 8:
            return

        if isinstance(data, list):
            for item in data:
                self._extract_text(item, depth + 1)
            return

        if not isinstance(data, dict):
            return

        # Look for common text response fields
        for key in ("text", "bot_response", "content", "message", "response", "body", "snippet"):
            val = data.get(key)
            if isinstance(val, str) and len(val) > 5:
                self._text_parts.append(val)

        # Check for sources
        if "sources" in data and isinstance(data["sources"], list):
            self._sources.extend(data["sources"])

        # Recurse into nested dicts and lists
        for value in data.values():
            if isinstance(value, dict):
                self._extract_text(value, depth + 1)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._extract_text(item, depth + 1)

    def _handle_streaming_text(self, text: str) -> None:
        """Handle SSE or line-delimited streaming responses."""
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                payload = line[6:]
                if payload == "[DONE]":
                    self._complete_event.set()
                    return
                try:
                    data = json.loads(payload)
                    self._extract_text(data)
                except json.JSONDecodeError:
                    if len(payload) > 5:
                        self._text_parts.append(payload)

    async def _idle_timer(self):
        """Mark complete after no new responses for idle_timeout seconds."""
        await asyncio.sleep(self._idle_timeout)
        self._complete_event.set()

    async def wait_for_completion(self, timeout: float = 30.0) -> ParsedResponse:
        """Wait for response collection to complete."""
        try:
            await asyncio.wait_for(self._complete_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass

        full_text = "\n".join(self._text_parts) if self._text_parts else ""
        return ParsedResponse(
            text=full_text,
            sources=self._sources,
            markdown=full_text,
            raw_messages=self._responses,
            complete=True,
        )
