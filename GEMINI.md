# Irona KiCad 10 Multi-Agent AI Co-Pilot

## System Architecture

Irona KiCad is an autonomous end-to-end multi-agent hardware design system built for KiCad 10. It converts natural language hardware requirements into fully placed, routed, physics-validated, and manufacturing-ready PCBs with automated CI/CD documentation.

### Core Agents

1. **Master Orchestrator (`agents/orchestrator.py`)**
   - Powered by: **Google Gemini** (`gemini-2.5-pro` / `gemini-2.5-flash`)
   - Role: High-level architectural reasoning, requirement extraction, BOM formulation, tool dispatching, verification review, and iterative design refinement.
2. **Spatial & Routing Agent (`agents/spatial_agent.py`)**
   - Powered by: **Local Ollama Model** (e.g. `llama3.2-vision`, `deepseek-r1`, `mistral`)
   - Role: Geometric floorplanning, component spacing, thermal dissipation zones, coordinate budgeting, Manhattan/A* routing path guidance, and collision resolution.
3. **Multi-Agent State Graph (`agents/graph.py` & `agents/state.py`)**
   - Built on: **LangGraph / LangChain**
   - State flow: `User Spec` -> `Orchestrator` -> `Librarian` -> `SchematicBuilder` -> `SpatialAgent` -> `IPCRouter` -> `PhysicsValidator` -> (Conditional Loop / `KiBot CI/CD`).

---

## Tooling & EDA Integration Layer

### 1. Librarian Tool (`tools/librarian.py`)
- Interface with Octopart (Nexar API) & SnapMagic REST APIs.
- Downloads symbol (`.kicad_sym`), footprint (`.kicad_mod`), and 3D STEP files.
- Automatically maintains and registers entries in project-level `sym-lib-table` and `fp-lib-table`.
- Provides offline synthetic CAD generator fallback for standard SMD/THT passives and packages (SOIC, QFN, SOT, 0805, 0603, etc.).

### 2. Schematic Builder (`tools/schematic_builder.py`)
- Generates native KiCad 10 S-expression schematics (`.kicad_sch`).
- Handles symbol instantiation, unique UUIDs, pin-to-wire connections, power/ground symbols, hierarchical sheets, and netlist extraction.

### 3. KiCad 10 IPC Router (`tools/ipc_router.py`)
- Interfaces with live KiCad 10 PCB Editor sessions via Python IPC Socket API (`kicad-python`) and offline S-expression board generators (`kicad_scripts/sexpr_generator.py`).
- Sets stackup (2/4/6 layers), places footprints at $(X, Y, \text{angle})$, routes track segments with width and net tags, inserts vias, and pours copper zones.
- Triggers DRC validation and extracts violation reports.

### 4. Physics Validator (`tools/physics_solver.py`)
- Headless simulation engine wrapping **Ki-PIDA** (Power Integrity - DC IR drop & current density) and **Elmer FEM** (Thermal & Signal Integrity impedance).
- Exports board geometry into mesh format, solves partial differential equations, and parses numerical outputs into structured JSON metrics (voltage drop, $A/\text{mm}^2$, hotspot temperatures).
- Evaluates against configurable safety thresholds and generates actionable feedback for the spatial agent.

### 5. CI/CD & Documentation (`.github/workflows/ci.yml` & `config/kibot.yaml`)
- Implements the **Vincent Nguyen KiBot** automated documentation standard.
- Containerized execution via KiCad Docker (`ghcr.io/inti-cmnb/kicad_auto_test:dev` / `setsoft/kicad_auto`).
- Pipeline:
  1. Automated Physics Validation Gate (`tools/physics_solver.py --check`)
  2. If passed: Run KiBot to generate:
     - Interactive HTML BoM (iBoM)
     - Schematic PDF with custom title block
     - Fabrication Gerbers (RS-274X) & NC Drill files
     - Pick-and-Place (XYRS) CSV and Assembly Drawings
     - 3D STEP export and photorealistic raytraced 2D renders

---

## Directory Structure

```
irona_kicad/
├── .github/
│   └── workflows/
│       └── ci.yml               # KiBot CI/CD pipeline + automated physics verification
├── config/
│   ├── kibot.yaml               # KiBot config for HTML BOM, Gerbers, PDFs, Interactive BOM
│   └── settings.yaml            # LLM endpoints (Gemini API, Ollama host), tool configs
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py          # Gemini-powered master orchestrator
│   ├── spatial_agent.py         # Ollama-powered placement/routing spatial reasoning agent
│   ├── state.py                 # LangGraph AgentState definition
│   └── graph.py                 # Multi-agent state graph & conditional routing logic
├── tools/
│   ├── __init__.py
│   ├── librarian.py             # Octopart/SnapMagic CAD fetcher & lib-table updater
│   ├── schematic_builder.py     # kicad-sch-api / S-Expression KiCad 10 schematic generator
│   ├── ipc_router.py            # KiCad 10 IPC API live PCB placement & router interface
│   ├── physics_solver.py        # Ki-PIDA & Elmer FEM headless physics wrapper & JSON parser
│   └── drc_validator.py         # KiCad DRC CLI runner and violation parser
├── kicad_scripts/
│   ├── __init__.py
│   ├── ipc_server_bridge.py     # KiCad 10 IPC bridge script for live PCB editor sessions
│   └── sexpr_generator.py       # S-expression parser/generator for KiCad 10 files
├── templates/
│   ├── sym_lib_table.template   # Template for sym-lib-table
│   ├── fp_lib_table.template    # Template for fp-lib-table
│   └── default_board.kicad_pcb  # Base KiCad 10 PCB stackup template
├── tests/
│   ├── test_librarian.py
│   ├── test_schematic.py
│   ├── test_ipc_router.py
│   ├── test_physics_solver.py
│   └── test_agents_graph.py
├── GEMINI.md                    # System context & architecture documentation
├── pyproject.toml / requirements.txt
├── main.py                      # CLI entrypoint to trigger end-to-end design run
└── README.md
```
