"""WebSocket message interception and parsing — config-driven."""
import asyncio
import base64
import json
import re
from dataclasses import dataclass, field


@dataclass
class ParsedResponse:
    text: str = ""
    sources: list[dict] = field(default_factory=list)
    markdown: str = ""
    raw_messages: list[dict] = field(default_factory=list)
    complete: bool = False


class WebSocketParser:
    """Collects and parses WebSocket messages using pipeline config rules."""

    def __init__(
        self,
        decode_base64: bool = False,
        ignore_pattern: str | None = None,
        completion_signal: str | None = None,
    ):
        self._decode_base64 = decode_base64
        self._ignore_re = re.compile(ignore_pattern) if ignore_pattern else None
        self._completion_re = re.compile(completion_signal) if completion_signal else None
        self._messages: list[str | bytes] = []
        self._response = ParsedResponse()
        self._complete_event = asyncio.Event()

    def on_message(self, payload: str | bytes) -> None:
        """Called for each WebSocket frame received."""
        text_payload = (
            payload if isinstance(payload, str) else payload.decode("utf-8", errors="replace")
        )

        # Skip messages matching the ignore pattern (heartbeats, keepalives)
        if self._ignore_re and self._ignore_re.match(text_payload):
            return

        self._messages.append(payload)

        try:
            if self._decode_base64 and isinstance(payload, str):
                decoded = base64.b64decode(payload)
                data = json.loads(decoded)
            elif isinstance(payload, (str, bytes)):
                data = json.loads(payload)
            else:
                return

            self._response.raw_messages.append(data)
            self._extract_response_data(data, text_payload)
        except Exception:
            # Not all messages are JSON — accumulate raw text as fallback
            self._response.text += text_payload

    def _extract_response_data(self, data: dict, raw: str) -> None:
        """Extract text and check for completion signal."""
        # Accumulate any text-like fields
        for key in ("text", "bot_response", "content", "message", "response"):
            if key in data and isinstance(data[key], str):
                self._response.text += data[key]
        if "sources" in data and isinstance(data["sources"], list):
            self._response.sources.extend(data["sources"])

        # Check completion signal against the raw message
        if self._completion_re and self._completion_re.search(raw):
            self._response.complete = True
            self._complete_event.set()

    async def wait_for_completion(self, timeout: float = 30.0) -> ParsedResponse:
        try:
            await asyncio.wait_for(self._complete_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self._response.complete = True
        self._response.markdown = self._response.text
        return self._response
