# BuildScaffold — Design Specification (MVP)

## Vision

An IDE for designing physical objects from constrained piece libraries. The user describes what they want in natural language, an AI agent composes a design from predefined pieces, and the system produces an interactive 3D preview and step-by-step assembly instructions. The architecture is model-agnostic — any LLM can serve as the design agent, and the scaffolding (validator, renderer, instruction generator) is the permanent product.

## Target Product (Post-MVP)

The end goal is designing real wooden furniture and structures from standard hardware-store materials (K-Rauta and similar). Key characteristics:

- **Pieces**: Standard lumber (45×45, 45×95, 95×95 posts; planks of various widths/thicknesses), brackets, screws, hinges, handles, pipes, shelf pins, casters, rubber feet
- **Joints**: Right-angle only (no mitre cuts). Screwed connections — either self-drilling screws into softwood face grain, or pilot hole + screw for edge/end grain and near-edge connections. Metal brackets and joist hangers for structural joins
- **Soft elements**: Cushions and fabric held in place mechanically — inset areas, rails, slots — not upholstered or glued. Similar to how Ikea bed frames hold mattresses by inset geometry
- **Finishing**: Paint, stain, varnish, wood oil. Instructions generated per-surface, including sanding, priming, drying times. Formulaic and repetitive — suitable for small LLM generation
- **Sourcing**: All pieces available at standard hardware stores. Output includes a shopping list with product dimensions and quantities. No custom manufacturing required
- **Assembly difficulty ceiling**: A person with a drill, drill bits, sandpaper, and a paintbrush can complete the project. No table saw, no router, no specialized tools

## MVP Scope

The MVP uses **Lego bricks** as the piece library. This validates the core architecture with a well-defined, pre-existing piece catalog (LDraw) where connection rules are simple and structural concerns are minimal. The full wood version swaps the piece library and adds finishing/structural rules on top of the same scaffolding.

### MVP delivers:

1. A working AI design loop (describe → compose → render → evaluate → iterate)
2. A validated JSON design schema
3. A piece library format that generalizes beyond Lego
4. An interactive 3D viewer
5. Step-by-step assembly instructions with rendered images per step

### MVP does not include:

- Wood pieces, finishing instructions, or structural validation
- Shopping list generation
- User accounts, persistence, or sharing
- Mobile support

## Prior Art — BrickGPT

BrickGPT (github.com/AvaLovelace1/BrickGPT, MIT license) is a CMU research project that generates physically stable brick structures from text prompts. It fine-tunes Llama-3.2-1B to predict bricks one at a time as text tokens, validates placement via rejection sampling and connectivity/physics analysis, and renders results with Blender. It won the ICCV 2025 Best Paper (Marr Prize).

**Why we don't fork it:** The architectures are incompatible. BrickGPT is a fine-tuned single-model pipeline (next-brick-prediction with constrained decoding). BuildScaffold is a model-agnostic scaffolding system where any LLM reads and writes complete design JSON, validated by external tools. BrickGPT has no interactive editor, no chat-based iteration loop, no assembly instructions, and no interactive 3D viewport. The interaction loop, mainly, is important.

**What we reference:**
- `brick_library.json` — LDraw part ID mappings for the MVP piece library
- `connectivity_analysis.py` — approach to stability validation via graph reachability
- LDraw coordinate conventions (x,z × 20 LDU; y × -24 LDU) for part geometry import
- Incremental validation pattern — BrickGPT validates each brick as it's placed rather than checking the entire structure at once. BuildScaffold adopts this: the AI builds layer by layer (a few bricks at a time), and the validator runs after each addition. This catches errors early and gives the LLM localized feedback instead of a wall of errors from a full design

## Architecture

### Three-Layer Architecture

The system is split into three layers so that the core logic is reusable across interfaces:

- **Core** (Python package): Piece library, validator, instruction generator, AI agent loop, offscreen renderer. Standalone — no UI dependency, fully testable from a script or test suite
- **CLI** (terminal interface): Interactive chat consuming core. Text-based validation reports, rendered images opened in system viewer or saved to disk, LDraw file export. Analogous to Claude Code's terminal mode
- **Web** (browser GUI): Thin API server exposing core over HTTP/WebSocket, plus React + Three.js frontend for the interactive IDE experience

### Technology Stack

- **Core**: Python. Trimesh + pyrender for offscreen rendering. JSON schema validation
- **CLI**: Python. Rich (or similar) for formatted terminal output. System image viewer integration
- **Web frontend**: React + Three.js (React Three Fiber). Split-panel layout with standard React components
- **Web backend**: Python API server (FastAPI or similar) — thin wrapper over core
- **LLM**: Any capable model via API. No fine-tuning required for MVP
- **Design format**: JSON

### Application Layout (IDE Model)

Split-panel web application, modeled after VS Code with Claude Code:

| Panel | Content |
|---|---|
| **Left** | Project files, piece library browser, current parts list with quantities and colors |
| **Center** | Interactive 3D viewport — user rotates, zooms, inspects the design. Click-to-select pieces. Build instruction step-through mode |
| **Right** | Chat panel — user describes intent, AI proposes and modifies designs, shows reasoning |

### CLI Interface

The terminal interface provides the full design workflow without a browser:

- **Interactive chat**: User describes intent, AI generates and iterates on designs. Progress and reasoning displayed as formatted text
- **Validation output**: Errors and warnings printed with piece IDs and descriptions. Color-coded severity (errors red, warnings yellow)
- **Rendered previews**: Multi-angle PNGs generated via offscreen renderer, saved to project directory. Optionally opened in the system image viewer automatically
- **LDraw export**: Designs exported as `.ldr` files, viewable in any LDraw-compatible tool (LDView, Studio 2.0)
- **Instruction step-through**: Assembly steps printed sequentially with rendered images per step. Text-based navigation (next/previous/jump to step)
- **Project files**: Design JSON, rendered images, and LDraw exports stored in a project directory on disk

### Core Components

#### 1. Piece Library

A declarative catalog of available pieces. Each piece defines:

```
{
  "id": "brick_2x4",
  "name": "Brick 2×4",
  "category": "brick",
  "geometry": { reference to LDraw part or parametric definition },
  "dimensions": { "studs_x": 4, "studs_y": 2, "height_plates": 3 },
  "connection_points": [
    { "type": "stud", "position": [0,0,1], "direction": "up" },
    { "type": "anti_stud", "position": [0,0,0], "direction": "down" }
  ],
  "colors": ["red", "blue", "white", ...],
  "ldraw_id": "3001.dat"
}
```

For MVP, import directly from LDraw's parts library. For wood version later, same format but with structural properties added (`max_load`, `grain_direction`, `weather_resistance`, `required_finishing`).

#### 2. Design Schema

The design document is JSON. It is the single source of truth — the equivalent of source code.

```
{
  "meta": {
    "name": "Small bench",
    "description": "User's description",
    "piece_library": "lego_basic",
    "version": 1
  },
  "pieces": [
    {
      "id": "piece_001",
      "type": "brick_2x4",
      "color": "red",
      "position": [0, 0, 0],
      "rotation": [0, 0, 0],
      "connections": [
        { "from_point": "stud_0", "to_piece": "piece_002", "to_point": "anti_stud_3" }
      ]
    }
  ],
  "groups": [
    {
      "id": "subassembly_leg_1",
      "name": "Front left leg",
      "pieces": ["piece_001", "piece_002", "piece_003"]
    }
  ]
}
```

Key properties:
- **Position** is absolute in world coordinates (grid-snapped for Lego, millimeter for wood)
- **Connections** are explicit — the validator checks these, not inferred from proximity
- **Groups** define subassemblies for the instruction generator
- The LLM reads and writes this format directly

#### 3. Validator (Compiler 1)

Reads the design JSON and produces a validation report:

- **Connection validity**: All declared connections match compatible connection point types. A stud can only connect to an anti-stud. Connection point positions must align within tolerance after applying piece positions and rotations
- **Collision detection**: No pieces occupy the same space. Implemented as a 3D occupancy grid — each piece's bounding volume is rasterized into the grid, and overlaps are flagged. For Lego, the grid resolution matches the stud pitch
- **Screw collision detection** (wood): Screws entering a post from opposite faces must not overlap inside the piece. A screw occupies depth on both sides of a connection — through the entry piece and into the receiving piece. For a 45mm post receiving screws from +x and -x, two 20mm screws would collide (20+20=40 > 45 clear depth is insufficient). This check only applies to posts (pieces with screw_receiver faces) — planks are thin pass-through pieces (screw_entry only) that cannot receive screws from the opposite side, so internal screw collision cannot occur for them. Two planks also cannot be attached directly (screw_entry is not compatible with screw_entry)
- **Gravity/stability**: Delegated to a pluggable stability checker (separate module, swappable per piece library). For Lego MVP: graph reachability — build a graph where nodes are pieces and edges are connections, mark ground-touching pieces as stable, BFS/DFS to propagate. Any piece not reached is flagged as unsupported (adapted from BrickGPT's connectivity analysis). For the wood version later: a different checker implementing force/torque equilibrium calculations for structural load validation. The stability interface takes a design and returns a list of unsupported piece IDs — the validator doesn't know or care how stability is determined
- **Screw penetration depth and joint strength** (wood stability): Screw penetration depth into the receiving piece directly affects how much load a joint can bear. A screw that barely enters the receiver holds less weight and resists less lateral force than one with deep engagement. The wood stability checker must account for this: given the screw length (from the fastener spec on the connection), entry piece thickness, and receiver piece dimension along the screw axis, compute effective penetration depth. Rule of thumb: at least 25mm into softwood for a load-bearing joint. Joints with insufficient penetration should be flagged as stability warnings. This also interacts with screw collision detection — screws from opposite faces compete for the same internal depth, reducing effective penetration for both
- **Completeness**: No floating pieces, no disconnected subgraphs (unless explicitly grouped as separate objects). The connection graph must be fully connected (single connected component, or one component per declared separate object)

Output: list of errors and warnings, referenced by piece ID. Errors (collisions, unsupported pieces) must be fixed. Warnings (marginal stability, unusual proportions) are advisory. The AI receives this and fixes violations.

#### 4. Renderer (Compiler 2)

Reads the design JSON and produces visual output. Two rendering paths serve different needs:

**Offscreen renderer (core — Trimesh + pyrender):**
- Loads piece geometry from library, places per design coordinates
- Produces PNG images from fixed camera angles (front, back, left, right, top, isometric)
- Used by the AI agent loop (visual feedback alongside validation report) and the CLI (user previews)
- Lightweight — no browser, no GPU required (software rasterizer fallback)
- The LLM needs clear structural views, not photorealistic ones. Trimesh is sufficient

**Interactive renderer (web — Three.js via React Three Fiber):**
- Full 3D scene with orbit controls, zoom, piece selection
- Real-time updates as the design changes
- Instruction step-through mode: previously placed pieces muted, newly placed pieces highlighted, step controls overlaid
- Same piece geometry files as the offscreen renderer — single source of truth for part shapes

**AI screenshots** are always produced by the offscreen renderer (even in the web GUI), ensuring consistent visual input to the LLM regardless of the user's viewport angle.

**Instruction step renders** produced by the offscreen renderer given a build sequence from the instruction generator. Each step shows new pieces highlighted and previous pieces muted, from a camera angle chosen to best show the new pieces.

#### 5. Instruction Generator (Compiler 3)

Reads the design JSON and produces an ordered assembly sequence optimized for human builders:

**Decomposition rules:**
- Bottom-up ordering (lowest pieces first)
- Subassemblies built separately, then attached to main body
- Each step adds 1–3 pieces (configurable)
- At every intermediate step, the partial build is stable (no floating pieces)
- Pieces that would block hand access to later placement sites are placed after the pieces they would block

**Output per step:**
```
{
  "step_number": 1,
  "pieces_added": ["piece_001", "piece_002"],
  "instruction_text": "Place two 2×4 red bricks side by side on the baseplate.",
  "camera_angle": "isometric_front_left",
  "highlight_pieces": ["piece_001", "piece_002"],
  "muted_pieces": []
}
```

**Instruction text** is generated by the LLM given the step context. For Lego this is trivial ("place brick X at position Y"). For wood version later, this expands to include pilot hole specs, screw selection, finishing order, and drying times.

The instruction view is a separate mode in the center viewport — same 3D scene but with step-by-step controls (previous/next), piece highlighting, and the instruction text overlaid.

#### 6. AI Design Agent

The LLM operates in a loop:

```
1. User describes intent ("a small shelf with two levels")
2. LLM generates a partial design — a few bricks at a time (layer by layer)
3. Validator runs on the partial design → errors fed back to LLM immediately
4. LLM fixes any errors, adds more bricks → go to step 3
5. Once the full design is complete, renderer runs → multi-angle screenshots fed back to LLM
6. LLM evaluates: structural issues? aesthetically wrong? doesn't match description?
7. LLM modifies JSON (still incrementally), go to step 3
8. After N iterations or convergence, present to user
9. User gives feedback in chat → go to step 2 with modifications
```

Building incrementally (a few bricks at a time, validated after each addition) catches errors early and gives the LLM localized, actionable feedback rather than a wall of errors from a full design attempt.

The LLM receives as context:
- Piece library documentation (available pieces, dimensions, connection rules)
- Current design JSON
- Validation report
- Multi-angle screenshots
- User's original description and any feedback
- System prompt defining the scaffolding constraints

No fine-tuning required. The scaffolding constrains the output space enough that a general model with good instructions can produce valid designs. As models improve, designs improve — the scaffolding captures permanent value.

## Design Decisions

**Why JSON, not a visual editor?** The AI needs to read and write the design. Text is the natural interface for LLMs. The 3D viewport is for the human; the JSON is for the AI. Same as code — humans read the rendered output, the compiler reads the source.

**Why explicit connections, not proximity?** Inferring connections from piece overlap is ambiguous and fragile. Explicit connections make validation deterministic and give the instruction generator clear dependency information for ordering steps.

**Why subassemblies?** Real build instructions group related pieces. "Build the leg, then attach it" is clearer than interleaving leg and seat pieces. The LLM defines groups; the instruction generator respects them.

**Why right angles only (wood version)?** Angled cuts require a mitre saw and precise measurement — beyond the target user's tools and skills. All joints are 90°. If the product succeeds, angled bracket pieces can be added to the piece library later — the user still doesn't cut angles, they buy pre-angled brackets.

**Why mechanical cushion retention?** Upholstery requires specialized tools and skills (staple guns, foam cutting, fabric stretching). Inset geometry that holds cushions by gravity and friction requires zero additional skills. The design simply includes a recessed area sized to the cushion dimensions. Same principle as Ikea bed frames holding mattresses.

## File Structure (MVP)

```
buildscaffold/
├── core/                          # Python package — all business logic
│   ├── validator.py               # Design validation (connections, collisions, delegates stability)
│   ├── stability/                 # Pluggable stability checkers
│   │   ├── base.py                # Interface: design → list of unsupported piece IDs
│   │   ├── lego.py                # Lego: graph reachability (BFS/DFS from ground)
│   │   └── wood.py                # Wood (post-MVP): force/torque equilibrium
│   ├── instructor.py              # Build sequence generation
│   ├── agent.py                   # LLM design loop (model-agnostic)
│   ├── renderer.py                # Offscreen rendering (Trimesh + pyrender)
│   ├── library.py                 # Piece library loading
│   └── schema/
│       ├── design.schema.json     # JSON schema for designs
│       └── library.schema.json    # JSON schema for piece libraries
├── cli/                           # Terminal interface
│   ├── main.py                    # Entry point
│   ├── chat.py                    # Interactive chat loop
│   └── display.py                 # Rich text output, image viewer integration
├── web/
│   ├── backend/
│   │   ├── api.py                 # REST/WebSocket endpoints (thin wrapper over core)
│   │   └── session.py             # Design session management
│   └── frontend/
│       └── src/
│           ├── panels/
│           │   ├── LibraryPanel.jsx    # Left: piece browser, parts list
│           │   ├── ViewportPanel.jsx   # Center: Three.js 3D viewer
│           │   └── ChatPanel.jsx       # Right: AI chat interface
│           ├── viewport/
│           │   ├── Scene.jsx           # React Three Fiber scene
│           │   ├── PieceRenderer.jsx   # Geometry loading + placement
│           │   ├── InstructionMode.jsx # Step-through view
│           │   └── OffscreenRenderer.js # Not used — core/renderer.py handles AI screenshots
│           └── App.jsx
├── libraries/
│   ├── lego_basic/                # MVP piece library
│   │   ├── library.json           # Piece catalog
│   │   └── parts/                 # LDraw geometry files
│   └── wood_basic/                # Post-MVP
│       ├── library.json
│       └── parts/
```

## Development Sequence

### Phase 1 — Core (no UI required)

1. **Design schema + validator**: Define JSON schema, build validator with connection, collision, and stability checks. Test with hand-written designs
2. **Piece library loader**: Import LDraw basic bricks subset (2×2, 2×4, 1×1, 1×2, plates, baseplates — ~20 piece types). Reference BrickGPT's brick_library.json for LDraw part IDs
3. **Offscreen renderer**: Trimesh + pyrender. Load LDraw geometry, render multi-angle PNGs from a design JSON

### Phase 2 — CLI (functional product without web development)

4. **Basic CLI chat**: Interactive terminal loop — user describes intent, system renders and validates. Text output with Rich formatting
5. **AI agent loop**: Connect LLM, feed it piece library docs + schema + validation report + rendered screenshots. Iterate until convergence
6. **Full CLI integration**: Chat with AI, view rendered images, export LDraw files, step through assembly instructions as text

Steps 1–6 deliver a fully functional product. A user can describe a design in the terminal, the AI generates it, and they get validated designs with rendered images and assembly instructions — all without a browser.

### Phase 3 — Web GUI (interactive IDE)

7. **3D viewport**: React Three Fiber scene that renders a design JSON. Orbit controls, piece selection
8. **API server**: Thin FastAPI wrapper over core — design CRUD, agent session management, WebSocket for streaming
9. **IDE layout**: Wire together panels (library browser, 3D viewport, chat). Instruction step-through mode in viewport
