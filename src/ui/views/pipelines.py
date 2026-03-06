"""Pipelines — config builder with page inspector."""
import json

import flet as ft
import httpx


class PipelinesView(ft.Column):
    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__(expand=True, scroll=ft.ScrollMode.AUTO, spacing=16)
        self.api_base = api_base
        self._editing_id: str | None = None

        # Pipeline list
        self.pipeline_list = ft.Column(spacing=4)

        # Form fields
        self.name_field = self._field("Name", "meta-ai")
        self.description_field = self._field("Description", "Meta AI scraper")
        self.entry_url_field = self._field("Entry URL", "https://www.meta.ai")
        self.google_search_check = ft.Checkbox(
            label="Navigate via Google search", value=False
        )
        self.google_term_field = self._field("Google search term", "meta.ai")
        self.input_selector_field = self._field("Input selector", "input[tabindex]")
        self.submit_method = ft.Dropdown(
            label="Submit method",
            value="enter_key",
            width=200,
            options=[
                ft.DropdownOption(key="enter_key", text="enter_key"),
                ft.DropdownOption(key="click", text="click"),
            ],
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
        )
        self.submit_selector_field = self._field("Submit button selector", "")
        self.capture_method = ft.Dropdown(
            label="Capture method",
            value="websocket",
            width=200,
            options=[
                ft.DropdownOption(key="websocket", text="websocket"),
                ft.DropdownOption(key="dom", text="dom"),
            ],
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
        )
        self.ws_url_pattern_field = self._field("WS URL pattern (regex)", ".*")
        self.ws_decode_base64_check = ft.Checkbox(label="Decode base64", value=False)
        self.ws_ignore_field = self._field("WS ignore pattern (regex)", "^.{0,20}$")
        self.ws_completion_field = self._field("WS completion signal (regex)", "")
        self.onboarding_json = ft.TextField(
            label="Onboarding steps (JSON array)",
            multiline=True,
            min_lines=3,
            max_lines=8,
            expand=True,
            value="[]",
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            text_style=ft.TextStyle(font_family="monospace"),
        )

        # Inspector section
        self.inspect_url_field = self._field("URL to inspect", "https://www.meta.ai")
        self.inspect_btn = ft.OutlinedButton(
            content="Inspect Page",
            style=ft.ButtonStyle(color="#FFFFFF", side=ft.BorderSide(1, "#FFFFFF")),
            on_click=self._on_inspect,
        )
        self.inspect_status = ft.Text("", size=12, color="#555555")
        self.inspect_results = ft.Column(spacing=8)

        # Action buttons
        self.save_btn = ft.OutlinedButton(
            content="Save Pipeline",
            style=ft.ButtonStyle(color="#FFFFFF", side=ft.BorderSide(1, "#FFFFFF")),
            on_click=self._on_save,
        )
        self.new_btn = ft.TextButton(
            content="New",
            style=ft.ButtonStyle(color="#888888"),
            on_click=lambda _: self._reset_form(),
        )

        self.controls = [
            ft.Container(
                content=ft.Text(
                    "Pipelines", size=24, weight=ft.FontWeight.BOLD, color="#FFFFFF"
                ),
                padding=ft.Padding(0, 0, 0, 8),
            ),
            ft.Text("Saved Pipelines", size=14, color="#888888"),
            self.pipeline_list,
            ft.Container(
                content=ft.Divider(height=1, color="#222222"),
                padding=ft.Padding(0, 8, 0, 8),
            ),
            # Inspector
            ft.Text(
                "Page Inspector", size=16, weight=ft.FontWeight.W_600, color="#888888"
            ),
            ft.Text(
                "Launch a browser to auto-detect inputs, buttons, and WebSocket connections.",
                size=12,
                color="#555555",
            ),
            ft.Row(
                controls=[
                    self.inspect_url_field,
                    self.inspect_btn,
                    self.inspect_status,
                ],
                spacing=12,
            ),
            self.inspect_results,
            ft.Container(
                content=ft.Divider(height=1, color="#222222"),
                padding=ft.Padding(0, 8, 0, 8),
            ),
            # Config form
            ft.Text(
                "Pipeline Configuration",
                size=16,
                weight=ft.FontWeight.W_600,
                color="#888888",
            ),
            ft.Row(
                controls=[self.name_field, self.description_field], spacing=12
            ),
            self.entry_url_field,
            self.google_search_check,
            self.google_term_field,
            ft.Row(
                controls=[
                    self.input_selector_field,
                    self.submit_method,
                    self.submit_selector_field,
                ],
                spacing=12,
            ),
            ft.Row(
                controls=[self.capture_method, self.ws_url_pattern_field], spacing=12
            ),
            ft.Row(
                controls=[
                    self.ws_decode_base64_check,
                    self.ws_ignore_field,
                    self.ws_completion_field,
                ],
                spacing=12,
            ),
            ft.Text("Onboarding Steps", size=14, color="#888888"),
            self.onboarding_json,
            ft.Row(controls=[self.save_btn, self.new_btn], spacing=12),
        ]

    def _field(self, label: str, hint: str) -> ft.TextField:
        return ft.TextField(
            label=label,
            hint_text=hint,
            expand=True,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
        )

    async def load_pipelines(self) -> None:
        """Fetch and display saved pipelines."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.api_base}/v1/pipelines")
                pipelines = resp.json()

            self.pipeline_list.controls = [
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                p["name"],
                                size=14,
                                color="#FFFFFF",
                                weight=ft.FontWeight.W_500,
                                expand=True,
                            ),
                            ft.Text(
                                p["entry_url"],
                                size=11,
                                color="#555555",
                                expand=True,
                            ),
                            ft.TextButton(
                                content="Edit",
                                style=ft.ButtonStyle(color="#888888"),
                                data=p["id"],
                                on_click=self._on_edit,
                            ),
                        ],
                    ),
                    padding=ft.Padding(8, 6, 8, 6),
                    border=ft.border.all(1, "#222222"),
                    border_radius=4,
                )
                for p in pipelines
            ]
            self.update()
        except Exception:
            pass

    async def _on_edit(self, e) -> None:
        """Load a pipeline config into the form for editing."""
        pipeline_id = e.control.data
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.api_base}/v1/pipelines/{pipeline_id}"
                )
                p = resp.json()
            self._editing_id = pipeline_id
            self.name_field.value = p.get("name", "")
            self.description_field.value = p.get("description", "")
            self.entry_url_field.value = p.get("entry_url", "")
            self.google_search_check.value = p.get("use_google_search", False)
            self.google_term_field.value = p.get("google_search_term", "")
            self.input_selector_field.value = p.get("input_selector", "")
            self.submit_method.value = p.get("submit_method", "enter_key")
            self.submit_selector_field.value = p.get("submit_selector", "")
            self.capture_method.value = p.get("capture_method", "websocket")
            self.ws_url_pattern_field.value = p.get("ws_url_pattern", "")
            self.ws_decode_base64_check.value = p.get("ws_decode_base64", False)
            self.ws_ignore_field.value = p.get("ws_ignore_pattern", "")
            self.ws_completion_field.value = p.get("ws_completion_signal", "")
            self.onboarding_json.value = json.dumps(
                p.get("onboarding_steps") or [], indent=2
            )
            self.update()
        except Exception:
            pass

    async def _on_save(self, e) -> None:
        """Save (create or update) the pipeline config."""
        try:
            steps = json.loads(self.onboarding_json.value or "[]")
        except json.JSONDecodeError:
            steps = []

        payload = {
            "name": self.name_field.value,
            "description": self.description_field.value,
            "entry_url": self.entry_url_field.value,
            "use_google_search": self.google_search_check.value,
            "google_search_term": self.google_term_field.value or None,
            "onboarding_steps": steps,
            "input_selector": self.input_selector_field.value,
            "submit_method": self.submit_method.value,
            "submit_selector": self.submit_selector_field.value or None,
            "capture_method": self.capture_method.value,
            "ws_url_pattern": self.ws_url_pattern_field.value or None,
            "ws_decode_base64": self.ws_decode_base64_check.value,
            "ws_ignore_pattern": self.ws_ignore_field.value or None,
            "ws_completion_signal": self.ws_completion_field.value or None,
        }
        try:
            async with httpx.AsyncClient() as client:
                if self._editing_id:
                    await client.put(
                        f"{self.api_base}/v1/pipelines/{self._editing_id}",
                        json=payload,
                    )
                else:
                    await client.post(
                        f"{self.api_base}/v1/pipelines", json=payload
                    )
            await self.load_pipelines()
            self._reset_form()
        except Exception:
            pass

    async def _on_inspect(self, e) -> None:
        """Run the page inspector and display results as selectable cards."""
        url = self.inspect_url_field.value
        if not url:
            return

        self.inspect_status.value = "Inspecting... (browser will open)"
        self.inspect_results.controls.clear()
        self.update()

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.api_base}/v1/inspect",
                    json={"url": url, "wait_seconds": 10},
                )
                data = resp.json()

            self.inspect_status.value = (
                f"Found: {len(data.get('inputs', []))} inputs, "
                f"{len(data.get('buttons', []))} buttons, "
                f"{len(data.get('websockets', []))} WebSockets"
            )

            # Show detected inputs as selectable cards
            if data.get("inputs"):
                self.inspect_results.controls.append(
                    ft.Text("Detected Inputs", size=13, color="#888888")
                )
                for inp in data["inputs"]:
                    detail = (
                        inp.get("placeholder")
                        or inp.get("aria_label")
                        or inp.get("name")
                        or ""
                    )
                    label = f"{inp['tag']}  {detail}"
                    self.inspect_results.controls.append(
                        self._selectable_card(
                            title=label.strip(),
                            subtitle=inp["selector"],
                            on_select=lambda _, s=inp["selector"]: self._set_field(
                                self.input_selector_field, s
                            ),
                        )
                    )

            # Show detected buttons
            if data.get("buttons"):
                self.inspect_results.controls.append(
                    ft.Text("Detected Buttons", size=13, color="#888888")
                )
                for btn in data["buttons"]:
                    self.inspect_results.controls.append(
                        self._selectable_card(
                            title=btn["text"] or btn.get("aria_label", "button"),
                            subtitle=btn["selector"],
                            on_select=lambda _, s=btn["selector"]: self._set_field(
                                self.submit_selector_field, s
                            ),
                        )
                    )

            # Show detected WebSockets
            if data.get("websockets"):
                self.inspect_results.controls.append(
                    ft.Text("Detected WebSockets", size=13, color="#888888")
                )
                for ws in data["websockets"]:
                    sample = (
                        ws["sample_messages"][0][:100]
                        if ws["sample_messages"]
                        else "none"
                    )
                    self.inspect_results.controls.append(
                        self._selectable_card(
                            title=f"{ws['url'][:80]}  ({ws['message_count']} msgs)",
                            subtitle=f"Sample: {sample}",
                            on_select=lambda _, u=ws["url"]: self._set_field(
                                self.ws_url_pattern_field,
                                u.split("//")[1].split("/")[0]
                                if "//" in u
                                else u,
                            ),
                        )
                    )

            self.update()
        except Exception as ex:
            self.inspect_status.value = f"Inspection failed: {ex}"
            self.update()

    def _selectable_card(self, title: str, subtitle: str, on_select) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text(title, size=12, color="#FFFFFF"),
                            ft.Text(
                                subtitle,
                                size=11,
                                color="#555555",
                                font_family="monospace",
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.TextButton(
                        content="Use",
                        style=ft.ButtonStyle(color="#FFFFFF"),
                        on_click=on_select,
                    ),
                ],
            ),
            padding=ft.Padding(8, 6, 8, 6),
            border=ft.border.all(1, "#222222"),
            border_radius=4,
            bgcolor="#0A0A0A",
        )

    def _set_field(self, field: ft.TextField, value: str) -> None:
        field.value = value
        try:
            self.update()
        except Exception:
            pass

    def _reset_form(self) -> None:
        self._editing_id = None
        for field in [
            self.name_field,
            self.description_field,
            self.entry_url_field,
            self.google_term_field,
            self.input_selector_field,
            self.submit_selector_field,
            self.ws_url_pattern_field,
            self.ws_ignore_field,
            self.ws_completion_field,
        ]:
            field.value = ""
        self.google_search_check.value = False
        self.ws_decode_base64_check.value = False
        self.onboarding_json.value = "[]"
        try:
            self.update()
        except Exception:
            pass
