# MedNexus — Multi-Agent Healthcare Orchestration Platform

**MedNexus** is a multi-agent clinical intelligence system that processes multimodal medical data — X-rays, PDFs, lab CSVs, and patient audio recordings — through a pipeline of specialized AI agents, culminating in a cross-modality Diagnostic Synthesis Report.

Built on the **Microsoft Agent Framework** with **A2A (Agent-to-Agent)** communication, **MCP (Model Context Protocol)** for data abstraction, and **Azure AI Foundry** for intelligence.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   MedNexus Command Center (React + Tailwind) │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Patient   │  │ Clinical         │  │ Agent Chatter     │  │
│  │ Search    │  │ Workspace Grid   │  │ (Live A2A Stream) │  │
│  └──────────┘  └──────────────────┘  └───────────────────┘  │
└────────────────────────┬─────────────────────────────────────┘
                         │  WebSocket /ws/chatter
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend (REST + WebSocket)        │
│  /api/patients  |  /api/patients/{id}/upload  |  /health     │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      A2A Event Bus                           │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐     │
│  │ Orchestrator │◄►│ Clinical    │  │ Vision           │     │
│  │ Agent        │  │ Sorter      │  │ Specialist       │     │
│  └──────┬──────┘  └─────────────┘  └──────────────────┘     │
│         │          ┌─────────────┐  ┌──────────────────┐     │
│         ├─────────►│ Patient     │  │ Diagnostic       │     │
│         │          │ Historian   │  │ Synthesis Agent   │     │
│         │          └─────────────┘  └──────────────────┘     │
└─────────┼────────────────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────────────────────────┐
│  Azure Services                                              │
│  ┌─────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │
│  │Cosmos DB│ │AI Search  │ │Blob Store │ │OpenAI/GPT │      │
│  │(State)  │ │(RAG)      │ │(MCP)      │ │(LLM)      │      │
│  └─────────┘ └───────────┘ └───────────┘ └───────────┘      │
└──────────────────────────────────────────────────────────────┘
```

### Agent Pipeline

1. **Clinical Sorter** — Monitors the MCP drop-folder, classifies incoming files (PDF, DICOM, IMAGE, AUDIO, LAB_CSV) and extracts patient IDs from filenames. **Phase 3:** Primary consumer of the MCP Clinical Data Gateway — uses `get_patient_records` and `fetch_medical_image` tools.
2. **Vision Specialist** — Processes medical images via GPT-4o multimodal. Returns structured findings with region, observations, impression, and confidence scores. **Phase 3:** Routes image access through the Clinical Data Gateway for audit logging.
3. **Patient Historian** — Performs RAG via Azure AI Search. Extracts text from PDFs, transcribes audio (Whisper), and synthesizes patient history.
4. **Orchestrator** — State-machine controller. Routes files to appropriate specialists, tracks status transitions in Cosmos DB, and triggers synthesis when all modalities arrive.
5. **Diagnostic Synthesis** — Cross-modality analysis. Compares audio transcript statements against X-ray findings, identifies discrepancies, and produces a severity-rated Synthesis Report.

---

## Project Structure

```
mednexus-hackathon/
├── src/mednexus/
│   ├── agents/             # All agent implementations
│   │   ├── base.py         # BaseAgent ABC with A2A messaging
│   │   ├── orchestrator.py # State-machine handoff controller
│   │   ├── clinical_sorter.py
│   │   ├── vision_specialist.py
│   │   ├── patient_historian.py
│   │   └── diagnostic_synthesis.py
│   ├── a2a/                # Agent-to-Agent event bus
│   │   └── __init__.py     # In-process bus with WS broadcast
│   ├── api/
│   │   └── main.py         # FastAPI app (REST + WebSocket)
│   ├── mcp/                # Model Context Protocol abstraction
│   │   ├── base.py         # Abstract MCPServer interface
│   │   ├── local_fs.py     # Local filesystem MCP
│   │   ├── azure_blob.py   # Azure Blob Storage MCP
│   │   ├── factory.py      # Hot-swap factory
│   │   ├── clinical_gateway.py  # Phase 3: MCP SDK Clinical Data Gateway
│   │   └── audit.py        # Phase 3: HIPAA-compliant audit logger
│   ├── models/             # Pydantic v2 schemas
│   │   ├── clinical_context.py  # Core state document
│   │   ├── agent_messages.py    # A2A message envelope
│   │   └── medical_files.py     # File classification
│   ├── services/           # Azure SDK clients
│   │   ├── cosmos_client.py     # Cosmos DB state manager
│   │   ├── llm_client.py        # Azure OpenAI (multimodal)
│   │   ├── search_client.py     # AI Search RAG queries
│   │   └── speech_client.py     # Whisper transcription
│   ├── functions/
│   │   └── function_app.py # Azure Functions blob trigger
│   └── config.py           # pydantic-settings configuration
├── ui/                     # React + Vite + Tailwind frontend
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── ClinicalWorkspace.tsx
│   │   │   ├── AgentChatter.tsx
│   │   │   ├── FileUploader.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── cards/      # Multimodal display cards
│   │   ├── hooks/          # useWebSocket, usePatientContext
│   │   └── types.ts        # Shared TypeScript interfaces
│   ├── vite.config.ts
│   └── tailwind.config.js
├── data/intake/            # Local MCP drop-folder
├── docker-compose.yml
├── Dockerfile
├── Dockerfile.ui
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## Prerequisites

- **Python 3.11+**
- **Node.js 20+** (for the UI)
- An **Azure subscription** with the following services provisioned:
  - Azure OpenAI (GPT-4o deployment)
  - Azure Cosmos DB (NoSQL API)
  - Azure AI Search
  - Azure Blob Storage
  - Azure Speech Services (optional, for Whisper transcription)

---

## Quick Start

### 1. Clone & Configure

```bash
git clone <repo-url>
cd mednexus-hackathon
cp .env.example .env
# Fill in your Azure credentials in .env
```

### 2. Backend

```bash
# Create virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Start the API server
uvicorn mednexus.api.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd ui
npm install
npm run dev
# Open http://localhost:5173
```

### 4. Docker (alternative)

```bash
# Full stack (API + UI + Cosmos Emulator)
docker compose up --build

# Or production single image
docker build --target production -t mednexus .
docker run -p 8000:8000 --env-file .env mednexus
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint | Yes |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | Yes |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name (default: `gpt-4o`) | No |
| `COSMOS_ENDPOINT` | Cosmos DB endpoint | Yes |
| `COSMOS_KEY` | Cosmos DB primary key | Yes |
| `COSMOS_DATABASE` | Database name (default: `mednexus`) | No |
| `COSMOS_CONTAINER` | Container name (default: `clinical_contexts`) | No |
| `AZURE_SEARCH_ENDPOINT` | Azure AI Search endpoint | Yes |
| `AZURE_SEARCH_KEY` | Azure AI Search admin key | Yes |
| `AZURE_SEARCH_INDEX` | Search index name (default: `mednexus-clinical`) | No |
| `AZURE_STORAGE_CONNECTION_STRING` | Blob Storage connection string | No* |
| `AZURE_STORAGE_CONTAINER` | Blob container name | No* |
| `AZURE_SPEECH_KEY` | Azure Speech key (for Whisper) | No |
| `AZURE_SPEECH_REGION` | Azure Speech region (default: `eastus`) | No |
| `MCP_DROP_FOLDER` | Local file intake path (default: `./data/intake`) | No |
| `MEDNEXUS_CORS_ORIGINS` | Allowed CORS origins, comma-separated | No |

\* When `AZURE_STORAGE_CONNECTION_STRING` is set, the MCP layer uses Azure Blob Storage; otherwise it falls back to the local filesystem.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | System health & registered agents |
| `GET` | `/api/patients` | List all patient contexts |
| `GET` | `/api/patients/{id}` | Retrieve a patient's Clinical Context |
| `POST` | `/api/patients/{id}` | Create a new patient context |
| `POST` | `/api/patients/{id}/upload` | Upload a medical file → triggers agent pipeline |
| `POST` | `/api/patients/{id}/approve` | **Phase 3:** MD sign-off on Synthesis Report (Human-in-the-Loop) |
| `WS` | `/ws/chatter` | Live Agent-to-Agent message stream |
| `GET` | `/api/chatter/history` | Recent A2A messages for late-joining clients |

---

## Key Design Decisions

### MCP Abstraction
The MCP layer wraps data sources behind a uniform `list_files()` / `read_bytes()` / `watch()` interface. A factory function inspects configuration to return either `LocalFileSystemMCP` or `AzureBlobMCP` — agent code never changes.

### A2A In-Process Bus
Rather than HTTP-based inter-agent RPC, MedNexus uses an in-process async event bus with an observer pattern. Each A2A message is:
- Routed to the target agent's inbox
- Logged to a rolling history buffer
- Broadcast to all WebSocket observers (the UI's Agent Chatter pane)

### Status Semaphore
The `ClinicalContext.status` field acts as a state-machine semaphore (`intake → waiting_for_radiology → waiting_for_history → synthesizing → finalized`), preventing agents from processing out of order.

### Multimodal Vision
The Vision Specialist sends medical images as base64 payloads to GPT-4o's multimodal endpoint, receiving structured JSON findings with confidence scores.

### Cross-Modality Synthesis
The Diagnostic Synthesis Agent specifically compares **audio transcript statements** against **X-ray findings** to detect discrepancies — e.g., a patient says "no chest pain" but imaging shows a pulmonary infiltrate.

### Phase 3: Clinical Data Gateway (MCP SDK)
A proper MCP-protocol server (`clinical_gateway.py`) built with the Python `mcp` SDK. It exposes:
- **`get_patient_records`** tool — lists all files for a patient, grouped by modality, with patient-scoped access control.
- **`fetch_medical_image`** tool — returns base64-encoded image data with strict cross-patient access prevention.
- **`clinical_protocol`** resource — read-only hospital standard analysis protocol.

All tool invocations are **audit-logged** to `data/audit/mcp_audit.jsonl` (HIPAA-compliant structured entries) via the `MCPAuditLogger` class.

### Phase 3: Human-in-the-Loop MD Sign-Off
The Synthesis Report card in the AGUI includes a prominent **"Approve and Sign-off by MD"** button. When clicked, it prompts for the physician’s name and calls `POST /api/patients/{id}/approve`. The context transitions to `APPROVED` status with full attribution (who, when, notes). This ensures no diagnostic output leaves the system without a qualified human review.

---

## Development

```bash
# Run tests
pytest

# Lint & format
ruff check src/ --fix
ruff format src/

# Type checking
mypy src/
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Orchestration** | Microsoft Agent Framework, A2A Protocol |
| **Data Abstraction** | MCP (Model Context Protocol) |
| **Intelligence** | Azure OpenAI GPT-4o (text + vision) |
| **State** | Azure Cosmos DB (NoSQL API) |
| **Search / RAG** | Azure AI Search |
| **Storage** | Azure Blob Storage |
| **Speech** | Azure Speech / Whisper |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | React 19 + Vite 6 + TypeScript + Tailwind CSS |
| **Infrastructure** | Docker, Azure Functions |

---

## License

This project was built for [hackathon name]. See LICENSE for details.
