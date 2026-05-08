# Joshua Yap — MCP Server Integration & Pipeline Orchestration

**BIOE 234 Final Project · Spring 2026**

## Role

Joshua built the **integration layer** — the FastMCP server, the Gemini client, the full-pipeline orchestrator tool, and the Streamlit web application that ties all four components together into a single end-to-end system.

---

## How it fits into the pipeline

```
User (browser) → app.py (Streamlit)
                      ↓
              Gemini 2.5 Flash
              (function calling)
                      ↓
            run_ot2_pipeline tool
                      ↓
        ┌─────────────┼──────────────┐
        ↓             ↓              ↓
  generator.py  simulation_engine  analyzer.py
   (Taylor)       (Adriann)         (Alex)
        └─────────────┼──────────────┘
                      ↓
               visualizer/
               (Christian)
                      ↓
         ~/Downloads/OT2_outputs/
```

Joshua's layer is what makes the project usable as a product — without it, the four components would be independent scripts with no user interface.

---

## Files

| File | Description |
|------|-------------|
| `app.py` | Streamlit web application — the primary user interface |
| `server.py` | FastMCP server — exposes all tools as MCP endpoints |
| `client_gemini.py` | Terminal-mode Gemini client — alternative headless interface |
| `run_full_pipeline.py` | MCP tool that chains generate → simulate → analyze → visualize |
| `run_full_pipeline.json` | C9 JSON schema for the full pipeline tool |
| `setup.bat` | Windows one-click setup script |
| `launch.bat` | Windows one-click launch script |

---

## What was built

### Streamlit web application (`app.py`)

The primary user interface — a chat-based web app where researchers describe protocols in plain English and receive generated scripts, simulations, and visualizations.

Key features:
- **Onboarding screen**: collects user name, lab/course, and session name before the first run
- **Gemini function calling**: the chat input is routed through Gemini 2.5 Flash with a `run_ot2_pipeline` tool declaration; Gemini decides when to invoke the pipeline and with what parameters
- **Custom protocol support**: a `task_type: "custom"` path routes to `generate_freeform_script`, enabling arbitrary protocols beyond the three templates
- **Self-correction loop**: if freeform generation produces a script that fails simulation, the error is fed back to Gemini for one automated retry
- **Download buttons**: PDF, HTML dashboard, stats PNG, and GIF are all available as one-click downloads after each run
- **Optimization recommendations**: heuristic findings are displayed with severity icons (🔴 high, 🟡 medium, 🟢 low)
- **New session button**: clears conversation history so each protocol run starts with a clean context
- **Millisecond run IDs**: prevents duplicate widget key errors when running multiple protocols in the same session

### FastMCP server (`server.py`)

Exposes all five tools as MCP endpoints using the BioE234 MCP Starter framework:
- `generate_protocol` (Taylor)
- `simulate_protocol` (Adriann)
- `analyze_protocol` (Alex)
- `visualize_deck_state` (Christian)
- `run_full_pipeline` (Josh — chains all four)

The framework auto-discovers tools by scanning `modules/<name>/tools/` for `.py` + `.json` file pairs.

### Full pipeline tool (`run_full_pipeline.py`)

The `run_full_pipeline` MCP tool chains all four stages in sequence, passing outputs between them:
1. Calls `generate_ot2_script` (or `generate_freeform_script` for custom)
2. Passes the script to `run_opentrons_simulation`
3. Passes the log to `analyze_optimization`
4. Passes the log and protocol object to all four visualizer outputs

### Terminal client (`client_gemini.py`)

A headless alternative to the Streamlit app for power users and testing. Connects to the FastMCP server via the MCP protocol, routes user input through Gemini, and prints results to the terminal.

### Setup automation (`setup.bat`, `launch.bat`)

- `setup.bat`: creates `.venv` and `venv_ot`, installs all dependencies, writes `OT_VENV_PYTHON` to `.env`
- `launch.bat`: activates `.venv` and starts Streamlit in one double-click

---

## Example outputs

Two complete end-to-end pipeline runs are included in `examples/` — each folder contains all five output artefacts produced by a single run.

### Serial dilution (`examples/serial_dilution/`)

Prompt: *"Run a serial dilution with 8 dilutions, dilution factor 2, and 180 µL initial volume using a p300 single channel on slot 1."*

| File | Description |
|------|-------------|
| `simulation_log.txt` | Raw `opentrons_simulate` output (~32 pipetting actions) |
| `stats_dashboard.png` | 4-panel statistics figure |
| `deck_animation.gif` | Frame-by-frame deck animation |
| `report.pdf` | Multi-page PDF report |
| `dashboard.html` | Interactive Plotly dashboard |

### Reagent addition (`examples/reagent_addition/`)

Prompt: *"Add 50 µL of reagent from a 195 mL reservoir on slot 4 to all wells in column 1 through 6 of a 96-well plate on slot 2. Use a p300 single-channel pipette with tip rack on slot 1."*

Same five output files, demonstrating the pipeline on a freeform (non-template) protocol with 192 pipetting actions.

---

## Key technical decisions

- **Streamlit over terminal**: The web UI makes the project accessible to researchers who aren't comfortable with command-line tools, which is the target audience for lab automation software.
- **Gemini function calling over manual parsing**: Having Gemini decide when to call the pipeline (rather than always calling it) allows the chat to handle follow-up questions, clarifications, and multi-turn conversations naturally.
- **Two-venv architecture**: The Opentrons package conflicts with FastMCP's pydantic/anyio versions. Running `opentrons_simulate` as a subprocess from a separate venv (`venv_ot`) resolves this without forking the codebase.
- **`@st.cache_resource` for pipeline modules**: Importing the pipeline modules once and caching them avoids re-importing on every Streamlit rerun, which would be expensive given the size of the Opentrons ecosystem.
