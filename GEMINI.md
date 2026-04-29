# GEMINI.md - SOC Triage System Instructional Context

## Project Overview
This project is a **SOC (Security Operations Center) Triage System** designed to automate the detection, analysis, and prioritization of security alerts. It utilizes machine learning for log anomaly detection and LLM-powered agents for automated triage and reporting.

### Tech Stack
- **Backend:** Python (FastAPI), LangChain (OpenAI), PyTorch (DeepLog/NeuralLog), Redis, Qdrant (Vector Database).
- **Frontend:** Next.js (TypeScript), Tailwind CSS.
- **Data Pipeline:** Log ingestion, sequence building, anomaly detection (DeepLog/NeuralLog), and automated triage.

### Architecture
1. **Ingestion Layer:** Consumes raw logs and builds sequences for analysis.
2. **Detection Layer:**
   - **DeepLog/NeuralLog:** ML models for identifying anomalous patterns in system/security logs.
3. **Queue/Router:** Orchestrates data flow between detection and triage components using Redis.
4. **Triage Layer:** 
   - **AI Agent:** Uses LangChain to perform deep analysis on alerts.
   - **Tools:** CVE lookup, IP reputation, MITRE ATT&CK mapping, and historical log analysis.
5. **Dashboard:** FastAPI backend and Next.js frontend for alert visualization and management.

---

## Building and Running

### Prerequisites
- Python 3.11+ (managed via `uv` or `pip`)
- Node.js & npm (for frontend)
- Redis & Qdrant (infrastructure services)

### Backend Setup
1. **Environment:**
   ```bash
   cd backend
   uv venv
   source .venv/bin/activate
   uv sync
   ```
2. **Infrastructure:**
   - Run setup scripts in `backend/scripts/`:
     ```bash
     bash scripts/setup_redis.sh
     bash scripts/setup_qdrant.sh
     ```
3. **Running the Pipeline:**
   - TODO: Define specific entry points for workers and the main API.
   - `python dashboard/main.py` (Likely entry point for the API).

### Frontend Setup
1. **Install dependencies:**
   ```bash
   cd frontend
   npm install
   ```
2. **Run development server:**
   ```bash
   npm run dev
   ```

### Testing
- Backend tests are located in `backend/tests/`.
- Run with: `pytest` (TODO: Verify specific test configurations).

---

## Development Conventions

### Coding Style
- **Python:** Adhere to PEP 8. Use type hints extensively as seen in `pyproject.toml`.
- **Frontend:** Follow Next.js App Router patterns and use Tailwind CSS for styling.

### Repository Structure
- `backend/`: Core logic, ML models, and API.
- `frontend/`: Dashboard UI.
- `context/`: Documentation and architectural diagrams.
- `data/`: Local storage for models, embeddings, and raw log samples.

### Key Components to Monitor
- `backend/triage/agent.py`: Core logic for the AI triage agent.
- `backend/detection/`: Implementation of DeepLog and NeuralLog models.
- `backend/dashboard/routes/`: API endpoints for the frontend.
- `backend/queue/`: Redis-based task routing logic.
