# Edini — Houdini AI Assistant

Natural language AI assistant for Houdini 21, powered by [Pi](https://github.com/earendil-works/pi-coding-agent).

## Features

- **Natural language node creation** — "Create a smoke simulation"
- **Parameter control** — "Set the grid size to 0.1"
- **VEX & Python scripting** — "Write a VEX expression to scatter points"
- **Scene inspection** — "What's connected to this node?"
- **HDA creation** — "Package this network as a digital asset"
- **Streaming responses** — See the AI think and act in real-time

## Prerequisites

- Houdini 21 (PySide6)
- Node.js 18+ (for Pi)

## Quick Start

```bash
# 1. Install Pi
npm install -g @earendil-works/pi-coding-agent

# 2. Set API key
set ANTHROPIC_API_KEY=sk-ant-...

# 3. Install Edini into Houdini
#    Run from Houdini Python Shell or with hython:
python scripts/install.py

# 4. Restart Houdini, then in Python Shell:
from edini import createPanel
panel = createPanel()
panel.show()
```

## Architecture

```
Houdini (Python/PySide6)              Pi (Node.js)
┌─────────────────────┐              ┌──────────────────┐
│  Edini Panel (UI)   │  JSON-RPC    │  Pi Agent Core   │
│  +- Chat View       │<-stdin/stdout->|  +- Model         │
│  +- Tool Cards      │              │  +- Tool System   │
│  +- Input Bar       │              │  +- Extensions    │
│        │            │              │        │          │
│  ┌─────v──────────┐ │              │  ┌─────v────────┐ │
│  │ Tool Executor  │ │<---HTTP------│  │ Edini Tools  │ │
│  │ (houp server)  │ │              │  │ (TypeScript)  │ │
│  └────────────────┘ │              │  └──────────────┘ │
└─────────────────────┘              └──────────────────┘
```

## Project Structure

```
edini/
  __init__.py          # Package init, createPanel()
  config.py            # Configuration constants
  panel.py             # PySide6 chat panel
  rpc_client.py        # Pi RPC client (subprocess + JSONL)
  node_utils.py        # Houdini node operations (pure houp)
  tool_executor.py     # HTTP server for tool execution

pi-extensions/
  edini-tools/         # Houdini tool registrations (16 tools)
  edini-context/       # Houdini system prompt injection

scripts/
  install.py           # Houdini package registration
  setup_pi.bat         # Windows Pi setup
```

## License

MIT
