# MedNexus — Multi-Agent Healthcare Orchestration Platform

**MedNexus** is a multi-agent clinical intelligence system that processes multimodal medical data — X-rays, PDFs, lab CSVs, and patient audio recordings — through a pipeline of specialized AI agents, culminating in a cross-modality Diagnostic Synthesis Report.

Built on the **Microsoft Agent Framework** with **A2A (Agent-to-Agent)** communication, **MCP (Model Context Protocol)** for data abstraction, and **Azure AI Foundry** for intelligence.

> **Hackathon Categories:** Grand Prize — Build AI Applications & Agents | Best Multi-Agent System | Best Azure Integration | Best Enterprise Solution

---

## Hero Technologies Used

| Hackathon Requirement | How MedNexus Uses It |
|---|---|
| **Microsoft Agent Framework** | 5 specialized agents (Orchestrator, Clinical Sorter, Vision Specialist, Patient Historian, Diagnostic Synthesis) with a state-machine controller and async A2A event bus |
| **Azure MCP** | MCP abstraction layer with hot-swap factory (Local FS ↔ Azure Blob), plus a full MCP SDK Clinical Data Gateway server exposing `get_patient_records` and `fetch_medical_image` tools with HIPAA audit logging |
| **Microsoft Foundry / Azure OpenAI** | GPT-4o for multimodal vision analysis (X-rays), cross-modality synthesis, patient-facing chat, and real-time voice assistant via Azure OpenAI Realtime API |
| **GitHub Copilot Agent Mode** | Entire project built with GitHub Copilot Agent Mode in VS Code — architecture design, agent implementations, React UI, Docker configs, and iterative debugging |
| **Azure Deployment** | Deployed to Azure Container Apps (frontend + backend), backed by Cosmos DB, AI Search, Blob Storage, and Azure Speech Services |

---

## What is MedNexus?

A doctor receives an X-ray, a lab report, a voice recording from the patient, and a 40-page PDF history — all for the same visit. Today, they piece those together manually. MedNexus does it for them.

**MedNexus is an AI-powered clinical copilot that reads every file a doctor drops in — images, documents, audio, labs — and produces a single, unified Diagnostic Synthesis Report in seconds.**

### What it does

- **Drop files, get answers.** Upload an X-ray, a PDF referral, a patient voice note, and lab results. Five specialized AI agents analyze each one in parallel and merge the findings into one coherent report.
- **Catch what humans miss.** The system cross-references modalities automatically — if a patient says *"no chest pain"* but the X-ray shows a pulmonary infiltrate, MedNexus flags the discrepancy.
- **Doctor stays in control.** Nothing leaves the system without an MD sign-off. The doctor reviews the synthesis, approves it, and only then can it be shared.
- **Patients get clarity, not confusion.** Once approved, the doctor shares a secure link (or QR code). The patient opens a mobile-friendly portal that explains findings in plain, everyday language — no medical jargon.
- **Patients can ask questions.** The portal includes a text chat and a real-time voice assistant. Patients can ask *"What does this mean for me?"* and get answers scoped only to their own clinical data.
- **Full episode-based workflow.** Each visit is an episode. A patient can have many episodes over time, and each one tracks its own files, findings, synthesis, approval, and actions — giving doctors a longitudinal view.
- **Live agent transparency.** A real-time "Agent Chatter" pane shows every agent's reasoning as it works — what it found, what it decided, what it handed off — so doctors understand *how* the AI reached its conclusions.

### Who it's for

| Role | What they get |
|---|---|
| **Doctor** | A command center that turns raw multimodal files into a reviewed, approved diagnostic report — faster and with fewer blind spots |
| **Patient** | A personal portal with plain-language results, a chat to ask questions, and a voice assistant — accessible from any phone via a shared link |
| **Hospital** | Audit-logged, HIPAA-aware data access with doctor attribution on every clinical decision |

### The workflow in 30 seconds

```
 1. Doctor opens MedNexus → Patient Grid shows all patients at a glance
 2. Selects a patient → Uploads files (X-ray, PDF, audio, labs)
 3. AI agents process in parallel → Findings appear in real time
 4. Cross-modality Synthesis Report is generated automatically
 5. Doctor reviews, edits if needed, and signs off
 6. Clicks "Share" → QR code / link generated with a secure token
 7. Patient opens the portal on their phone
 8. Reads plain-language summary → Chats or voice-asks follow-up questions
```

---

## Architecture

```mermaid
flowchart TB
    subgraph UI["MedNexus Command Center — React + Tailwind"]
        PG[Patient Grid]
        CW[Clinical Workspace]
        AC[Agent Chatter]
        PP[Patient Portal]
    end

    subgraph API["FastAPI Backend — REST + WebSocket"]
        REST["REST API\n/api/patients • /upload • /approve"]
        WS["WebSocket\n/ws/chatter"]
        PORTAL["Portal Endpoints\n/portal/context • /portal/chat • /portal/voice"]
    end

    subgraph AGENTS["A2A Event Bus — Microsoft Agent Framework"]
        ORCH[Orchestrator Agent]
        CS[Clinical Sorter]
        VS[Vision Specialist]
        PH[Patient Historian]
        DS[Diagnostic Synthesis]
        ORCH <-->|task assign| CS
        ORCH <-->|task assign| VS
        ORCH <-->|task assign| PH
        ORCH -->|trigger| DS
    end

    subgraph MCP["MCP Layer"]
        GW[Clinical Data Gateway\nMCP SDK Server]
        FACTORY["MCP Factory\nLocal FS ↔ Azure Blob"]
        AUDIT["Audit Logger\nHIPAA-compliant JSONL"]
    end

    subgraph AZURE["Azure Services"]
        COSMOS[(Cosmos DB\nPatient State)]
        SEARCH[(AI Search\nRAG Index)]
        BLOB[(Blob Storage\nMedical Files)]
        OPENAI[Azure OpenAI\nGPT-4o Multimodal]
        REALTIME[Azure OpenAI\nRealtime Voice]
        SPEECH[Azure Speech\nWhisper STT]
    end

    UI -- HTTP/WS --> API
    API --> AGENTS
    AGENTS --> MCP
    MCP --> AZURE
    WS -.->|live broadcast| AC
    CS --> GW
    VS --> GW
    GW --> AUDIT
    DS --> OPENAI
    PH --> SEARCH
    PORTAL --> REALTIME
```

<details>
<summary>ASCII fallback (if Mermaid doesn't render)</summary>

```
┌──────────────────────────────────────────────────────────────┐
│                   MedNexus Command Center (React + Tailwind) │
│  ┌──────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Patient   │  │ Clinical         │  │ Agent Chatter     │  │
│  │ Grid      │  │ Workspace        │  │ (Live A2A Stream) │  │
│  └──────────┘  └──────────────────┘  └───────────────────┘  │
└────────────────────────┬─────────────────────────────────────┘
                         │  REST + WebSocket
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                     FastAPI Backend                           │
│  /api/patients  |  /upload  |  /approve  |  /portal/*        │
└────────────────────────┬─────────────────────────────────────┘
                         │
           ┌─────────────┼──────────────┐
           ▼             ▼              ▼
     ┌───────────┐ ┌───────────┐ ┌───────────────┐
     │ Clinical  │ │ Vision    │ │ Patient       │
     │ Sorter    │ │ Specialist│ │ Historian     │
     └─────┬─────┘ └─────┬─────┘ └───────┬───────┘
           └─────────────┼───────────────┘
                         ▼
              ┌─────────────────────┐
              │ Diagnostic Synthesis│
              └──────────┬──────────┘
                         │
    ┌────────────────────┼────────────────────┐
    ▼          ▼         ▼         ▼          ▼
┌────────┐┌────────┐┌────────┐┌────────┐┌────────┐
│CosmosDB││Search  ││Blob    ││OpenAI  ││Speech  │
│(State) ││(RAG)   ││(MCP)   ││(GPT-4o)││(Whisper│
└────────┘└────────┘└────────┘└────────┘└────────┘
```

</details>

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
## Responsible AI & Security

MedNexus is designed with healthcare-grade safety and compliance in mind:

| Principle | Implementation |
|---|---|
| **Human-in-the-Loop** | No diagnostic output leaves the system without an MD sign-off. The doctor reviews, optionally edits, and explicitly approves every Synthesis Report before it can be shared with the patient. |
| **Patient-Scoped Data Isolation** | The MCP Clinical Data Gateway enforces per-patient access boundaries. An agent processing Patient A cannot access Patient B's files — cross-patient access is blocked at the tool level, not just the UI. |
| **HIPAA-Compliant Audit Logging** | Every MCP tool invocation (file access, image fetch) is logged to `data/audit/mcp_audit.jsonl` with timestamp, agent ID, patient ID, tool name, and parameters. Every approval records the physician name, timestamp, and notes. |
| **Secure Portal Access** | Patient portals are accessed via JWT tokens with configurable expiry. Tokens are scoped to a single patient and signed with a server-side secret. No login credentials are exposed to patients — just a link or QR code. |
| **Transparent AI Reasoning** | The Agent Chatter pane shows every agent's decision chain in real time. Doctors can see what each agent found, what it decided, and why — building trust and enabling oversight. |
| **No PII in Agent Logs** | A2A messages broadcast to the UI contain agent reasoning summaries, not raw patient data. Structured clinical findings are stored only in the patient's Cosmos DB context document. |

---

## Try It — Judge Testing Guide

Sample files are included in `data/samples/` so you can test the full pipeline immediately.

### Quick Test (Live Deployment)

1. Open the deployed frontend (URL provided in submission)
2. Click any patient on the **Patient Grid** — or create a new one
3. Upload the sample files from `data/samples/`:
   - `chest_xray.png` — triggers Vision Specialist
   - `bloodwork.csv` — triggers Lab analysis
   - `patient_transcript.txt` — triggers audio/text processing
   - `referral_letter.pdf` — triggers PDF extraction + RAG indexing
4. Watch the **Agent Chatter** pane — you'll see each agent classify, analyze, and hand off in real time
5. Once all agents finish, the **Synthesis Report** card appears with cross-modality findings
6. Click **"Approve and Sign-off by MD"** → enter any name → report is finalized
7. Click **"Share"** → copy the link or scan the QR code
8. Open the link on your phone → see the **Patient Portal** with plain-language summary
9. Try the **text chat** ("What does my X-ray show?") and the **voice assistant** (tap the mic)

### Local Setup

See [Quick Start](#quick-start) below. After `docker compose up --build`, open `http://localhost:5173` and follow the same steps above.

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
| **Infrastructure** | Docker, Azure Container Apps, Azure Functions |
| **Dev Tools** | VS Code, GitHub Copilot Agent Mode, GitHub |

---

## Built With GitHub Copilot

This project was built end-to-end using **GitHub Copilot Agent Mode** in VS Code — from initial architecture design and agent implementations to the React UI, Docker configurations, Azure deployment scripts, and iterative debugging. Copilot Agent Mode was used not just for code generation but as an active development partner: researching APIs, diagnosing race conditions, auditing CSS for UI bugs, and reasoning through multi-agent orchestration patterns.

---

## License

This project was built for the **AI Dev Days Hackathon 2026**. See LICENSE for details.
