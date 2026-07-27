# 🕷️ Pachong — 分布式电商爬虫系统

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/Kafka-3%2B-231F20?logo=apachekafka" alt="Kafka">
  <img src="https://img.shields.io/badge/PostgreSQL-15%2B-4169E1?logo=postgresql" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Redis-7%2B-DC382D?logo=redis" alt="Redis">
  <img src="https://img.shields.io/badge/Playwright-Chromium-45BA4B?logo=playwright" alt="Playwright">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  <a href="#-quick-demo"><img src="https://img.shields.io/badge/Try%20Now-No%20Setup-2ea44f" alt="Try Now - No Setup"></a>
</p>

<p align="center">
  <b>From URL submission to structured data extraction — fully automated pipeline</b><br>
  4-Engine Adaptive Scraping · 5-Layer Extraction · Elastic Distributed Scheduling · Full Anti-Detection
</p>

---

## 🚀 Quick Demo

> **无须 PostgreSQL、Redis、Kafka**，克隆后直接运行：

```bash
git clone https://github.com/QWQZhangErHao/pachong.git
cd pachong
pip install -e ".[dev]"
python demo.py
```

你会看到 7 个步骤依次执行，模拟完整的爬虫+提取流水线：

```
============================================================
  Pachong - End-to-End E-Commerce Scraping Demo
============================================================

[Step 1] URL Priority Scoring
---------------------------------------------
  [HIGH] [product  ] score= 95  https://amazon.cn/dp/B0CJ5YHZ7V
  [LOW ] [cart     ] score= 10  https://shop.example.com/cart
  [MED ] [category ] score= 40  https://store.example.com/category/headphones
  [LOW ] [login    ] score=  5  https://mall.example.com/login

[Step 2] Geo-Bound Browser Identity
---------------------------------------------
  Language:   zh-CN (zh-CN, zh, en)
  Platform:   Win32
  Screen:     1920x1080
  UA:         Mozilla/5.0 (Windows NT 10.0; Win64; x64)...

[Step 5] Five-Tier Extraction Pipeline
  Title      -> Apple AirPods Pro (2nd Gen) with MagSafe Charging Case
  Price      -> 1799.00
  SKU        -> 10004578091234
  Rating     -> 4.8
  Reviews    -> 528000
```

<details>
<summary>📸 Web Console Screenshots</summary>
<br>

> *(Screenshots welcome — open a PR to add yours!)*

| Feature | Preview |
|---------|---------|
| Dashboard | *Coming soon* |
| Task Detail | *Coming soon* |
| Live Logs | *Coming soon* |

</details>

---

## 🌟 Core Features

### 🚀 4-Engine Adaptive Scraping

| Engine | Priority | Use Case |
|--------|----------|----------|
| **HTTP/2** | 1st | Static/simple pages — aiohttp pool, fastest |
| **Playwright** | 2nd | JS-rendered pages — Chromium pool, handles SPA |
| **Nodriver** | 3rd | Experimental — lightweight headless |
| **Auto-degrade** | Fallback | Anti-bot escalation — detects failure, switches engine |

### 🧠 5-Layer Data Extraction

```
Layer 1: Schema.org / JSON-LD   →  Structured markup
Layer 2: CSS / XPath Selectors  →  Precise field targeting
Layer 3: Adaptive IE (spaCy)    →  NER entity recognition
Layer 4: LLM Repair (GPT-4o)    →  Missing field completion
Layer 5: Multimodal Vision      →  Screenshot OCR + image understanding
```

> **Field recall rate > 92%** — All 5 layers run in parallel, results fused

### ⚡ Elastic Scheduling

```
URL Submission → Priority Queue → Dedup → Token Bucket → Kafka/Redis → Workers
```

- **Per-domain token bucket** — independent rate limiting
- **Adaptive semaphore** — dynamic concurrency based on anti-bot feedback
- **Resumable** — auto-recover unfinished tasks after crash

### 🛡️ Full Anti-Detection

- Browser fingerprint randomization (Canvas/WebGL/Font per request)
- Proxy rotation (HTTP/SOCKS5 pool)
- PID controller for adaptive rate control
- Cookie isolation per domain

### 📊 Observability

Prometheus + Grafana + OpenTelemetry — dashboards for tasks, latency, error rate, circuit breaker state.

---

## ⚡ Quick Start

### 🎮 Zero-Dependency Demo

```bash
pip install -e ".[dev]"
python demo.py
```

### 🧪 Full Setup

#### Prerequisites

- Python 3.12+
- PostgreSQL 15+
- Redis 7+
- Kafka 3+ (optional — Redis Streams can substitute)
- Playwright Chromium

#### Installation

```bash
# Clone
git clone https://github.com/QWQZhangErHao/pachong.git
cd pachong

# Virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -e ".[dev]"
playwright install chromium

# Configure
cp .env.example .env
# Edit .env with your database, Redis config

# Initialize DB
alembic upgrade head
```

#### Running

```bash
# Start web console
pachong serve

# Or dev mode
uvicorn pachong.api.app:app --reload --port 8000

# Start worker
pachong worker

# Submit a single task
pachong submit --url "https://example.com/product/123" --priority 80

# Batch submit
pachong batch --file urls.txt

# Export results
pachong export --format csv --output results.csv
```

#### Docker

```bash
# Local full environment
docker compose up -d

# Production
docker compose -f deploy/docker-compose.prod.yml up -d

# Kubernetes
kubectl apply -f deploy/k8s/
```

---

## 📡 API Usage

```bash
# Submit a task
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/product/123", "priority": 80}'

# Query task status
curl http://localhost:8000/api/tasks/{task_id}

# Get results
curl http://localhost:8000/api/tasks/{task_id}/result

# Batch submit
curl -X POST http://localhost:8000/api/batch -F "file=@urls.txt"

# Stats overview
curl http://localhost:8000/api/stats
```

### WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/tasks/{task_id}');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}%, Status: ${data.status}`);
};
```

---

## 🧰 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | Native HTML/CSS/JS (Apple Design System) | Web Console |
| **API** | FastAPI + Uvicorn | REST + WebSocket |
| **Async HTTP** | aiohttp (HTTP/2 pool), httpx | Network requests |
| **Browser** | Playwright (Chromium), Nodriver | JS rendering |
| **Queue** | Kafka / Redis Streams | Task distribution |
| **DB** | PostgreSQL + SQLAlchemy 2.0 (async) | Task & result storage |
| **Cache** | Redis (token bucket, circuit breaker, LLM cache) | Performance |
| **Storage** | MinIO / S3 | Raw HTML, screenshots |
| **Observability** | Prometheus + Grafana + OpenTelemetry | Monitoring |
| **Deploy** | Docker Compose / Kubernetes (HPA) / AWS Lambda | Deployment |

---

## 🏗️ Architecture

<details>
<summary>Click to expand — System Architecture</summary>

```
+-----------------------------------------------------------+
|                        Clients                              |
|  CLI (Typer) │ Web Console │ API (REST/WebSocket)          |
+---------------------------+-------------------------------+
                            | URL Submission
+---------------------------v-------------------------------+
|                    Scheduler Layer                          |
|  Priority Queue · URL Dedup · Token Bucket · Dispatcher    |
+-----------------------------------------------------------+
                            |
+---------------------------v-------------------------------+
|                     Network Layer                           |
|  4-Engine Adaptive Scraping                                |
|  HTTP/2 ← Playwright ← Nodriver (auto-degrade)            |
|  Fingerprint · Proxy Rotation · Rate Control               |
+-----------------------------------------------------------+
                            | Raw HTML / Screenshots
+---------------------------v-------------------------------+
|                    Extractor Layer                          |
|  5-Layer Parallel Pipeline                                 |
|  Schema → CSS/XPath → IE → LLM → Multimodal Vision        |
|  Result Fusion · Field Validation · Format Normalization   |
+-----------------------------------------------------------+
                            | Structured Data
+---------------------------v-------------------------------+
|                     Storage Layer                           |
|  PostgreSQL (Tasks) │ MongoDB (Results) │ MinIO/S3 (Raw)   |
+-----------------------------------------------------------+
```

</details>

<details>
<summary>Click to expand — Extraction Pipeline Flow</summary>

```
                    +------------------+
                    |    Raw HTML      |
                    |   + Screenshots  |
                    +--------+---------+
           +-----------------+-----------------+
           v                 v                 v
    +-----------+    +-----------+    +-----------+
    | Schema    |    | CSS/XPath |    | Adaptive  |
    | org/      |    | Selectors |    | IE (spaCy)|
    | JSON-LD   |    |           |    |           |
    +----+------+    +-----+-----+    +-----+-----+
         |                  |                |
         +--------+---------+--------+------+
                  v                  v
           +-----------+     +-----------+
           | LLM Fix   |     | Multimodal|
           | (GPT-4o)  |     | Vision    |
           +----+------+     +-----+-----+
                |                  |
                +--------+---------+
                         v
                  +------------------+
                  |  Result Fuser    |
                  |  Field Validate  |
                  |  Format Normalize|
                  +------------------+
```

</details>

### Field Coverage Matrix

| Field | Layer 1 | Layer 2 | Layer 3 | Layer 4 | Layer 5 |
|-------|:-------:|:-------:|:-------:|:-------:|:-------:|
| Product Title | ✅ | ✅ | ✅ | ✅ | ✅ |
| Price | ✅ | ✅ | ✅ | ✅ | ❌ |
| Description | ✅ | ✅ | ✅ | ✅ | ✅ |
| Image URL | ✅ | ✅ | ❌ | ❌ | ✅ |
| SKU/Variant | ✅ | ✅ | ❌ | ✅ | ❌ |
| Rating | ✅ | ✅ | ❌ | ✅ | ❌ |
| Stock | ❌ | ✅ | ❌ | ✅ | ❌ |
| Category | ✅ | ✅ | ✅ | ✅ | ❌ |

<details>
<summary>Click to expand — Anti-Detection System</summary>

```
+-----------------------------------------------------+
|              Anti-Detection Engine                    |
+-----------------------------------------------------+
|  +-------------+  +----------+  +---------+         |
|  | Fingerprint  |  | Proxy    |  | Rate    |        |
|  | Randomization|  | Rotation |  | Control |        |
|  | - Canvas     |  | - HTTP   |  | - PID   |        |
|  | - WebGL      |  | - SOCKS5 |  | - Adaptive      |
|  | - Font       |  | - Auto   |  | - Backoff       |
|  | - Audio      |  | - Health |  |         |        |
|  +-------------+  +----------+  +---------+         |
|  +-------------------------------------------------+ |
|  |          Circuit Breaker                         | |
|  |  LLM Calls · Playwright · Per-domain             | |
|  |  Failure Count -> Open -> Cool -> Half -> Close  | |
|  +-------------------------------------------------+ |
+-----------------------------------------------------+
```

</details>

---

## 📁 Project Structure

```
pachong/                          # 📦 Source code
├── api/                          # FastAPI routing layer
├── cli/                          # Typer CLI entrypoint
├── core/                         # Config, models, exceptions
├── network/                      # HTTP, browser pool, anti-detection
├── extractor/                    # 5-layer extraction pipeline
├── scheduler/                    # Priority queue, rate limiter
├── queue/                        # Kafka/Redis message backends
├── storage/                      # PostgreSQL, Redis, S3, MongoDB
├── resilience/                   # Circuit breaker, metrics
├── anti_detect/                  # Fingerprint, identity, proxy
├── serverless/                   # AWS Lambda / GCP functions
└── tracing/                      # OpenTelemetry setup

scripts/                          # 🛠️ Helper scripts
├── build.bat                     # Build & package (Windows)
├── start.bat                     # Quick-start server (Windows)
├── pachong.bat                   # CLI frontend (Windows)
├── pachong.spec                  # PyInstaller spec
├── submit.py                     # URL submission tool
├── package.py                    # Portable distribution packager
├── seed_proxies.py               # Seed dev proxy pool
├── init_db.sh                    # DB initialization
└── urls.txt                      # Sample URLs for batch testing

config/                           # ⚙️ Configuration
├── default.yaml                  # Default settings
├── development.yaml              # Dev overrides
└── production.yaml               # Prod overrides

deploy/                           # 🚀 Deployment
├── docker/                       # Dockerfiles + compose
├── k8s/                          # Kubernetes manifests
├── monitoring/                   # Prometheus + Grafana
└── serverless/                   # Lambda/GCP handlers

tests/                            # 🧪 Tests
├── unit/                         # Unit tests
└── integration/                  # Integration tests

📄 Root files
├── demo.py                       # Zero-dependency demo (start here!)
├── Makefile                      # Build commands
├── pyproject.toml                # Project metadata & dependencies
├── README.md                     # This file
├── CLAUDE.md                     # AI assistant instructions
├── alembic.ini                   # DB migrations config
└── .env.example                  # Environment template
```

---

## 📊 Observability

| Tool | Endpoint | Purpose |
|------|----------|---------|
| **Prometheus** | `/metrics` | Collection (requests, latency, error rate) |
| **Grafana** | Pre-built dashboards | Visual monitoring |
| **OpenTelemetry** | OTLP Exporter | Distributed tracing → Jaeger/Zipkin |
| **Structlog** | Structured logging | Contextual logs with `task_id` |

### Key Metrics

```
pachong_tasks_total{status="completed"}     # Completed tasks
pachong_tasks_total{status="failed"}        # Failed tasks
pachong_scrape_duration_seconds            # Scrape duration
pachong_extraction_recall_rate             # Field recall rate
pachong_ban_detector_blocked              # Anti-bot triggers
pachong_circuit_breaker_open              # Circuit breaker count
```

---

## 🧪 Development

```bash
# Tests
pytest -v
pytest --cov=pachong --cov-report=html   # With coverage
locust -f tests/load/locustfile.py       # Load testing

# Code quality
ruff format . && ruff check . && mypy pachong/

# Workflow
docker compose up -d postgres redis       # Start deps
uvicorn pachong.api.app:app --reload      # Dev server
pytest tests/ -v                          # Run tests
```

---

## ⚠️ FAQ & Pitfalls

| Issue | Symptoms | Solution |
|-------|----------|----------|
| Windows Firewall | All tasks fallback to demo | Check firewall/proxy, `curl` test external connectivity |
| Playwright launch fail | `Error: browserType.launch` | `playwright install chromium`, set `PLAYWRIGHT_BROWSERS_PATH` |
| Low LLM cache hit | Repeated API calls | Cache key uses first 10KB HTML + structure signature |
| Redis pool exhausted | `ConnectionError` | `max_connections: 50`, use `redis.asyncio.ConnectionPool` |
| PostgreSQL deadlock | `could not serialize access` | `asyncpg` + `isolation_level="read_committed"` |
| False anti-bot triggers | Legit requests banned | Adjust PID parameters, increase proxy pool size |

---

## 🗺️ Roadmap

- [x] Zero-dependency demo script (`python demo.py`)
- [ ] WebSocket real-time task progress push
- [ ] Browser fingerprint rotation store
- [ ] Adaptive retry strategy (dynamic backoff by error type)
- [ ] One-click export to Excel/PDF
- [ ] Slack/DingTalk bot alert integration
- [ ] AI-powered CAPTCHA auto-solver

---

## 🤝 Contributing

```bash
# 1. Fork the project
# 2. Create your feature branch
git checkout -b feat/amazing-feature
# 3. Commit changes
git commit -m "feat: add amazing feature"
# 4. Push
git push origin feat/amazing-feature
# 5. Open a Pull Request
```

---

## 📄 License

[MIT](LICENSE) © Pachong Team

---

<p align="center">
  <sub>Built with Rust-level performance ambition in Python · Open an Issue for questions</sub>
</p>
