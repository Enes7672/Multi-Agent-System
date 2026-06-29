# Multi-Agent System

6 AI agents collaborating via Ollama to build software projects.

## Agents

| Model | Agents | Focus |
|-------|--------|-------|
| codellama:7b | BackendDeveloper, DatabaseDeveloper | Python modules, SQL schemas |
| deepseek-coder:6.7b | ApiDeveloper, SecurityDeveloper | REST APIs, security audits |
| starcoder:3b | FrontendDeveloper, TestDeveloper | React/Vue components, unit tests |

## Quick Start

```bash
git clone https://github.com/your-user/multi-agent-system.git
cd multi-agent-system
pip install -r requirements.txt

ollama pull codellama:7b
ollama pull deepseek-coder:6.7b
ollama pull starcoder:3b

python main.py
```

## Tests

```bash
pytest tests/ -v
```

## Project Structure

```
multi-agent-system/
├── agents/              # 6 specialist agents + base class
├── core/                # Coordinator, Ollama client, hardware detection
├── nexus/               # Inter-agent message bus, SQLite storage
├── utils/               # Sandbox, validators, memory, templates
├── tests/               # Unit and integration tests
├── config.yaml          # Agent model mappings
├── main.py              # Entry point
└── requirements.txt
```

## How It Works

1. **Hardware detection** - System detects CPU/RAM/GPU and selects optimal models
2. **Project planning** - PlannerAgent breaks requirements into tasks
3. **Parallel execution** - Coordinator distributes tasks with dependency management
4. **Code generation** - Each agent generates code via Ollama
5. **Security review** - SecurityDeveloper audits all output
6. **Testing** - TestDeveloper writes unit tests for generated code

## License

MIT
