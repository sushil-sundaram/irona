# Graph Report - irona_kicad  (2026-08-15)

## Corpus Check
- 35 files · ~34,751 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 388 nodes · 714 edges · 22 communities (18 shown, 4 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 70 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `407664b0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- PhysicsSolverEngine
- IPCRouterEngine
- Librarian
- schematic_builder.py
- KiCad10IPCClient
- SchematicCircuitBuilder
- graph.py
- AltiumAcademyReviewer
- IronaAgentState
- AltiumReviewAgent
- MasterOrchestratorAgent
- Tooling & EDA Integration Layer
- Irona KiCad 10 AI Co-Pilot ⚡
- main.py
- IronaDesignGraph
- .evaluate_board
- state.py
- .run_drc
- agents/__init__.py
- kicad_scripts/__init__.py
- tools/__init__.py
- irona-kicad

## God Nodes (most connected - your core abstractions)
1. `IPCRouterEngine` - 35 edges
2. `IronaAgentState` - 33 edges
3. `SchematicCircuitBuilder` - 33 edges
4. `AltiumAcademyReviewer` - 24 edges
5. `PhysicsSolverEngine` - 22 edges
6. `DRCEngine` - 21 edges
7. `KiCad10IPCClient` - 18 edges
8. `DocumentationGenerator` - 18 edges
9. `Librarian` - 18 edges
10. `ERCEngine` - 17 edges

## Surprising Connections (you probably didn't know these)
- `librarian_node()` --uses--> `Librarian`  [INFERRED]
  agents/graph.py → tools/librarian.py
- `schematic_node()` --uses--> `SchematicCircuitBuilder`  [INFERRED]
  agents/graph.py → tools/schematic_builder.py
- `erc_validator_node()` --uses--> `ERCEngine`  [INFERRED]
  agents/graph.py → tools/erc_validator.py
- `router_node()` --uses--> `IPCRouterEngine`  [INFERRED]
  agents/graph.py → tools/ipc_router.py
- `drc_validator_node()` --uses--> `DRCEngine`  [INFERRED]
  agents/graph.py → tools/drc_validator.py

## Import Cycles
- None detected.

## Communities (22 total, 4 thin omitted)

### Community 0 - "PhysicsSolverEngine"
Cohesion: 0.06
Nodes (35): handle_tool_call(), process_jsonrpc_message(), Any, Dispatches tool calls to EDA tools and returns formatted JSON result., Processes an incoming JSON-RPC 2.0 MCP message and generates a response., Main event loop for MCP stdio transport., run_stdio_server(), DocumentationGenerator (+27 more)

### Community 1 - "IPCRouterEngine"
Cohesion: 0.07
Nodes (20): KiCad 10 IPC Server & Client Bridge (kicad-python) Provides JSON-RPC socket…, TestDocGenerator, TestDRCValidator, Unit & Integration Tests for KiCad 10 IPC Router & Layout Engine, TestPCBReviewer, Unit & Integration Tests for Physics Solver Tool, TestPhysicsSolver, IPCRouterEngine (+12 more)

### Community 2 - "Librarian"
Cohesion: 0.08
Nodes (24): Unit & Integration Tests for KiCad 10 CAD Librarian Tool, TestLibrarian, Librarian, main(), Any, Path, Librarian Tool for KiCad 10 (Irona EDA) Fetches CAD models (symbols,…, Generate KiCad 10 S-expression for a footprint (.kicad_mod). (+16 more)

### Community 3 - "schematic_builder.py"
Cohesion: 0.09
Nodes (14): generate_uuid(), KiCad10PCBGenerator, KiCad10SchematicGenerator, Any, KiCad 10 S-Expression Parser & Generator Provides utilities to parse,…, Generate a valid KiCad UUID string., Serialize into valid KiCad 10 .kicad_sch S-expression., Helper to build structured S-expressions with indentation. (+6 more)

### Community 4 - "KiCad10IPCClient"
Cohesion: 0.10
Nodes (11): KiCad10IPCClient, MockKiCadIPCServer, Any, Mock KiCad 10 IPC Server for testing and CI/CD environments. Emulates the KiCad…, Start the mock server in a background daemon thread., Client interface connecting to KiCad 10 IPC socket. Exposes methods to inspect…, Attempts to connect to KiCad 10 via Unix socket or TCP., Send JSON-RPC request to KiCad 10 session. (+3 more)

### Community 5 - "SchematicCircuitBuilder"
Cohesion: 0.09
Nodes (13): TestERCValidator, TestSchematicBuilder, main(), Any, Path, Injects visual wires and net labels for standard power nodes., Writes the .kicad_sch file., Exports a JSON and IPC-compatible netlist dictionary. (+5 more)

### Community 6 - "graph.py"
Cohesion: 0.13
Nodes (20): ci_doc_node(), drc_validator_node(), erc_validator_node(), librarian_node(), physics_routing_condition(), physics_validator_node(), LangGraph Multi-Agent State Graph for Irona KiCad 10 Orchestrates the end-to-…, Executes PCB layout and track routing using IPCRouterEngine. (+12 more)

### Community 7 - "AltiumAcademyReviewer"
Cohesion: 0.19
Nodes (10): AltiumAcademyReviewer, Any, Evaluates Rick Hartley's primary rule: 'Every signal trace must have an…, Evaluates IPC-2221 Generic Standard for Printed Board Design: - Table 6-1…, Evaluates IPC-2222 Sectional Standard for Rigid Printed Boards: - Aspect Ratio:…, Evaluates IPC-2223 rules for flexible/rigid transitions and teardrop…, Evaluates IPC-6012 (Rigid Board Qualification) and IPC-A-600 (Acceptability): -…, Runs all review modules and compiles a quantitative scorecard and executive… (+2 more)

### Community 8 - "IronaAgentState"
Cohesion: 0.18
Nodes (10): Spatial reasoning and coordinate floorplanning., spatial_node(), Spatial & Layout Agent for Irona KiCad 10 Powered by local Ollama model (with…, Agent responsible for spatial floorplanning, placement coordinates, and trace…, Queries local Ollama instance if active., Synthesizes component placement coordinates and track widths based on…, SpatialLayoutAgent, IronaAgentState (+2 more)

### Community 9 - "AltiumReviewAgent"
Cohesion: 0.23
Nodes (5): AltiumReviewAgent, agents/review_agent.py ====================== Altium Academy & IPC Standards…, Expert PCB design review agent synthesizing Altium Academy best practices and…, Performs comprehensive review of the PCB layout, schematic, and physics…, TestReviewAgent

### Community 10 - "MasterOrchestratorAgent"
Cohesion: 0.22
Nodes (7): orchestrator_node(), Master Orchestrator decomposes spec and plans BOM., MasterOrchestratorAgent, Any, Generates standard tested BOM for synchronous buck converter., Master reasoning agent orchestrating hardware design decisions., Extracts electrical requirements and formulates the initial BOM from the spec…

### Community 11 - "Tooling & EDA Integration Layer"
Cohesion: 0.18
Nodes (10): 1. Librarian Tool (`tools/librarian.py`), 2. Schematic Builder (`tools/schematic_builder.py`), 3. KiCad 10 IPC Router (`tools/ipc_router.py`), 4. Physics Validator (`tools/physics_solver.py`), 5. CI/CD & Documentation (`.github/workflows/ci.yml` & `config/kibot.yaml`), Core Agents, Directory Structure, Irona KiCad 10 Multi-Agent AI Co-Pilot (+2 more)

### Community 12 - "Irona KiCad 10 AI Co-Pilot ⚡"
Cohesion: 0.18
Nodes (10): 1. Installation, 2. Run Autonomous Design Co-Pilot, 3. Run Headless Multiphysics Verification, 4. Run Test Suite, 🏗️ Architecture & Multi-Agent Engine, 📦 CI/CD & Automated KiBot Pipeline, Core Agents, Irona KiCad 10 AI Co-Pilot ⚡ (+2 more)

### Community 13 - "main.py"
Cohesion: 0.29
Nodes (9): display_results_summary(), main(), print_banner(), Any, Path, Irona KiCad 10 Multi-Agent AI Co-Pilot CLI Main entry point for autonomous end-…, Runs the complete multi-agent pipeline., Displays structured summary of generated hardware project. (+1 more)

### Community 14 - "IronaDesignGraph"
Cohesion: 0.28
Nodes (4): IronaDesignGraph, Manages the execution flow of the multi-agent system., Unit & Integration Tests for LangGraph Multi-Agent Engine, TestMultiAgentGraph

### Community 15 - ".evaluate_board"
Cohesion: 0.31
Nodes (5): Any, Calculates DC IR drop and Current Density across power nets. R = rho * L / (W *…, Solves 2D Steady-State Heat Conduction Equation with Natural Convection on PCB:…, Calculates characteristic impedance Z0 for microstrip traces on F.Cu over FR-4.…, Runs full physics evaluation suite, verifies thresholds, and compiles layout…

### Community 16 - "state.py"
Cohesion: 0.43
Nodes (5): Master Orchestrator Agent for Irona KiCad 10 Powered by Google Gemini (with…, ComponentSpec, HardwareRequirements, Multi-Agent State Schema for Irona KiCad 10 Defines the shared LangGraph state…, BaseModel

### Community 17 - ".run_drc"
Cohesion: 0.33
Nodes (6): point_to_segment_dist(), Any, Executes full DRC rules suite and returns detailed violations report., Calculates minimum Euclidean distance from a point (px, py) to line segment…, Calculates minimum Euclidean distance between two line segments., segment_to_segment_dist()

## Knowledge Gaps
- **15 isolated node(s):** `irona-kicad`, `Core Agents`, `1. Librarian Tool (`tools/librarian.py`)`, `2. Schematic Builder (`tools/schematic_builder.py`)`, `3. KiCad 10 IPC Router (`tools/ipc_router.py`)` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `IPCRouterEngine` connect `IPCRouterEngine` to `PhysicsSolverEngine`, `schematic_builder.py`, `KiCad10IPCClient`, `SchematicCircuitBuilder`, `graph.py`, `AltiumReviewAgent`?**
  _High betweenness centrality (0.207) - this node is a cross-community bridge._
- **Why does `SchematicCircuitBuilder` connect `SchematicCircuitBuilder` to `PhysicsSolverEngine`, `IPCRouterEngine`, `schematic_builder.py`, `graph.py`, `AltiumReviewAgent`?**
  _High betweenness centrality (0.141) - this node is a cross-community bridge._
- **Why does `Librarian` connect `Librarian` to `PhysicsSolverEngine`, `graph.py`?**
  _High betweenness centrality (0.134) - this node is a cross-community bridge._
- **Are the 10 inferred relationships involving `IPCRouterEngine` (e.g. with `router_node()` and `handle_tool_call()`) actually correct?**
  _`IPCRouterEngine` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `IronaAgentState` (e.g. with `ci_doc_node()` and `drc_validator_node()`) actually correct?**
  _`IronaAgentState` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `SchematicCircuitBuilder` (e.g. with `schematic_node()` and `handle_tool_call()`) actually correct?**
  _`SchematicCircuitBuilder` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `AltiumAcademyReviewer` (e.g. with `AltiumReviewAgent` and `handle_tool_call()`) actually correct?**
  _`AltiumAcademyReviewer` has 6 INFERRED edges - model-reasoned connections that need verification._