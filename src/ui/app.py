"""Main Flet app — left nav rail, black & white minimalist, 4 tabs."""
import flet as ft

from src.ui.views.dashboard import DashboardView
from src.ui.views.history import HistoryView
from src.ui.views.logs import LogsView
from src.ui.views.pipelines import PipelinesView
from src.ui.views.playground import PlaygroundView


async def flet_main(page: ft.Page):
    page.title = "Meta Scraper"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#000000"
    page.window.width = 1400
    page.window.height = 900
    page.padding = 0
    page.spacing = 0

    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            surface="#000000",
            on_surface="#FFFFFF",
            primary="#FFFFFF",
            on_primary="#000000",
            surface_container="#111111",
            surface_container_low="#0A0A0A",
            surface_container_lowest="#000000",
        ),
    )

    dashboard = DashboardView()
    history_view = HistoryView()
    logs_view = LogsView()
    playground = PlaygroundView()
    pipelines_view = PipelinesView()

    views = [dashboard, history_view, logs_view, playground, pipelines_view]

    content_area = ft.Container(
        content=dashboard,
        expand=True,
        padding=32,
        bgcolor="#000000",
    )

    def switch_view(e):
        idx = e.control.selected_index
        content_area.content = views[idx]
        page.update()

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=72,
        min_extended_width=200,
        extended=True,
        bgcolor="#0A0A0A",
        indicator_color="#222222",
        on_change=switch_view,
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.DASHBOARD_OUTLINED,
                selected_icon=ft.Icons.DASHBOARD,
                label="Dashboard",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.HISTORY_OUTLINED,
                selected_icon=ft.Icons.HISTORY,
                label="History",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.TERMINAL_OUTLINED,
                selected_icon=ft.Icons.TERMINAL,
                label="Logs",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SCIENCE_OUTLINED,
                selected_icon=ft.Icons.SCIENCE,
                label="Playground",
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SETTINGS_INPUT_COMPONENT_OUTLINED,
                selected_icon=ft.Icons.SETTINGS_INPUT_COMPONENT,
                label="Pipelines",
            ),
        ],
    )

    page.add(
        ft.Row(
            controls=[
                nav_rail,
                ft.VerticalDivider(width=1, color="#222222"),
                content_area,
            ],
            expand=True,
            spacing=0,
        )
    )

    # Load initial data
    await dashboard.load_initial()
    await history_view.load_initial()
    await logs_view.load_initial()
    await pipelines_view.load_pipelines()
