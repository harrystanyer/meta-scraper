# Meta Scraper

A configurable AI provider scraper service that uses Playwright to automate Chrome instances and extract responses from Meta AI. Features a real-time Flet web dashboard, a REST API compatible with the Cloro monitor schema, and PostgreSQL-backed task persistence.

## Next steps
After speaking with Ricardo he mentioned the annoyance of UI changes on the AI providers side which then would break the scraper, a lot of the time at undesirable times. To combat this the next thing I would introduce is page caching when the service is working then upon a failure create a diff view to show exactly what has changed. If you were to then share this difference with an LLM this could make the change descisions and auto regenerate the pipeline config not needing any human interaction. I would suggest creating a ReAct agent which is triggered by high failure rates for a service which has access to an instance of the service, runs the service locally and iterates the config for the scraper based on the working and current web page data. After the ReAct loop confirms consistent scraping again this can be pushed to the production server. 

This agent could be extended to to be able to build new scraper configs (for new providers) or allow for when providers introduce new features we could add a natural language interface for the agent so we can then develop configs for anything. This method would require a configurable scraping engine which I imagine Cloro either already has or would not be difficult to introduce and then give the agent access to call the endpoints + edit the configs and you have a greatly extendable system.

## Deployment & Scaling

This service is designed to run on self-managed infrastructure (VPS providers like Hetzner, OVH, Contabo) rather than large cloud platforms. A single VPS should be able to run 3–5 Chromium instances. Each node runs its own independent Playwright pool. All nodes share a single PostgreSQL database. Then place a load balancer in front of all the nodes.

## Features

- **Multi-instance browser pool** — Spawns and coordinates up to 5 concurrent Playwright Chromium instances, each with its own serial task queue to prevent prompt overlap
- **Configurable pipelines** — Pipeline configs define the full browser automation flow: navigation, onboarding steps, input selectors, submit method, and response capture method
- **Three capture methods** — DOM polling (primary for Meta AI), WebSocket frame interception, or HTTP/fetch response parsing
- **Automated onboarding** — Handles Meta AI's Welcome dialog and age verification automatically on each new instance
- **Rate-limit detection & recovery** — Detects "maximum messages limit" responses, re-queues the failed task, and refreshes the browser context (new cookies/session) without killing the instance
- **Real-time dashboard** — Flet web UI with live metrics (success rate, queue depth, active instances), instance status, and recent activity
- **Request history** — Browsable, filterable log of every request with full prompt/response detail
- **Batch testing** — Built-in playground for single prompts or concurrent batch tests (up to 100 parallel)
- **Instance logs** — Per-instance structured logs with level and step filtering
- **Pipeline CRUD + page inspector** — Create/edit pipelines via the UI; auto-detect input fields, buttons, and WebSocket connections on any page
- **Cloro-compatible API** — `POST /v1/monitor/{pipeline}` follows the request/response schema from docs.cloro.dev

## Tech Stack


| Layer                  | Technology                    | Why                                                                                     |
| ---------------------- | ----------------------------- | --------------------------------------------------------------------------------------- |
| **Browser automation** | Playwright (Python, async)    | Reliable Chromium control, async-native, built-in selectors and wait APIs               |
| **Web UI**             | Flet 0.25+ via `flet.fastapi` | Material 3 components served as a web app alongside the API, no separate frontend build |
| **API**                | FastAPI + Uvicorn             | Async-first, automatic OpenAPI docs, dependency injection for DB sessions               |
| **Database**           | PostgreSQL + asyncpg          | Async driver, native UUID and JSON column support, connection pooling                   |
| **ORM**                | SQLAlchemy 2.0 (async)        | Declarative models, async session management, identity map                              |
| **Migrations**         | Alembic                       | Async-aware migration runner with SQLAlchemy metadata autogeneration                    |
| **Settings**           | pydantic-settings             | Typed config with env variable override (`META_SCRAPER_` prefix)                        |
| **HTTP client**        | httpx                         | Used by Flet UI views to call the local API (async)                                     |
| **Package manager**    | uv                            | Fast dependency resolution and virtualenv management                                    |
| **Linter**             | Ruff                          | Line length 100, rules E/F/I                                                            |


## Architecture Decisions

**Per-instance serial queues** — Each browser instance gets its own `asyncio.Queue` and dedicated worker coroutine. This guarantees prompts never overlap on the same browser tab, which was the root cause of early race conditions where multiple questions would merge into a single input field.

**DOM capture over WebSocket** — Meta AI uses GraphQL (`/api/graphql`) rather than WebSockets for streaming responses. The DOM capture method polls `[data-testid="assistant-message"]` elements, waits for a new element after submission, then monitors text stabilisation with a 5-second minimum wait to avoid capturing intermediate "Searching the web" states.

**Short-lived DB sessions for polling** — The `/v1/monitor` endpoint can poll for up to 15 minutes waiting for a response. Rather than holding an open DB session (which exhausted the connection pool at 100 concurrent requests), the endpoint closes its session immediately after enqueuing and opens a fresh session for each 0.5s poll check.

**Instance refresh over recycle** — When an instance hits Meta AI's rate limit, we close the browser context (clearing cookies/session state) and create a fresh one on the same browser process, rather than killing and re-launching the entire browser. This is faster and avoids Chromium process accumulation. Pending tasks from the instance's queue are drained back to the global queue.

**Flet UI polls the API** — The dashboard, history, and log views poll the REST API every 2-3 seconds rather than using the internal EventBus for push updates. The EventBus works in-process but can't reliably push to Flet web clients running in separate contexts.

**Pipeline-driven configuration** — All browser automation behaviour (selectors, onboarding steps, capture method, submit method) is stored in the `pipelines` DB table. This makes the scraper generic — you could add other AI providers without code changes by creating a new pipeline config.

## Project Structure

```
meta-scraper/
├── run.py                          # Uvicorn launcher
├── pyproject.toml                  # Dependencies & tooling config
├── alembic.ini                     # DB migration config
├── alembic/
│   ├── env.py                      # Async Alembic migration runner
│   └── versions/                   # Migration scripts
└── src/
    ├── main.py                     # FastAPI app factory + Flet mount + seed pipeline
    ├── config.py                   # Pydantic settings (DB URL, pool sizes, etc.)
    ├── events.py                   # In-process async pub/sub event bus
    ├── api/
    │   ├── router.py               # All REST endpoints under /v1
    │   └── schemas.py              # Pydantic request/response models
    ├── database/
    │   ├── models.py               # SQLAlchemy ORM models (tasks, pipelines, logs)
    │   ├── crud.py                 # All DB operations
    │   └── session.py              # Async engine + session factory
    ├── scraper/
    │   ├── manager.py              # Instance pool, task dispatcher, serial queues
    │   ├── instance.py             # Per-browser Playwright instance + capture logic
    │   ├── inspector.py            # Page element auto-detector
    │   ├── websocket_parser.py     # WebSocket frame parser
    │   └── fetch_parser.py         # HTTP/GraphQL response parser
    └── ui/
        ├── app.py                  # Flet app layout + navigation rail
        └── views/
            ├── dashboard.py        # Live metrics + instance status
            ├── history.py          # Request history browser
            ├── logs.py             # Instance log viewer
            ├── playground.py       # Single + batch prompt testing
            └── pipelines.py        # Pipeline CRUD + page inspector
```

## Quickstart

### Prerequisites

- **Python 3.11+**
- **PostgreSQL** (running locally on default port 5432)
- **uv** (Python package manager)

### 1. Install PostgreSQL

**macOS (Homebrew):**

```bash
brew install postgresql@17
brew services start postgresql@17
```

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### 2. Create the database

```bash
# Connect to PostgreSQL (macOS Homebrew uses your OS user by default)
psql -U postgres

# Or if that fails, try:
sudo -u postgres psql
```

```sql
CREATE DATABASE meta_scraper;
CREATE USER postgres WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE meta_scraper TO postgres;
\q
```

If the `postgres` user already exists, just create the database:

```sql
CREATE DATABASE meta_scraper;
\q
```

### 3. Clone and install dependencies

```bash
git clone https://github.com/harrystanyer/meta-scraper.git
cd meta-scraper

# Install Python dependencies
uv sync

# Install Playwright browsers
uv run playwright install chromium
```

### 4. Run database migrations

```bash
uv run alembic upgrade head
```

### 5. Start the service

```bash
uv run python run.py
```

The service starts on `http://localhost:8000`:

- **Web UI** — `http://localhost:8000` (Flet dashboard)
- **API docs** — `http://localhost:8000/docs` (Swagger/OpenAPI)
- **Metrics** — `http://localhost:8000/v1/metrics`

The default `meta-ai` pipeline is seeded automatically on first startup.

### 6. Send a test prompt

```bash
curl -X POST http://localhost:8000/v1/monitor/meta-ai \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is 5 * 5?", "country": "US", "include": {"rawResponse": false}}'
```

The first request will spawn a Chromium instance (visible by default), navigate to meta.ai, complete onboarding, and return the response. Subsequent requests reuse existing instances.

## Configuration

All settings can be overridden with environment variables prefixed with `META_SCRAPER_`:


| Setting              | Default                                                              | Env Var                           | Description                          |
| -------------------- | -------------------------------------------------------------------- | --------------------------------- | ------------------------------------ |
| `database_url`       | `postgresql+asyncpg://postgres:postgres@localhost:5432/meta_scraper` | `META_SCRAPER_DATABASE_URL`       | PostgreSQL connection string         |
| `pool_max_instances` | `5`                                                                  | `META_SCRAPER_POOL_MAX_INSTANCES` | Maximum concurrent browser instances |
| `headless`           | `false`                                                              | `META_SCRAPER_HEADLESS`           | Run browsers in headless mode        |


## API Endpoints


| Method   | Path                          | Description                                             |
| -------- | ----------------------------- | ------------------------------------------------------- |
| `POST`   | `/v1/monitor/{pipeline_name}` | Submit prompt, wait for response (long-poll)            |
| `GET`    | `/v1/async/task/{task_id}`    | Check status of a specific task                         |
| `GET`    | `/v1/tasks`                   | List all tasks (filterable by `status`, paginated)      |
| `GET`    | `/v1/pipelines`               | List all pipelines                                      |
| `POST`   | `/v1/pipelines`               | Create a new pipeline                                   |
| `GET`    | `/v1/pipelines/{id}`          | Get full pipeline config                                |
| `PUT`    | `/v1/pipelines/{id}`          | Update a pipeline                                       |
| `DELETE` | `/v1/pipelines/{id}`          | Delete a pipeline                                       |
| `POST`   | `/v1/inspect`                 | Auto-detect page elements (inputs, buttons, WebSockets) |
| `GET`    | `/v1/metrics`                 | Dashboard metrics (counts, rates, active instances)     |
| `GET`    | `/v1/logs`                    | Instance logs (filterable by `instance_id`, `level`)    |