# RIFT 2026 — Autonomous DevOps Agent 🚀

An autonomous AI agent that fixes build/test failures in GitHub repositories. Built for the Rift 2026 competition.

![Dashboard Preview](./dashboard-preview.png)

## 🌟 Features

- **Autonomous Debugging**: Clones, tests, detects failures, and generates AI fixes using **Sarvam AI** (OpenAI-compatible).
- **Glassmorphism Dashboard**: Premium React + Vite UI with real-time logs and visualizations.
- **Smart Branching**: Creates `TEAM_LEADER_AI_Fix` branches and pushes fixes automatically.
- **CI/CD Monitoring**: Watches GitHub Actions pipelines and iterates until green.
- **Live Updates**: WebSocket-based real-time terminal logs and status updates.
- **Scoring System**: Calculates score based on speed and efficiency (starts at 100).

## 🛠️ Tech Stack

- **Backend**: Python 3.11+, FastAPI, GitPython, Pytest, Pydantic
- **Frontend**: React 19, Vite, Tailwind-style CSS (custom), Framer Motion
- **AI Provider**: Sarvam AI (`sarvam-m` model)
- **Database**: In-memory (with `results.json` persistence per repo)

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- GitHub Account (and a fine-grained PAT with `Contents: Read & Write` permissions)
- Sarvam AI API Key

### 1. Backend Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your SARVAM_API_KEY and GITHUB_TOKEN
```

### 2. Frontend Setup

```bash
cd frontend
npm install
```

### 3. Running the Application

**Start the Backend (Port 8080):**
```bash
cd backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

**Start the Dashboard (Port 5173):**
```bash
cd frontend
npm run dev
```

Open **http://localhost:5173** in your browser.

## 🎯 How to Use

1. Enter the **GitHub Repository URL** (e.g., `https://github.com/username/broken-repo`).
2. Enter your **Team Name** and **Leader Name**.
3. (Optional) Provide a GitHub Token if the repo is private or to unlock higher rate limits.
4. Click **Run Agent**.
5. Watch the agent clone, analyze, test, and fix bugs in real-time!
6. Once complete, view the **Score Breakdown**, **Fixes Table**, and **CI/CD Timeline**.

## 📊 Scoring System

- **Base Score**: 100 points
- **Speed Bonus**: +10 points if completed in < 5 minutes
- **Efficiency Penalty**: -2 points per commit over 20 commits
- **Final Score**: Calculated automatically at the end of the run.

## 📁 Project Structure

```
Rift2026/
├── backend/            # FastAPI Agent
│   ├── app/
│   │   ├── agent.py    # Core logic (Clone -> Test -> Fix -> Push)
│   │   ├── services/   # Git, TestRunner, FixGenerator (Sarvam AI)
│   │   └── main.py     # API & WebSocket endpoints
│   └── requirements.txt
├── frontend/           # React Dashboard
│   ├── src/components/ # Glassmorphism UI components
│   └── context/        # State management
└── results.json        # Generated results for the last run
```

## 📜 License

MIT License. Created for Rift 2026.
