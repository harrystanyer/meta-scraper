"""Playground — test prompts against any pipeline."""
import asyncio
import json

import flet as ft
import httpx


class PlaygroundView(ft.Column):
    def __init__(self, api_base: str = "http://localhost:8000"):
        super().__init__(expand=True, scroll=ft.ScrollMode.AUTO, spacing=16)
        self.api_base = api_base
        self._client = httpx.AsyncClient(timeout=960)

        self.pipeline_field = ft.TextField(
            value="meta-ai",
            label="Pipeline",
            width=160,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
        )
        self.prompt_input = ft.TextField(
            hint_text="Enter a prompt...",
            multiline=True,
            min_lines=2,
            max_lines=5,
            expand=True,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            focused_border_color="#FFFFFF",
            cursor_color="#FFFFFF",
        )
        self.country_input = ft.TextField(
            value="US",
            width=80,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            text_align=ft.TextAlign.CENTER,
        )
        self.submit_btn = ft.OutlinedButton(
            content="Send",
            style=ft.ButtonStyle(
                color="#FFFFFF",
                side=ft.BorderSide(1, "#FFFFFF"),
            ),
            on_click=self._on_submit,
        )
        self.status_text = ft.Text("", size=12, color="#555555")

        self.response_text = ft.Text(
            "",
            selectable=True,
            size=14,
            color="#FFFFFF",
        )
        self.sources_column = ft.Column(spacing=4)
        self.raw_text = ft.Text(
            "",
            selectable=True,
            size=11,
            color="#888888",
        )

        # --- Batch test section ---
        self.batch_count = ft.TextField(
            value="10",
            label="n",
            width=80,
            color="#FFFFFF",
            bgcolor="#111111",
            border_color="#222222",
            text_align=ft.TextAlign.CENTER,
        )
        self.batch_btn = ft.OutlinedButton(
            content="Send Batch",
            style=ft.ButtonStyle(
                color="#FFFFFF",
                side=ft.BorderSide(1, "#FFFFFF"),
            ),
            on_click=self._on_batch,
        )
        self.batch_status = ft.Text("", size=12, color="#555555")
        self.batch_results = ft.Column(spacing=2)

        self.controls = [
            ft.Text("Playground", size=24, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
            # Single prompt
            ft.Row(
                controls=[self.pipeline_field, self.prompt_input, self.country_input],
                spacing=12,
            ),
            ft.Row(controls=[self.submit_btn, self.status_text], spacing=12),
            ft.Divider(height=1, color="#222222"),
            ft.Text("Response", size=14, weight=ft.FontWeight.W_600, color="#888888"),
            ft.Container(
                content=self.response_text,
                padding=16,
                border=ft.border.all(1, "#222222"),
                border_radius=4,
                bgcolor="#111111",
            ),
            ft.Text("Sources", size=14, weight=ft.FontWeight.W_600, color="#888888"),
            self.sources_column,
            ft.Text("Raw", size=14, weight=ft.FontWeight.W_600, color="#888888"),
            ft.Container(
                content=self.raw_text,
                padding=16,
                border=ft.border.all(1, "#222222"),
                border_radius=4,
                bgcolor="#0A0A0A",
            ),
            ft.Divider(height=1, color="#333333"),
            # Batch test
            ft.Text(
                "Batch Test", size=18, weight=ft.FontWeight.BOLD, color="#FFFFFF"
            ),
            ft.Text(
                'Sends n prompts ("What is i*i?") in parallel to stress-test instances.',
                size=12,
                color="#555555",
            ),
            ft.Row(
                controls=[self.batch_count, self.batch_btn, self.batch_status],
                spacing=12,
            ),
            self.batch_results,
        ]

    def _safe_update(self) -> None:
        try:
            self.update()
        except Exception:
            pass

    # --- Single prompt ---

    async def _on_submit(self, e) -> None:
        if not self.prompt_input.value:
            return

        self.submit_btn.disabled = True
        self.status_text.value = "Processing..."
        self.response_text.value = ""
        self.sources_column.controls.clear()
        self.raw_text.value = ""
        self._safe_update()

        pipeline_name = self.pipeline_field.value or "meta-ai"
        try:
            resp = await self._client.post(
                f"{self.api_base}/v1/monitor/{pipeline_name}",
                json={
                    "prompt": self.prompt_input.value,
                    "country": self.country_input.value,
                    "include": {"rawResponse": True, "markdown": True},
                },
            )
            data = resp.json()

            if data.get("success"):
                result = data["result"]
                self.response_text.value = result.get("text", "No response")
                self.status_text.value = f"Done — {len(result.get('text', ''))} chars"

                for src in result.get("sources", []):
                    self.sources_column.controls.append(
                        ft.Container(
                            content=ft.Column(
                                controls=[
                                    ft.Text(
                                        src.get("label", "Source"),
                                        size=13,
                                        color="#FFFFFF",
                                        weight=ft.FontWeight.W_500,
                                    ),
                                    ft.Text(
                                        src.get("url", ""), size=11, color="#555555"
                                    ),
                                ],
                                spacing=2,
                            ),
                            padding=ft.Padding(8, 6, 8, 6),
                            border=ft.border.all(1, "#222222"),
                            border_radius=4,
                        )
                    )

                self.raw_text.value = json.dumps(
                    result.get("rawResponse", []), indent=2
                )[:5000]
            else:
                self.response_text.value = data.get("error", "Unknown error")
                self.status_text.value = "Failed"
        except Exception as ex:
            self.response_text.value = f"Request failed: {ex}"
            self.status_text.value = "Error"
        finally:
            self.submit_btn.disabled = False
            self._safe_update()

    # --- Batch test ---

    async def _on_batch(self, e) -> None:
        try:
            n = int(self.batch_count.value)
        except (ValueError, TypeError):
            self.batch_status.value = "Invalid number"
            self._safe_update()
            return

        n = max(1, min(n, 1000))
        self.batch_btn.disabled = True
        self.batch_results.controls.clear()
        self.batch_status.value = f"Sending {n} prompts..."
        self._safe_update()

        pipeline_name = self.pipeline_field.value or "meta-ai"
        results = [None] * n
        succeeded = 0
        failed = 0
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent requests
        last_update = [0]  # Mutable counter for throttled UI updates

        async def send_one(idx: int) -> None:
            nonlocal succeeded, failed
            prompt = f"What is {idx + 1} * {idx + 1}?"
            async with semaphore:
                try:
                    resp = await self._client.post(
                        f"{self.api_base}/v1/monitor/{pipeline_name}",
                        json={"prompt": prompt},
                    )
                    data = resp.json()
                    if data.get("success"):
                        text = data["result"]["text"]
                        results[idx] = ("OK", prompt, text[:80])
                        succeeded += 1
                    else:
                        err = data.get("error", "Unknown")[:60]
                        results[idx] = ("FAIL", prompt, err)
                        failed += 1
                except Exception as ex:
                    results[idx] = ("ERR", prompt, str(ex)[:60])
                    failed += 1

            # Throttle UI updates — every 5 completions or on the last one
            done = succeeded + failed
            if done - last_update[0] >= 5 or done == n:
                last_update[0] = done
                self.batch_status.value = f"{done}/{n}  —  {succeeded} OK, {failed} failed"
                self._safe_update()
                # Yield to the event loop so Flet can process WebSocket pings
                await asyncio.sleep(0)

        # Fire all with semaphore controlling concurrency
        tasks = [asyncio.create_task(send_one(i)) for i in range(n)]
        await asyncio.gather(*tasks)

        # Build results table
        self.batch_results.controls.clear()
        for idx, res in enumerate(results):
            if res is None:
                continue
            status, prompt, text = res
            color = "#44FF44" if status == "OK" else "#FF4444"
            self.batch_results.controls.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Text(
                                status,
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=color,
                                width=40,
                            ),
                            ft.Text(prompt, size=11, color="#888888", width=180),
                            ft.Text(text, size=11, color="#FFFFFF"),
                        ],
                        spacing=8,
                    ),
                    padding=6,
                )
            )

        self.batch_status.value = (
            f"Done — {succeeded}/{n} succeeded, {failed}/{n} failed"
        )
        self.batch_btn.disabled = False
        self._safe_update()
