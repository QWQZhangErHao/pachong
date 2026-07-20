# 🕷️ Pachong — 分布式电商爬虫系统

> **World-class distributed e-commerce scraping system**  
> 从 URL 提交到结构化数据提取的全自动流水线，支持自适应反检测与弹性调度

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Async](https://img.shields.io/badge/Async-aiohttp%20%7C%20Playwright-orange.svg)]()
[![Kafka](https://img.shields.io/badge/Streaming-Kafka%20%7C%20Redis-black.svg)]()

---

## 🌟 核心特性

| 特性 | 说明 |
|------|------|
| 🚀 **四引擎自适应抓取** | HTTP/2 → Playwright → Nodriver 自动降级，应对 JS 挑战和反爬 |
| 🧠 **五层提取管道** | Schema.org → CSS/XPath → 自适应 IE → LLM 修复 → 多模态视觉，字段召回率 > 92% |
| ⚡ **分布式调度** | Kafka + Redis 令牌桶 + PostgreSQL，支持水平扩展 |
| 🛡️ **反检测系统** | 指纹随机化、代理轮换、请求速率自适应控制 |
| 📊 **实时监控** | Prometheus + Grafana + OpenTelemetry 全链路可观测 |
| 🌐 **Web 控制台** | Apple 风格 UI，实时任务状态与结果预览 |
| ☁️ **多云部署** | Docker Compose / Kubernetes (HPA) / AWS Lambda (Serverless) |

---

## 🏗️ 架构概览

```
┌─────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────┐
│  URL     │ → │  Scheduler  │ → │  四引擎抓取  │ → │ 五层提取  │
│  提交    │   │ (Kafka+Redis)│   │ HTTP/2→Play │   │ Schema→LLM│
└─────────┘   └────────────┘   └─────────────┘   └──────────┘
                                                    │
                                              ┌─────▼─────┐
                                              │  PostgreSQL│
                                              │  / MongoDB │
                                              └───────────┘
```

## 📁 项目结构

```
pachong/
├── api/               # FastAPI 路由层 (REST + WebSocket)
│   ├── routes/        # 具体端点（tasks, stats, batch）
│   └── services/      # 任务 CRUD 服务
├── core/              # 核心实体与配置
│   ├── config.py      # YAML 配置 + 热加载
│   ├── entities.py    # Pydantic 模型（Task, Result）
│   └── exceptions.py  # 自定义异常层级
├── scheduler/         # 调度器
│   ├── queue.py       # 优先级队列 + URL 去重
│   ├── rate_limiter.py# 域名级令牌桶 + 自适应信号量
│   └── dispatcher.py  # Kafka / Redis 分发
├── network/           # 网络与反检测
│   ├── http_client.py # aiohttp 连接池（按域名 Session）
│   ├── dns_cache.py   # DNS 缓存 + 预热
│   └── anti_detect/   # 浏览器指纹、代理、验证码
├── extractor/         # 数据提取管道
│   ├── pipeline.py    # 五层提取引擎编排
│   ├── schemas/       # Schema.org / 商品 / 文章定义
│   └── llm/           # LLM 修复与增强
├── queue/             # 消息队列抽象
├── storage/           # 存储层 (PostgreSQL, MongoDB, S3)
├── resilience/        # 弹性模式（熔断、重试、退避）
├── tracing/           # OpenTelemetry 可观测性
└── cli/               # 命令行入口 (Typer)
```

---

## ⚡ 快速开始

### 环境要求

- Python 3.12+
- PostgreSQL 15+
- Redis 7+
- Kafka 3+（可选，可用 Redis Streams 替代）
- Playwright Chromium 浏览器

### 安装

```bash
# 克隆仓库
git clone https://github.com/QWQZhangErHao/pachong.git
cd pachong

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 安装
pip install -e ".[dev]"

# 安装 Playwright 浏览器
playwright install chromium

# 配置
cp .env.example .env
# 编辑 .env 填入数据库、Redis 等配置

# 初始化数据库
alembic upgrade head
```

### 启动

```bash
# 启动 Web 控制台
pachong serve

# 或通过 uvicorn
uvicorn pachong.api.app:app --reload

# 启动爬虫 Worker
pachong worker

# 提交任务
pachong submit --url "https://example.com/product/123"

# 批量提交
pachong batch --file urls.txt
```

---

## 🧪 测试

```bash
# 运行所有测试
pytest

# 带覆盖率
pytest --cov=pachong --cov-report=html

# 性能测试 (Locust)
locust -f tests/load/locustfile.py
```

---

## 🐳 Docker 部署

```bash
# 本地生产模拟
docker compose up -d

# Kubernetes (HPA 自动扩缩)
kubectl apply -f deploy/k8s/
```

---

## 📊 可观测性

- **指标**: Prometheus (`/metrics`)
- **日志**: 结构化日志 (structlog)
- **追踪**: OpenTelemetry → Jaeger/Zipkin
- **告警**: Grafana 仪表盘

---

## 📄 License

MIT
