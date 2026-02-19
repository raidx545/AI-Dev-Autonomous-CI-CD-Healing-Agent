# Autonomous DevOps Agent — Rift2026

## Project Overview

An **Autonomous DevOps Agent** with a **React Dashboard** that:
1. Takes a GitHub repository URL as input via web interface
2. Clones and analyzes the repository structure
3. Discovers and runs all test files automatically
4. Identifies all failures and generates AI-powered targeted fixes (using Google Gemini)
5. Commits fixes with `[AI-AGENT]` prefix and pushes to a new branch (`TEAMNAME_LEADERNAME_AI_Fix`)
6. Monitors CI/CD pipeline (GitHub Actions) and iterates until all tests pass
7. Displays comprehensive results in a premium React dashboard

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Dashboard (Vite)                     │
│  ┌──────────┐ ┌────────────┐ ┌──────────┐ ┌──────────────┐  │
│  │InputForm │ │RunSummary  │ │Pipeline  │ │  DiffViewer  │  │
│  │          │ │Card        │ │Logs      │ │              │  │
│  └────┬─────┘ └────────────┘ └──────────┘ └──────────────┘  │
│       │            ▲              ▲              ▲            │
│       │            └──────────────┴──────────────┘            │
│       ▼                    WebSocket                         │
├─────────────────────────────────────────────────────────────┤
│                    FastAPI Backend (:8000)                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                  Agent Orchestrator                     │  │
│  │  clone → analyze → test → fix → retest → commit/push  │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  │
│  │Clone     │ │Test      │ │Fix       │ │ CI/CD        │  │
│  │Service   │ │Runner    │ │Generator │ │ Monitor      │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  │
│  ┌──────────┐                                              │
│  │Git Ops   │                                              │
│  └──────────┘                                              │
└─────────────────────────────────────────────────────────────┘
         │               │                    │
    GitHub Repo      Gemini API         GitHub Actions API
```

---

## Directory Structure

```
Rift2026/
├── PROJECT_CONTEXT.md          ← This file (full project context)
├── .env.example                ← Environment variable template
├── .env                        ← Actual env vars (create from .env.example)
│
├── backend/
│   ├── requirements.txt        ← Python dependencies
│   └── app/
│       ├── __init__.py
│       ├── config.py           ← Settings from env vars (Pydantic)
│       ├── models.py           ← All data models (RunRequest, TestFailure, etc.)
│       ├── agent.py            ← Core orchestrator loop
│       ├── main.py             ← FastAPI app (REST + WebSocket)
│       └── services/
│           ├── __init__.py
│           ├── clone_service.py    ← Git clone + language/framework detection
│           ├── test_runner.py      ← Test discovery, execution, failure parsing
│           ├── fix_generator.py    ← Gemini AI-powered code fix generation
│           ├── git_ops.py          ← Branch, commit [AI-AGENT], push
│           └── cicd_monitor.py     ← GitHub Actions API polling
│
└── frontend/                   ← (Phase 3 — not yet built)
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── index.css           ← Dark glassmorphism design system
        ├── context/
        │   └── AgentContext.jsx ← Global state for agent run
        ├── hooks/
        │   └── useWebSocket.js ← WebSocket with auto-reconnect
        └── components/
            ├── InputForm.jsx       ← Repo URL, team name, leader name
            ├── RunSummaryCard.jsx   ← Status badge, branch, timings
            ├── PipelineLogs.jsx     ← Real-time terminal logs
            ├── IterationTimeline.jsx← Fix iteration history
            ├── DiffViewer.jsx       ← Side-by-side code diffs
            └── CICDStatus.jsx       ← CI/CD pipeline visualization
```

---

## Phase Completion Status

| Phase | Status | Notes |
|-------|--------|-------|
| **Phase 1: Planning** | ✅ Done | Architecture, models, directory structure designed |
| **Phase 2: Backend** | ✅ Done | All 9 files built, server tested (imports + endpoints) |
| **Phase 3: Frontend** | ⬜ TODO | React + Vite dashboard with glassmorphism UI |
| **Phase 4: Integration** | ⬜ TODO | End-to-end testing with real GitHub repos |
| **Phase 5: Documentation** | ⬜ TODO | README, setup guide, walkthrough |

---

## Backend Details (Phase 2 — COMPLETED)

### API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | Health check |
| `POST` | `/api/runs` | Start a new agent run (returns `run_id`) |
| `GET` | `/api/runs/{run_id}` | Get run status/summary |
| `GET` | `/api/runs` | List all runs |
| `WS` | `/ws/{run_id}` | WebSocket for real-time events |

### Agent Flow
```
1. Clone repo (git clone with token auth)
2. Analyze structure (detect language, test framework, file counts)
3. Install dependencies (pip install / npm install)
4. Create branch: TEAMNAME_LEADERNAME_AI_Fix
5. Run tests (pytest / jest / vitest / go test / mvn test)
6. If tests fail → iterate:
   a. Parse failures into structured TestFailure objects
   b. Locate source files (test_foo.py → foo.py)
   c. Build AI prompt with source + test + error context
   d. Call Gemini API to generate fix
   e. Apply fix, generate diff
   f. Re-run tests
   g. Repeat up to MAX_ITERATIONS (default: 5)
7. Commit all changes with "[AI-AGENT] Fix: ..." message
8. Push to remote
9. Monitor GitHub Actions CI/CD (poll every 15s, max 10min)
10. Return RunSummary
```

### WebSocket Events
Events sent to connected clients during a run:
- `phase_change` — agent moved to a new phase
- `log` — informational message
- `error` — something went wrong
- `ping` — keepalive

### Key Models
- **RunRequest**: `repo_url`, `team_name`, `leader_name`, `github_token`
- **TestFailure**: `test_name`, `file_path`, `error_message`, `error_type`, `line_number`
- **FileChange**: `file_path`, `original_content`, `fixed_content`, `diff`
- **RunSummary**: `branch_name`, `total_failures_detected`, `total_fixes_applied`, `cicd_status`, `total_time_seconds`

---

## Frontend Plan (Phase 3 — TODO)

### Design
- **Dark theme** with glassmorphism (glass cards, subtle blur, glow effects)
- **Color palette**: Deep purple/blue gradients
- **Typography**: Inter from Google Fonts
- **Animations**: Framer Motion for smooth transitions

### Key Components
1. **InputForm** — Repo URL, team name, leader name, GitHub token, "Start Analysis" button
2. **RunSummaryCard** — Shows repo URL, team/leader, branch name, failure/fix counts, pass/fail badge, total time
3. **PipelineLogs** — Terminal-style real-time log viewer with auto-scroll
4. **IterationTimeline** — Vertical timeline of fix iterations (⏳ → ✅/❌)
5. **DiffViewer** — Side-by-side code diff using `react-diff-viewer-continued`
6. **CICDStatus** — Live CI/CD pipeline visualization

### Dependencies
- `react`, `react-dom`, `react-router-dom`
- `framer-motion` — animations
- `react-diff-viewer-continued` — diff display
- `lucide-react` — icons
- `axios` — HTTP requests

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token with `repo` scope |
| `GEMINI_API_KEY` | Yes | Google Gemini API key for AI fix generation |
| `MAX_ITERATIONS` | No | Max fix attempts (default: 5) |

---

## How to Run (Current State)

```bash
# 1. Set up environment
cd /Users/raidx/Desktop/CodE/Projects/Rift2026
cp .env.example .env
# Edit .env with your actual keys

# 2. Install backend dependencies
cd backend
pip install -r requirements.txt

# 3. Start backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Test (in another terminal)
curl http://localhost:8000/health
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"repo_url":"https://github.com/OWNER/REPO","team_name":"MyTeam","leader_name":"MyName"}'
```

---

## Run Summary Card Requirements
The dashboard must display:
- Repository URL that was analyzed
- Team name and team leader name
- Branch name created (`TEAM_NAME_LEADER_AI_Fix`)
- Total failures detected and total fixes applied
- Final CI/CD status badge: **PASSED** (green) / **FAILED** (red)
- Total time taken (start to finish)
