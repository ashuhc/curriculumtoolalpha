# Northeastern Economics · Course Scheduler

A collaborative web app for planning the **undergraduate** economics curriculum. Graduate courses (5000+) are excluded everywhere.

| Area | What it does |
|---|---|
| **Teaching Preferences** | Signed-in faculty rank up to six courses, choose Principles courses, and set Fall/Spring loads, overloads and unique circumstances. Each person's latest submission counts. |
| **Demand Estimator** | Projects enrollment from historical data with a growth multiplier (0.85×–1.50×), a history window and a trend. Sizes sections: large Principles lectures (100–200+), small classes (40–45), remote sections capped at 25. Scales weekly 65-min recitations (ECON 1125/1126) at 30 students per section. Checks prerequisite rules by course level. |
| **Master Schedule** | Matches instructors with a min-cost-flow optimizer that staffs mandatory core courses first. Places sections on `Course_Sequences.pdf` blocks: 1–5 and A–H for lectures, lab windows L–W for recitations, which never overlap their lecture. Offers a grid and a weekly calendar view. |
| **Collaboration** | Live updates over WebSockets, presence, section locks while editing, threaded comments on sections, and versioned publishing with a registrar catalog CSV export. |
| **Conflicts** | Flags unstaffed core sections, instructor time overlaps, recitations overlapping their lecture, and remote-cap violations. Also flags over/under-allocation against contracts (Tenured 3/yr; Full-time/Temporary 6/yr; Adjunct 1–2/yr) and mismatches between approved and requested overloads. |
| **Assistant** | A floating help widget that explains settings, metrics and workflows, and looks up courses and live numbers. It runs locally on rule-based intents; no API key is needed. |
| **Administration** | Scheduler-only management of submissions, the faculty roster and groups, overloads, the course catalog, user accounts and roles, enrollment uploads, and the publication history. |

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS v4, Zustand, lucide-react, Inter |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy 2, WebSockets (uvicorn) |
| Database | PostgreSQL 16 (Docker/production) or SQLite (zero-setup local development) |
| Auth | Role-based sign-in (`admin` = scheduler, `faculty`) with PBKDF2 password hashes and signed, expiring tokens |
| Infrastructure | Docker and Docker Compose, nginx, GitHub Actions CI, AWS ECR and ECS Fargate deploy workflow |

```
backend/
  main.py            FastAPI app (CORS, routers, lifespan)
  routers/           auth_routes · catalog · preferences · planning · collab (locks, comments, /ws) · data
  engine.py          forecasting + scheduling engine (framework-free)
  services.py        DB → engine adapter, plan cache, CSV builders
  auth.py            password hashing, tokens, role dependencies
  realtime.py        WebSocket hub (presence + broadcast)
  models.py          SQLAlchemy models    schemas.py  Pydantic models
  seed_db.py         loads ECON_Enrollment.xlsx, custom_faculty.json, faculty_overloads.json,
                     teacher_preferences.csv and the TEACHER_PREFERENCES.py course catalog
  tests/             pytest API suite (SQLite or PostgreSQL)
frontend/
  src/store/         Zustand stores: auth · plan settings · schedule cache · collaboration (WebSocket) · ui
  src/pages/         Overview · Demand · Schedule · Conflicts · Preferences · Admin · Login
  src/components/    app shell, section drawer, weekly calendar, assistant, design-system primitives
  nginx.conf.template  serves the SPA and proxies /api and /ws to the backend
docker-compose.yml   postgres + backend + frontend
.github/workflows/   ci.yml (tests on SQLite and Postgres, build, docker) · deploy-aws.yml (ECR and ECS)
infra/aws/           ECS task definition template
```

---

## Option A: run everything with Docker (recommended)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Colima).

```bash
cp .env.example .env          # optional: change passwords / AUTH_SECRET
docker compose up --build
```

Open **http://localhost:8080**. API docs are at http://localhost:8000/docs. On first start the backend seeds PostgreSQL from the source files.

```bash
docker compose down            # stop (data persists in the pgdata volume)
docker compose down -v         # stop and delete the database
```

## Option B: run locally in VS Code (no Docker)

Requires Python 3.9+ and Node 18+. Open two terminals (Terminal → Split Terminal).

**Terminal 1: API**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python seed_db.py                         # creates backend/scheduler.db (SQLite)
uvicorn main:app --reload                 # http://localhost:8000  (docs at /docs)
```

To use a local PostgreSQL instead of SQLite:

```bash
createdb econ_scheduler
export DATABASE_URL=postgresql://$(whoami)@localhost:5432/econ_scheduler
python seed_db.py && uvicorn main:app --reload
```

**Terminal 2: web app**

```bash
cd frontend
npm install
npm run dev                               # http://localhost:5173
```

### Sign-in accounts

`seed_db.py` creates these accounts. In development the login page lists them for one-click fill.

| Role | Email | Password |
|---|---|---|
| Scheduler (admin) | `admin@northeastern.edu` | `econpassword123` (or `$ADMIN_PASSWORD`) |
| Second scheduler | `scheduler2@northeastern.edu` | `scheduler123` |
| Faculty (linked to *Stone, Michael*) | `m.stone@northeastern.edu` | `faculty123` |

Set `SEED_DEMO_USERS=false` to create only the admin. Create real faculty accounts in **Administration → Users & roles** and link each to its roster entry.

**Try the collaboration features:** open the app in two different browsers (or a normal and a private window) and sign in as the two schedulers. Open the same section on **Master Schedule**. Click **Edit section** in one window and the other shows *Locked by…*. Reassign the instructor and the change appears in the other window immediately. Comments, presence avatars and publish notifications are live too.

### Tests

```bash
cd backend && pytest -q                                       # SQLite
DATABASE_URL=postgresql://localhost/econ_test pytest -q       # PostgreSQL
cd frontend && npm run build                                  # type-check + production build
```

---

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite `backend/scheduler.db` | `postgresql://…` or `postgres://…` URLs are accepted |
| `AUTH_SECRET` | random, saved to `backend/.auth_secret` | token signing key. **Set it in production** |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `admin@northeastern.edu` / `econpassword123` | first scheduler account |
| `SEED_DEMO_USERS` | `true` | also seed the demo scheduler and faculty accounts |
| `CORS_ORIGINS` | localhost dev origins | comma-separated allowed origins |
| `SCHEDULER_DATA_DIR` | repo root | where `seed_db.py` reads the source files |
| `VITE_API_URL` | `http://localhost:8000` | frontend → API URL; empty means same origin (Docker/nginx) |

### Single sign-on (Auth0 / Northeastern SSO)

The app uses its own role-based accounts. All authorization goes through one dependency, `auth.current_user`. To move to Auth0 or university SSO, replace `decode_token()` in `backend/auth.py` with JWKS verification of the identity provider's access token, and map its role claim onto `User.role`. On the frontend, replace the sign-in form with the provider's login redirect.

## Deploying to AWS

`.github/workflows/deploy-aws.yml` runs on version tags (`v*`) or manually. It builds both images, pushes them to ECR and rolls out an ECS Fargate service using `infra/aws/task-definition.json`. The `web` (nginx) and `api` containers share a task; nginx proxies to `localhost:8000`.

One-time setup:
1. Create ECR repositories `econ-scheduler-api` and `econ-scheduler-web`, plus an ECS cluster and service (behind an ALB on port 80 of `web`).
2. Create RDS PostgreSQL. Store `DATABASE_URL`, `AUTH_SECRET` and `ADMIN_PASSWORD` in Secrets Manager, then fill the ARNs, account ID, region and your domain into the task definition.
3. Create an IAM role trusted for GitHub OIDC with ECR push and ECS deploy permissions.
4. In the GitHub repo, set secret `AWS_ROLE_ARN` and variables `AWS_REGION`, `ECS_CLUSTER` and `ECS_SERVICE`.

Run **one API task**. The WebSocket hub and plan cache are in-process, so scaling out horizontally needs a shared pub/sub such as Redis, as noted in `realtime.py`.

## Legacy prototype

`COURSE_SCHEDULER.py` and `TEACHER_PREFERENCES.py` (Streamlit) still run against the original files with `streamlit run COURSE_SCHEDULER.py`. They share the same engine through `scheduler_engine.py`, a shim around `backend/engine.py`.
