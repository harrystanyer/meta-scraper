"""Entry point: FastAPI app with Flet UI and scraper manager."""
from contextlib import asynccontextmanager

import flet.fastapi as flet_fastapi
from fastapi import FastAPI

from src.api.router import router as api_router
from src.api.router import set_manager
from src.database import crud
from src.database.models import Base
from src.database.session import async_session, engine
from src.scraper.manager import ScrapeManager
from src.ui.app import flet_main

manager = ScrapeManager()


async def seed_default_pipeline():
    """Create the default meta-ai pipeline if it doesn't exist."""
    async with async_session() as session:
        existing = await crud.get_pipeline_by_name(session, "meta-ai")
        if existing:
            return
        await crud.create_pipeline(
            session,
            name="meta-ai",
            description="Meta AI direct",
            entry_url="https://www.meta.ai",
            use_google_search=False,
            onboarding_steps=[
                # Step 1: Welcome dialog — click Continue
                {
                    "action": "click",
                    "selector": "button:has-text('Continue')",
                    "optional": True,
                    "timeout_ms": 15000,
                },
                # Step 2: Age verification — click Year dropdown trigger
                {
                    "action": "click",
                    "selector": "button:has-text('Year')",
                    "optional": True,
                    "timeout_ms": 5000,
                },
                # Step 3: Select a year from Radix dropdown
                {
                    "action": "click",
                    "selector": "[role='option']:has-text('1998')",
                    "optional": True,
                    "timeout_ms": 3000,
                },
                # Step 4: Click Continue on age verification
                {
                    "action": "click",
                    "selector": "button:has-text('Continue')",
                    "optional": True,
                    "timeout_ms": 5000,
                },
                # Step 5: Wait for page to settle after onboarding
                {
                    "action": "wait",
                    "value": "3000",
                },
            ],
            input_selector='input[placeholder*="Ask"]',
            submit_method="click",
            submit_selector='button[aria-label="Send"]',
            capture_method="dom",
            dom_response_selector='[data-testid="assistant-message"]',
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default pipeline
    await seed_default_pipeline()

    # Start scraper manager (will load the default pipeline)
    set_manager(manager)
    await manager.start(default_pipeline_name="meta-ai")

    # Start Flet app manager
    await flet_fastapi.app_manager.start()

    yield

    # Shutdown
    await manager.stop()
    await flet_fastapi.app_manager.shutdown()
    await engine.dispose()


app = FastAPI(title="Meta AI Scraper", lifespan=lifespan)

# API routes first (before Flet mount)
app.include_router(api_router)

# Flet UI at root (must be last — catch-all)
app.mount("/", flet_fastapi.app(flet_main))
