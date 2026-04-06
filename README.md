# Bookshop — Microservices Portfolio Project

A production-style online bookstore built as a DevOps portfolio project, demonstrating containerization, CI/CD, observability, and microservices architecture.

---

## Architecture

```
                        ┌─────────────┐
                        │   Browser   │
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │  Frontend   │  nginx · port 3000
                        └──────┬──────┘
                               │
                        ┌──────▼──────┐
                        │ API Gateway │  FastAPI · port 8000
                        │  JWT auth   │
                        └──┬──┬──┬───┘
                           │  │  │
             ┌─────────────┘  │  └─────────────┐
             │                │                 │
      ┌──────▼──────┐  ┌──────▼──────┐  ┌──────▼──────┐
      │ user-service│  │ book-service│  │order-service│
      │  port 8001  │  │  port 8002  │  │  port 8003  │
      └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
             │                │                 │
             └────────────────┘         ┌───────▼──────┐
                      │                 │   RabbitMQ   │
               ┌──────▼──────┐          └───────┬──────┘
               │ PostgreSQL  │          ┌───────▼──────┐
               └─────────────┘          │notification- │
                                        │   service    │
                                        │  port 8004   │
                                        └─────────────┘
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| frontend-service | 3000 | React SPA served by nginx |
| api-gateway | 8000 | JWT validation, request routing |
| user-service | 8001 | Registration, login, JWT issuance |
| book-service | 8002 | Book catalog CRUD |
| order-service | 8003 | Order management, inter-service calls |
| notification-service | 8004 | RabbitMQ consumer, email notifications |

### Infrastructure

| Component | Purpose |
|-----------|---------|
| PostgreSQL 15 | Persistent storage (separate DB per service) |
| RabbitMQ 3 | Async messaging between order and notification services |
| Prometheus | Metrics collection from all services |
| Grafana | Metrics visualization |

---

## Tech Stack

**Backend:** Python 3.11 · FastAPI · SQLAlchemy · Alembic · PyJWT · bcrypt · httpx · aio-pika  
**Frontend:** React 18 · Vite · React Router v6  
**Infrastructure:** Docker · Docker Compose · nginx  
**Observability:** Prometheus · Grafana · prometheus-fastapi-instrumentator  
**Testing:** pytest · pytest-asyncio · httpx · respx  

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Git

### 1. Clone the repository

```bash
git clone https://github.com/PiceOfPentogramm/bookshop.git
cd bookshop
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set your values:

```env
POSTGRES_USER=user
POSTGRES_PASSWORD=your-password
SECRET_KEY=your-secret-key-here
RABBITMQ_DEFAULT_USER=your-rabbitmq-user
RABBITMQ_DEFAULT_PASS=your-rabbitmq-password
RABBITMQ_URL=amqp://your-rabbitmq-user:your-rabbitmq-password@rabbitmq:5672/
```

Generate a secure `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Start all services

```bash
docker compose up --build
```

### 4. Access the application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API Gateway | http://localhost:8000 |
| Swagger (user) | http://localhost:8001/docs |
| Swagger (books) | http://localhost:8002/docs |
| Swagger (orders) | http://localhost:8003/docs |
| RabbitMQ UI | http://localhost:15672 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (admin/admin) |

---

## Running Tests

Each service has its own integration test suite. Tests use a real PostgreSQL test database and mock inter-service HTTP calls with `respx`.

```bash
# user-service
pytest user-service/tests -q

# book-service
pytest book-service/tests -q

# order-service
pytest order-service/tests -q

# notification-service
pytest notification-service/tests -q

# api-gateway
pytest api-gateway/tests -q
```

> Tests require PostgreSQL running locally on port 5432. Fastest way:
> ```bash
> docker run -d --name test-postgres -e POSTGRES_USER=user -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:15
> ```

---

## Project Structure

```
bookshop/
├── api-gateway/
├── book-service/
├── frontend-service/
├── grafana/
│   └── provisioning/
│       └── datasources/     # Prometheus auto-configured as datasource
├── notification-service/
├── order-service/
├── postgres/
│   └── init.sql             # Creates all databases on first run
├── prometheus/
│   └── prometheus.yaml
├── user-service/
├── docker-compose.yaml
├── .env.example
└── .gitattributes
```

---

## Development Process

The backend microservices were developed using AI-assisted generation (Claude Code CLI and GitHub Copilot) with manual architectural decisions, code review, and integration test validation at each stage.

**Workflow:**
1. Define service specification — endpoints, models, inter-service communication
2. Generate service code via AI tooling
3. Review generated code for correctness and security
4. Write and run integration tests against a real PostgreSQL instance
5. Fix bugs identified by tests
6. Write Dockerfile and add service to Docker Compose
7. Validate end-to-end in containerized environment

All infrastructure code (Dockerfiles, docker-compose, nginx config, Prometheus config) was written manually.

---

## DevSecOps

- Passwords and secrets stored in `.env` — never committed to git
- `.gitattributes` enforces LF line endings for shell scripts and Dockerfiles
- JWT tokens signed with HS256, 24-hour expiry
- Passwords hashed with bcrypt
- API Gateway validates all JWT tokens before forwarding to backend services
- Generic error messages on login to prevent user enumeration

