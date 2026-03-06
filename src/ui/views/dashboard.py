"""Dashboard — metrics and instance status, refreshed via polling."""
import asyncio

import flet as ft
import httpx


class DashboardView(ft.Column):
    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__(expand=True, scroll=ft.ScrollMode.AUTO, spacing=24)
        self.api_base = api_base
        self._polling = False
        self._client = httpx.AsyncClient(timeout=5)

        # Metric value refs for live updates
        self._metric_refs: dict[str, ft.Text] = {}

        metrics_row = ft.Row(
            controls=[
                self._metric_card("Total", "total"),
                self._metric_card("Successes", "completed"),
                self._metric_card("Failed", "failed"),
                self._metric_card("Success Rate", "success_rate", suffix="%"),
                self._metric_card("Failure Rate", "failure_rate", suffix="%"),
                self._metric_card("Queue", "queue_size"),
                self._metric_card("Instances", "active_instances"),
            ],
            wrap=True,
            spacing=12,
        )

        self.instance_list = ft.Column(spacing=4)
        self.activity_list = ft.Column(spacing=2)

        self.clear_btn = ft.OutlinedButton(
            content="Clear Database",
            style=ft.ButtonStyle(
                color="#FF4444",
                side=ft.BorderSide(1, "#FF4444"),
            ),
            on_click=self._on_clear,
        )
        self.clear_status = ft.Text("", size=12, color="#555555")

        self.controls = [
            ft.Row(
                controls=[
                    ft.Text(
                        "Dashboard",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color="#FFFFFF",
                        expand=True,
                    ),
                    self.clear_btn,
                    self.clear_status,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            metrics_row,
            ft.Divider(height=1, color="#222222"),
            ft.Text("Instances", size=16, weight=ft.FontWeight.W_600, color="#888888"),
            self.instance_list,
            ft.Divider(height=1, color="#222222"),
            ft.Text("Recent Activity", size=16, weight=ft.FontWeight.W_600, color="#888888"),
            self.activity_list,
        ]

    def _metric_card(self, label: str, key: str, suffix: str = "") -> ft.Container:
        value_text = ft.Text(
            "0" + suffix, size=28, weight=ft.FontWeight.BOLD, color="#FFFFFF"
        )
        self._metric_refs[key] = value_text
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(label, size=11, color="#888888"),
                    value_text,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            padding=16,
            border=ft.border.all(1, "#333333"),
            border_radius=8,
            bgcolor="#111111",
            width=150,
        )

    def _safe_update(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    async def _on_clear(self, e) -> None:
        self.clear_btn.disabled = True
        self.clear_status.value = "Clearing..."
        self._safe_update()
        try:
            resp = await self._client.delete(f"{self.api_base}/v1/tasks")
            if resp.status_code == 200:
                self.clear_status.value = "Cleared"
            else:
                self.clear_status.value = f"Error: {resp.status_code}"
        except Exception as ex:
            self.clear_status.value = f"Error: {ex}"
        self.clear_btn.disabled = False
        await self._refresh_metrics()
        self._safe_update()

    async def load_initial(self) -> None:
        """Fetch initial metrics and start polling."""
        await self._refresh_metrics()
        await self._refresh_activity()
        self._polling = True
        asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        """Poll metrics and activity every 3 seconds."""
        while self._polling:
            await asyncio.sleep(3)
            try:
                changed = await self._refresh_metrics()
                activity_changed = await self._refresh_activity()
                if changed or activity_changed:
                    self._safe_update()
            except Exception:
                pass

    async def _refresh_metrics(self) -> bool:
        """Fetch metrics from API. Returns True if values changed."""
        changed = False
        try:
            resp = await self._client.get(f"{self.api_base}/v1/metrics")
            if resp.status_code == 200:
                data = resp.json()
                for key, ref in self._metric_refs.items():
                    val = data.get(key, 0)
                    if key in ("failure_rate", "success_rate"):
                        new_val = f"{val:.1f}%"
                    else:
                        new_val = str(val)
                    if ref.value != new_val:
                        ref.value = new_val
                        changed = True

                # Update instance list
                instance_ids = data.get("instance_ids", [])
                new_controls = [
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.CIRCLE, size=8, color="#44FF44"),
                                ft.Text(iid, size=13, color="#FFFFFF"),
                            ],
                            spacing=8,
                        ),
                        padding=8,
                    )
                    for iid in instance_ids
                ]
                if len(new_controls) != len(self.instance_list.controls):
                    self.instance_list.controls = new_controls
                    changed = True
        except Exception:
            pass
        return changed

    async def _refresh_activity(self) -> bool:
        """Fetch recent completed/failed tasks from logs."""
        try:
            resp = await self._client.get(
                f"{self.api_base}/v1/logs",
                params={"limit": 20},
            )
            if resp.status_code == 200:
                logs = resp.json()
                new_controls = []
                for log in logs:
                    msg = log.get("message", "")
                    level = log.get("level", "INFO")
                    step = log.get("step", "")
                    ts = log.get("created_at", "")
                    time_str = ts[11:19] if len(ts) > 19 else ""

                    if level == "ERROR":
                        color = "#FF4444"
                        indicator = "ERR"
                    elif "complete" in step.lower() or "response" in step.lower():
                        color = "#44FF44"
                        indicator = "OK"
                    else:
                        color = "#888888"
                        indicator = level[:4]

                    new_controls.append(
                        ft.Container(
                            content=ft.Row(
                                controls=[
                                    ft.Text(time_str, size=11, color="#555555", width=70),
                                    ft.Text(
                                        indicator,
                                        size=11,
                                        weight=ft.FontWeight.BOLD,
                                        color=color,
                                        width=40,
                                    ),
                                    ft.Text(
                                        msg[:80],
                                        size=11,
                                        color="#AAAAAA",
                                    ),
                                ],
                                spacing=8,
                            ),
                            padding=8,
                        )
                    )

                old_count = len(self.activity_list.controls)
                self.activity_list.controls = new_controls
                return len(new_controls) != old_count
        except Exception:
            pass
        return False
