🧠 Multi-Agent System (MAS)

> **6 Agents. 3 LLMs. 1 Full-Stack Project.**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-0.1+-green.svg)](https://ollama.ai/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)](https://www.docker.com/)

---

## 🇹🇷 Türkçe Kısa Özet

Bu sistem, **Ollama** üzerinde çalışan 6 farklı uzman yapay zeka ajanını (Backend, Veritabanı, API, Güvenlik, Frontend, Test) bir araya getiren otonom bir yazılım geliştirme ekibidir. Kullanıcı sadece yüksek seviyeli gereksinimleri (ör. "E-Ticaret API'si") girdiğinde, sistem bu gereksinimleri analiz eder, görevlere böler, ajanları paralel olarak çalıştırır, kod üretir, güvenlik taraması yapar, testler yazar ve tüm projeyi eksiksiz bir klasör yapısıyla sunar. Tüm iletişim **Nexus** mesajlaşma katmanı üzerinden yürür ve öğrenme yeteneği için uzun süreli bellek (Long-term Memory) kullanır.

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Agent Breakdown](#-agent-breakdown)
- [Technology Stack](#-technology-stack)
- [How It Works (Step-by-Step)](#-how-it-works-step-by-step)
- [Installation & Setup](#-installation--setup)
- [Configuration](#-configuration)
- [Usage Guide](#-usage-guide)
- [Project Structure](#-project-structure)
- [Testing](#-testing)
- [Roadmap](#-roadmap)
- [License](#-license)

---

## 🚀 Overview

The **Multi-Agent System (MAS)** is a cutting-edge, asynchronous micro-framework designed to automate the entire software development lifecycle. It simulates a real-world engineering team where each member is an AI expert with a specific domain focus.

Unlike traditional code generators that produce monolithic outputs, this system employs **decentralized task decomposition**. A dedicated Planner Agent breaks down high-level requirements into atomic sub-tasks. These tasks are then distributed to specialized agents that run **concurrently** (respecting resource limits), communicating via a central event bus (Nexus) to share context, review code, and resolve dependencies.

The result is a fully structured project containing backend modules, database schemas, REST APIs, security configurations, frontend components (React/Vue), and a comprehensive test suite.

---

## ✨ Key Features

- **🤖 6 Specialized Agents**: Each agent uses a tailored LLM (Codellama, Deepseek-Coder, Starcoder) optimized for its role.
- **⚡ Asynchronous Parallel Execution**: Tasks with no dependencies run simultaneously, drastically reducing build time.
- **🧠 Long-Term Memory (RAG)**: Stores successful/unsuccessful patterns in SQLite and injects them into prompts to improve future code quality.
- **📡 Nexus Communication Layer**: A robust message bus with protocol handling, request-response mechanisms, and persistent SQLite storage for all inter-agent messages.
- **🛡️ Integrated Security & Validation**:
  - **Code Sandboxing**: Executes generated code securely via Docker.
  - **Security Agent**: Audits all code against OWASP guidelines.
  - **LLM Output Validator**: Checks syntax, detects dangerous patterns (eval, exec, SQLi).
- **💾 Hardware-Aware Resource Manager**: Detects CPU/RAM/GPU and dynamically adjusts the number of concurrent agents to prevent system overload.
- **🔁 Self-Healing Retry Logic**: Failed tasks are retried with contextual correction prompts (`CircuitBreaker` & `RetryManager`).
- **🧪 Auto Test Generation**: Automatically writes and executes unit/integration tests using Pytest or Jest.

---

## 🏗️ System Architecture

The system follows a layered, event-driven architecture:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER INPUT (Requirements)                       │
└─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     COORDINATOR (Orchestration Layer)                   │
│  - Project Lifecycle Management                                         │
│  - Task Dependency Graph Construction                                   │
│  - State Persistence (SQLite)                                           │
└──────────────┬──────────────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          NEXUS (Messaging Bus)                          │
│  - Publish/Subscribe                                                    │
│  - Protocol Handling (Task Assign, Code Review, Help)                   │
│  - Message History & Persistence                                        │
└──┬──────────────┬──────────────┬──────────────┬──────────────┬─────────┘
   │              │              │              │              │
   ▼              ▼              ▼              ▼              ▼
┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
│Backend │  │Database│  │  API   │  │Security│  │Frontend│  │  Test  │
│ Agent  │  │ Agent  │  │ Agent  │  │ Agent  │  │ Agent  │  │ Agent  │
│(Llama) │  │(Llama) │  │(DeepS.)│  │(DeepS.)│  │(StarC.)│  │(StarC.)│
└────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘  └────┬───┘
     │           │           │           │           │           │
     └───────────┴───────────┴───────────┴───────────┴───────────┘
                                   │
                                   ▼
                     ┌─────────────────────────┐
                     │    OLLAMA (LLM Engine)   │
                     │  (Local Inference Server) │
                     └─────────────────────────┘
                                   │
                                   ▼
                     ┌─────────────────────────┐
                     │   OUTPUT (Project Files) │
                     └─────────────────────────┘
Data Flow Details:

Ingress: User defines project scope via CLI.

Decomposition: Planner agent translates requirements into a JSON task list.

Dispatching: Coordinator builds a dependency graph and pushes ready tasks to Nexus.

Execution: Agents consume tasks, query Ollama, generate code, and publish results back to Nexus.

Validation: Security agent scans outputs; Test agent generates validation suites.

Assembly: Coordinator merges all generated files into a structured project directory.

🤖 Agent Breakdown
Agent Role	Model	Primary Responsibilities	Key Capabilities
Backend Developer	codellama:7b	Python modules, business logic, error handling	PEP8 compliance, type hints, refactoring
Database Developer	codellama:7b	Schema design, SQL queries, Alembic migrations	Normalization, indexing, ORM (SQLAlchemy)
API Developer	deepseek-coder:6.7b	RESTful endpoints, FastAPI/Flask apps, OpenAPI spec	Authentication, middleware, HTTP standards
Security Developer	deepseek-coder:6.7b	Vulnerability scanning, encryption modules, auditing	OWASP Top 10, penetration testing plans
Frontend Developer	starcoder:3b	React/Vue components, CSS/Tailwind, state management	Accessibility (a11y), responsive design
Test Developer	starcoder:3b	Unit tests, integration tests, E2E (Playwright)	AAA pattern, mocking, coverage reporting
🛠️ Technology Stack
Core Framework: Python 3.12+ (asyncio, dataclasses)

LLM Integration: Ollama (Local inference)

Database Persistence: aiosqlite (SQLite with async support)

Containerization: Docker (for sandboxed code execution)

Observability: OpenTelemetry (Optional)

Testing: pytest, pytest-asyncio (Backend), Jest (Frontend)

Security: cryptography, passlib, python-jose

Configuration: PyYAML, python-dotenv

⚙️ How It Works (Step-by-Step)
Here is a detailed breakdown of the execution pipeline:

Initialization (main.py):

Detects hardware specs (CPU/RAM/GPU).

Connects to Ollama and verifies required models are installed.

Initializes SQLite storage and Long-term Memory.

Registers all 6 agents with Nexus.

Project Creation (coordinator.create_project):

User provides a name, description, and requirements dictionary.

Coordinator creates a project record and initializes a Git repository.

Task Planning (coordinator.plan_project):

If a Planner agent is available, it decomposes requirements. Otherwise, a rule-based fallback creates tasks for each module/endpoint/component.

Tasks are assigned priorities (CRITICAL, HIGH, MEDIUM, LOW).

Dependencies are automatically linked (e.g., database depends on backend).

Parallel Execution (coordinator.execute_project):

Coordinator enters a loop, identifying tasks whose dependencies are satisfied.

A semaphore (configurable via hardware detection) limits concurrent tasks.

For each ready task:

The assigned agent executes agent.execute_task.

Agent builds a prompt (including existing code, project tree, and past memories).

Agent calls Ollama via _generate_with_ollama.

Raw output is parsed using extract_file_blocks to save files.

Output is validated (syntax & security).

Self-Correction (Retry Logic):

If a task fails, RetryManager catches the error.

The context is enriched with the error message and passed back to the agent.

Agent attempts to generate a corrected version (up to 3 retries).

Cross-Agent Review (_review_and_test):

Upon completion of the development phase, the Security and Test agents automatically review the generated code.

Security agent scans for vulnerabilities.

Test agent writes a test suite and runs it.

Final Assembly:

All generated files are saved under data/projects/<project_id>/.

A status report is returned to the user.

📦 Installation & Setup
Prerequisites
Python 3.12+: Ensure python and pip are installed.

Ollama: Install from ollama.ai and run ollama serve.

Docker: (Optional but recommended for sandbox). Ensure Docker daemon is running.

1. Clone the Repository
bash
git clone https://github.com/your-username/multi-agent-system.git
cd multi-agent-system
2. Create a Virtual Environment
bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
3. Install Dependencies
bash
pip install -r requirements.txt
4. Pull the Required LLM Models
The system uses specific models per agent. Pull them with Ollama:

bash
ollama pull codellama:7b
ollama pull deepseek-coder:6.7b
ollama pull starcoder:3b
(Ensure your system has at least 16GB of RAM to run all three simultaneously.)

5. Configure Environment
Copy the example environment file:

bash
cp .env.example .env
Edit .env if you changed the default Ollama URL or want to disable Docker.

🔧 Configuration
config.yaml
This file maps agents to models and defines resource limits.

yaml
agents:
  backend-developer:
    role: "backend-developer"
    model: "codellama:7b"
    capabilities: ["python_module", "class_design"]

resource_limits:
  max_memory_mb: 4096
  max_cpu_percent: 80
.env
Controls runtime environment variables:

OLLAMA_URL: Endpoint for the Ollama API.

TASK_TIMEOUT: Maximum time an agent can spend on a task (default: 300s).

MAX_RETRIES: Number of retry attempts for failed tasks.

DOCKER_REQUIRED: Set to false to disable Docker sandboxing (NOT recommended for production).

💻 Usage Guide
Running the Interactive CLI
Start the system using:

bash
python main.py
You will see a menu like this:

text
==================================================
MULTI-AGENT SYSTEM (6 AGENTS + NEXUS)
==================================================
1. Create Project
2. Execute Project
3. System Status
4. Agent Status
5. Nexus Stats
6. Recommended Models
7. Exit
Example Workflow:

Select 1 and enter a name (e.g., "E-Commerce API").

Paste the following JSON requirements:

json
{
  "modules": ["user_auth", "product_catalog"],
  "api_endpoints": ["/auth/login", "/products"],
  "frontend_components": ["LoginForm", "ProductList"]
}
Select 2 and enter the generated Project ID to execute all tasks.

Running the Demo (Automated)
For a quick demonstration without manual input, run:

bash
python demo_project.py
This script automatically creates and executes a sample e-commerce project, printing the entire flow to the console.

📁 Project Structure
text
multi-agent-system/
│
├── agents/                         # Agent implementations
│   ├── __init__.py
│   ├── base_agent.py               # Abstract class (Ollama integration, context mgmt)
│   ├── backend_developer.py        # codellama:7b
│   ├── database_developer.py       # codellama:7b
│   ├── api_developer.py            # deepseek-coder:6.7b
│   ├── security_developer.py       # deepseek-coder:6.7b
│   ├── frontend_developer.py       # starcoder:3b
│   ├── test_developer.py           # starcoder:3b
│   └── planner_agent.py            # Task decomposition logic
│
├── core/                           # Backend engine
│   ├── config.py                   # Config loader
│   ├── coordinator.py              # Task orchestration & project lifecycle
│   ├── hardware_detector.py        # CPU/RAM/GPU detection
│   ├── resource_manager.py         # Dynamic scaling, circuit breaker
│   └── ollama_client.py            # Async Ollama API wrapper
│
├── nexus/                          # Inter-agent communication
│   ├── __init__.py
│   ├── message.py                  # Message/MessageType definitions
│   ├── bus.py                      # Publish/Subscribe Event Bus
│   ├── protocol.py                 # Request/Response handlers
│   ├── storage.py                  # SQLite persistence
│   └── nexus.py                    # Main Nexus class (coordinates bus & storage)
│
├── utils/                          # Cross-cutting utilities
│   ├── __init__.py
│   ├── code_validator.py           # AST validation, dangerous pattern detection
│   ├── error_handler.py            # RetryManager, CircuitBreaker
│   ├── git_integration.py          # Automatic commits
│   ├── long_term_memory.py         # RAG memory (SQLite)
│   ├── sandbox.py                  # Docker/Restricted Python execution
│   ├── template_engine.py          # Centralized code templates
│   ├── test_runner.py              # pytest/jest execution
│   └── sql_safety.py               # SQL injection protection
│
├── tests/                          # Unit and integration tests
│   ├── conftest.py
│   ├── test_agents.py
│   ├── test_memory.py
│   ├── test_sandbox.py
│   └── test_validator.py
│
├── data/                           # Runtime data (auto-created)
│   ├── projects/                   # Generated project source codes
│   ├── nexus.db                    # Message history
│   └── memory.db                   # Long-term memory storage
│
├── config.yaml                     # Agent model mappings
├── .env.example                    # Environment variables template
├── requirements.txt                # Python dependencies
├── demo_project.py                 # Automated demo script
├── main.py                         # Entry point
└── README.md                       # This file
🧪 Testing
To ensure the system is stable, run the test suite:

bash
pytest tests/ -v
Test categories include:

Agent Code Generation: Validates that Backend/Database/API agents produce syntactically correct code.

Dependency Resolution: Ensures the Coordinator does not execute tasks before their dependencies are met.

Memory Retrieval: Verifies that the long-term memory correctly fetches relevant past examples.

Validator: Confirms that dangerous patterns (e.g., eval, exec) are correctly flagged.

🗺️ Roadmap
Base agent architecture and Ollama integration.

Parallel task execution with dependency graph.

Nexus message bus and SQLite persistence.

Hardware detection and dynamic resource management.

Graphical User Interface (GUI): A React-based dashboard to visualize agent workflows.

Advanced RAG: Integrate vector databases (ChromaDB) for semantic memory retrieval instead of keyword-based search.

Multi-Modal Support: Allow agents to process images/PDFs for frontend mockup generation.

Cloud Deployment: Helm charts for Kubernetes deployment.

📄 License
Distributed under the MIT License. See LICENSE for more information.

🌟 Contributing
Contributions are what make the open-source community such an amazing place. If you have suggestions for improving this system, please feel free to fork the repo and submit a pull request.

Fork the Project.

Create your Feature Branch (git checkout -b feature/AmazingFeature).

Commit your Changes (git commit -m 'Add some AmazingFeature').



 The "AI-as-a-Team" Philosophy
This project is not just a finished software product—it is a living case study of how a human architect can effectively direct, structure, and govern a Large Language Model (AI) to produce a complex, multi-layered system.

Instead of asking the AI for a single script, I approached it as a software engineering manager would approach a junior team:

Blueprint First: I started by defining the macro-architecture—6 specialized roles, a message bus (Nexus), a coordinator, and resource governance. I did not let the AI design the architecture; I imposed it.

Constrained Creativity: Each agent was given a strict prompt (AGENT_PROMPT) and a limited set of capabilities (AGENT_CAPABILITIES). This ensured that the AI's "creativity" stayed within the boundaries of its role (e.g., the Frontend agent never touches database logic).

Iterative Refinement: When the AI produced suboptimal code, I didn't rewrite it manually. Instead, I refined the system prompts and the template engine (template_engine.py) to guide the AI toward better outputs on the next run.

Built-in Feedback Loops: The Long-Term Memory and the Retry Manager are not just features; they are control mechanisms I designed to let the AI learn from its own mistakes without human intervention.

Tooling Layer: I wrapped the AI's raw output with validators (code_validator.py), security scanners, and sandboxes (sandbox.py) to ensure that even if the AI hallucinates, the system stays safe.

Key Takeaway: This project demonstrates that the future of software engineering is not about replacing humans with AI, but about orchestrating AI agents with clear boundaries, explicit roles, and robust feedback mechanisms. The code you see here is 90% AI-written—but the system design, the constraints, and the governing logic are 100% human.



Push to the Branch (git push origin feature/AmazingFeature).

Open a Pull Request.
