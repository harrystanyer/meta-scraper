"""Cloro-compatible request/response schemas + pipeline config schemas."""
from pydantic import BaseModel, Field


class IncludeOptions(BaseModel):
    markdown: bool = True
    rawResponse: bool = False


class MonitorRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10000)
    country: str = Field(default="US", max_length=5)
    include: IncludeOptions = Field(default_factory=IncludeOptions)


class Source(BaseModel):
    url: str = ""
    label: str = ""
    description: str = ""


class MonitorResult(BaseModel):
    text: str = ""
    sources: list[Source] = []
    markdown: str = ""
    rawResponse: list[dict] = []
    model: str = ""


class MonitorResponse(BaseModel):
    success: bool
    result: MonitorResult | None = None
    error: str | None = None


class TaskStatusResponse(BaseModel):
    task: dict
    response: MonitorResponse | None = None


# --- Pipeline schemas ---


class OnboardingStep(BaseModel):
    action: str  # "click", "fill", "select", "wait"
    selector: str = ""
    value: str = ""
    optional: bool = False
    timeout_ms: int = 5000


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    entry_url: str
    use_google_search: bool = False
    google_search_term: str | None = None
    onboarding_steps: list[OnboardingStep] = []
    input_selector: str
    submit_method: str = "enter_key"
    submit_selector: str | None = None
    capture_method: str = "websocket"
    ws_url_pattern: str | None = None
    ws_decode_base64: bool = False
    ws_ignore_pattern: str | None = None
    ws_completion_signal: str | None = None
    dom_response_selector: str | None = None
    user_agent: str | None = None


class InspectRequest(BaseModel):
    url: str
    wait_seconds: int = Field(default=10, ge=3, le=30)
