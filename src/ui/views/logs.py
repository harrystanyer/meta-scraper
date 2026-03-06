"""Logs — real-time log stream with filtering, terminal-style."""
import flet as ft
import httpx

from src.events import Event, EventType, event_bus


class LogsView(ft.Column):
    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__(expand=True, spacing=12)
        self.api_base = api_base
        self._all_logs: list[dict] = []
        self._known_instances: set[str] = set()

        self.instance_filter = ft.Dropdown(
            label="Instance",
            options=[ft.DropdownOption(key="ALL", text="All")],
            value="ALL",
            width=220,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            on_select=lambda _: self._apply_filter(),
        )
        self.level_filter = ft.Dropdown(
            label="Level",
            options=[
                ft.DropdownOption(key="ALL", text="All"),
                ft.DropdownOption(key="INFO", text="INFO"),
                ft.DropdownOption(key="WARN", text="WARN"),
                ft.DropdownOption(key="ERROR", text="ERROR"),
            ],
            value="ALL",
            width=140,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            on_select=lambda _: self._apply_filter(),
        )
        self.clear_btn = ft.TextButton(
            content="Clear",
            style=ft.ButtonStyle(color="#888888"),
            on_click=lambda _: self._clear_logs(),
        )

        self.log_list = ft.ListView(expand=True, spacing=0, auto_scroll=False)

        self.controls = [
            ft.Container(
                content=ft.Text("Logs", size=24, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                padding=ft.Padding(0, 0, 0, 8),
            ),
            ft.Row(
                controls=[self.instance_filter, self.level_filter, self.clear_btn],
                spacing=12,
            ),
            ft.Container(
                content=self.log_list,
                expand=True,
                bgcolor="#0A0A0A",
                border=ft.border.all(1, "#222222"),
                border_radius=4,
                padding=8,
            ),
        ]

        # Subscribe to live log events
        event_bus.subscribe(EventType.LOG, self._on_log)

    async def load_initial(self) -> None:
        """Fetch historical logs on first load."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.api_base}/v1/logs", params={"limit": 200}
                )
                logs = resp.json()
            for log in reversed(logs):  # oldest first
                self._all_logs.append(log)
                iid = log.get("instance_id", "")
                if iid and iid not in self._known_instances:
                    self._known_instances.add(iid)
            self._rebuild_instance_options()
            self._apply_filter()
        except Exception:
            pass

    async def _on_log(self, event: Event) -> None:
        """Receive a live log entry from the event bus."""
        log = {
            "instance_id": event.data.get("instance_id", ""),
            "level": event.data.get("level", "INFO"),
            "message": event.data.get("message", ""),
            "step": event.data.get("step", ""),
            "created_at": event.timestamp.isoformat(),
        }
        self._all_logs.append(log)
        # Keep max 500 in memory
        if len(self._all_logs) > 500:
            self._all_logs = self._all_logs[-500:]

        iid = log["instance_id"]
        if iid and iid not in self._known_instances:
            self._known_instances.add(iid)
            self._rebuild_instance_options()

        # Only display if passes current filter
        if self._matches_filter(log):
            self.log_list.controls.append(self._log_row(log))
            try:
                self.update()
            except Exception:
                pass

    def _matches_filter(self, log: dict) -> bool:
        if self.instance_filter.value and self.instance_filter.value != "ALL":
            if log.get("instance_id") != self.instance_filter.value:
                return False
        if self.level_filter.value and self.level_filter.value != "ALL":
            if log.get("level") != self.level_filter.value:
                return False
        return True

    def _apply_filter(self) -> None:
        """Re-render log list based on current filters."""
        self.log_list.controls = [
            self._log_row(log) for log in self._all_logs if self._matches_filter(log)
        ]
        try:
            self.update()
        except Exception:
            pass

    def _log_row(self, log: dict) -> ft.Container:
        ts = log.get("created_at", "")[:19].replace("T", " ")
        level = log.get("level", "INFO")
        # Intensity-based: ERROR is bright white, WARN is medium, INFO is dim
        level_brightness = {"ERROR": "#FFFFFF", "WARN": "#AAAAAA", "INFO": "#666666"}
        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(
                        ts,
                        size=11,
                        color="#444444",
                        width=140,
                        font_family="monospace",
                    ),
                    ft.Text(
                        level.ljust(5),
                        size=11,
                        weight=ft.FontWeight.BOLD,
                        color=level_brightness.get(level, "#666666"),
                        width=50,
                        font_family="monospace",
                    ),
                    ft.Text(
                        log.get("instance_id", "")[-8:],
                        size=11,
                        color="#555555",
                        width=80,
                        font_family="monospace",
                    ),
                    ft.Text(
                        log.get("message", ""),
                        size=12,
                        color="#CCCCCC",
                        expand=True,
                        font_family="monospace",
                    ),
                ],
                spacing=8,
            ),
            padding=ft.Padding(4, 2, 4, 2),
        )

    def _rebuild_instance_options(self) -> None:
        self.instance_filter.options = [
            ft.DropdownOption(key="ALL", text="All")
        ] + [ft.DropdownOption(key=iid, text=iid) for iid in sorted(self._known_instances)]

    def _clear_logs(self) -> None:
        self._all_logs.clear()
        self.log_list.controls.clear()
        try:
            self.update()
        except Exception:
            pass
