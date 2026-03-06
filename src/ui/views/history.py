"""Request History — browse all previous requests and responses with pagination."""
import asyncio
from datetime import datetime

import flet as ft
import httpx


class HistoryView(ft.Column):
    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__(expand=True, spacing=16)
        self.api_base = api_base
        self._polling = False
        self._client = httpx.AsyncClient(timeout=5)
        self._offset = 0
        self._limit = 25
        self._total = 0
        self._status_filter = "ALL"

        self.filter_dd = ft.Dropdown(
            value="ALL",
            options=[
                ft.DropdownOption(key="ALL", text="All"),
                ft.DropdownOption(key="COMPLETED", text="Completed"),
                ft.DropdownOption(key="FAILED", text="Failed"),
                ft.DropdownOption(key="QUEUED", text="Queued"),
                ft.DropdownOption(key="PROCESSING", text="Processing"),
            ],
            width=160,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            on_select=self._on_filter_change,
        )
        self.refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_color="#888888",
            on_click=self._on_refresh,
        )
        self.count_text = ft.Text("", size=12, color="#555555")

        self.task_list = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)

        # Pagination controls
        self.prev_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_LEFT,
            icon_color="#888888",
            on_click=self._on_prev,
            disabled=True,
        )
        self.next_btn = ft.IconButton(
            icon=ft.Icons.CHEVRON_RIGHT,
            icon_color="#888888",
            on_click=self._on_next,
            disabled=True,
        )
        self.page_text = ft.Text("", size=12, color="#888888")

        # Detail panel (shown when a row is clicked)
        self.detail_prompt = ft.Text("", size=13, color="#AAAAAA", selectable=True)
        self.detail_response = ft.Text(
            "", size=13, color="#FFFFFF", selectable=True
        )
        self.detail_meta = ft.Text("", size=11, color="#555555")
        self.detail_panel = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text(
                                "Details",
                                size=14,
                                weight=ft.FontWeight.W_600,
                                color="#888888",
                                expand=True,
                            ),
                            ft.IconButton(
                                icon=ft.Icons.CLOSE,
                                icon_size=16,
                                icon_color="#888888",
                                on_click=self._close_detail,
                            ),
                        ],
                    ),
                    ft.Text("Prompt", size=11, color="#555555"),
                    ft.Container(
                        content=self.detail_prompt,
                        padding=12,
                        border=ft.border.all(1, "#222222"),
                        border_radius=4,
                        bgcolor="#0A0A0A",
                    ),
                    ft.Text("Response", size=11, color="#555555"),
                    ft.Container(
                        content=self.detail_response,
                        padding=12,
                        border=ft.border.all(1, "#222222"),
                        border_radius=4,
                        bgcolor="#111111",
                        height=300,
                    ),
                    self.detail_meta,
                ],
                spacing=8,
            ),
            visible=False,
            padding=16,
            border=ft.border.all(1, "#222222"),
            border_radius=8,
            bgcolor="#0A0A0A",
        )

        self.controls = [
            ft.Text(
                "Request History",
                size=24,
                weight=ft.FontWeight.BOLD,
                color="#FFFFFF",
            ),
            ft.Row(
                controls=[
                    ft.Text("Filter:", size=12, color="#888888"),
                    self.filter_dd,
                    self.refresh_btn,
                    self.count_text,
                ],
                spacing=12,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            # Header row
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text("Status", size=11, color="#555555", width=90),
                        ft.Text("Prompt", size=11, color="#555555", width=250),
                        ft.Text("Response", size=11, color="#555555", expand=True),
                        ft.Text("Instance", size=11, color="#555555", width=130),
                        ft.Text("Time", size=11, color="#555555", width=80),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding(12, 8, 12, 8),
                border=ft.border.only(bottom=ft.BorderSide(1, "#222222")),
            ),
            self.task_list,
            # Pagination row
            ft.Row(
                controls=[
                    self.prev_btn,
                    self.page_text,
                    self.next_btn,
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=8,
            ),
            self.detail_panel,
        ]

    async def load_initial(self) -> None:
        await self._fetch_tasks()
        self._polling = True
        asyncio.create_task(self._poll_loop())

    def _safe_update(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    async def _poll_loop(self) -> None:
        while self._polling:
            await asyncio.sleep(5)
            try:
                await self._fetch_tasks()
            except Exception:
                pass

    async def _on_filter_change(self, e) -> None:
        self._status_filter = self.filter_dd.value
        self._offset = 0
        await self._fetch_tasks()

    async def _on_refresh(self, e) -> None:
        await self._fetch_tasks()

    async def _on_prev(self, e) -> None:
        self._offset = max(0, self._offset - self._limit)
        await self._fetch_tasks()

    async def _on_next(self, e) -> None:
        if self._offset + self._limit < self._total:
            self._offset += self._limit
            await self._fetch_tasks()

    def _update_pagination(self) -> None:
        current_page = (self._offset // self._limit) + 1
        total_pages = max(1, (self._total + self._limit - 1) // self._limit)
        self.page_text.value = f"Page {current_page} of {total_pages}  ({self._total} total)"
        self.prev_btn.disabled = self._offset == 0
        self.next_btn.disabled = self._offset + self._limit >= self._total

    async def _fetch_tasks(self) -> None:
        try:
            params = {"limit": self._limit, "offset": self._offset}
            if self._status_filter != "ALL":
                params["status"] = self._status_filter

            resp = await self._client.get(
                f"{self.api_base}/v1/tasks", params=params
            )
            if resp.status_code != 200:
                return
            data = resp.json()
        except Exception:
            return

        self._total = data.get("total", 0)
        tasks = data.get("items", [])
        self.count_text.value = f"Showing {len(tasks)} of {self._total}"
        self._update_pagination()

        new_controls = []
        for t in tasks:
            status = t.get("status", "")
            prompt = t.get("prompt", "")
            response = t.get("response_text") or t.get("failure_reason") or ""
            instance_id = t.get("instance_id") or ""
            created = t.get("created_at", "")
            completed = t.get("completed_at", "")

            # Duration
            duration = ""
            if created and completed:
                try:
                    c = datetime.fromisoformat(created)
                    d = datetime.fromisoformat(completed)
                    secs = (d - c).total_seconds()
                    duration = f"{secs:.1f}s"
                except Exception:
                    pass

            # Status color
            if status == "COMPLETED":
                status_color = "#44FF44"
            elif status == "FAILED":
                status_color = "#FF4444"
            elif status == "PROCESSING":
                status_color = "#FFAA00"
            else:
                status_color = "#888888"

            task_data = t
            row = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Text(
                            status,
                            size=11,
                            weight=ft.FontWeight.BOLD,
                            color=status_color,
                            width=90,
                        ),
                        ft.Text(
                            prompt[:40] + ("..." if len(prompt) > 40 else ""),
                            size=11,
                            color="#AAAAAA",
                            width=250,
                        ),
                        ft.Text(
                            response[:60] + ("..." if len(response) > 60 else ""),
                            size=11,
                            color="#FFFFFF",
                            expand=True,
                        ),
                        ft.Text(
                            instance_id[-12:] if instance_id else "",
                            size=11,
                            color="#555555",
                            width=130,
                        ),
                        ft.Text(duration, size=11, color="#888888", width=80),
                    ],
                    spacing=8,
                ),
                padding=ft.Padding(12, 8, 12, 8),
                border=ft.border.only(bottom=ft.BorderSide(1, "#111111")),
                on_click=lambda e, td=task_data: self._show_detail(td),
                ink=True,
            )
            new_controls.append(row)

        self.task_list.controls = new_controls
        self._safe_update()

    def _close_detail(self, e) -> None:
        self.detail_panel.visible = False
        self._safe_update()

    def _show_detail(self, task_data: dict) -> None:
        self.detail_prompt.value = task_data.get("prompt", "")
        self.detail_response.value = (
            task_data.get("response_text")
            or task_data.get("failure_reason")
            or "(no response)"
        )
        meta_parts = [
            f"ID: {task_data.get('id', '')}",
            f"Status: {task_data.get('status', '')}",
            f"Instance: {task_data.get('instance_id', '')}",
            f"Created: {task_data.get('created_at', '')}",
            f"Completed: {task_data.get('completed_at', '')}",
        ]
        self.detail_meta.value = "  |  ".join(meta_parts)
        self.detail_panel.visible = True
        self._safe_update()
