# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ECEN723 Spring 2026 Team 14 — a traffic simulation system modeling vehicle routing and signal coordination on a 3×3 grid of intersections. The system is split into two independent software groups:

- **V-Group** (Vehicle Management): spawning, pathfinding, movement, collision avoidance
- **I-Group** (Infrastructure Management): traffic signal control, intersection conflict detection

## Running the Code

```bash
# Text-based simulation (1800 steps / 1 hour, no vehicle cap)
python3 simulation.py

# Animated visualization (requires matplotlib)
python3 visualization.py

# V-Group independent test suite (interactive menu, options 1–7)
python3 -m v_group.v_group_test

# Run a specific test scenario with a chosen signal strategy
python3 -c "from v_group.v_group_test import VGroupTestSuite; VGroupTestSuite(signal_strategy='adversarial').run_test(num_steps=300)"

# Run stress test non-interactively (all signal strategies, 1800 steps each)
python3 -c "from v_group.v_group_test import VGroupStressTest; VGroupStressTest().run_all_strategies()"

# V-Group debug utilities (vehicle tracing, deadlock detection)
python3 -m v_group.v_group_debug

# I-Group independent test suite (interactive menu, options 1–8)
python3 -m i_group.i_group_test

# I-Group animated visualization (normal + violation modes)
python3 -m i_group.i_group_viz
```

No external dependencies are required for the core simulation. `matplotlib` is required only for `visualization.py`, `v_group/v_group_viz.py`, and `i_group/i_group_viz.py`.

## Architecture

### Module Responsibilities

| File | Role |
|------|------|
| `common.py` | Shared data structures: `Direction`, `SignalState`, `Position`, `Vehicle`, `RoadNetwork`, `VehicleState`, `InfrastructureState` |
| `v_group/v_group.py` | `PathPlanner` (greedy nearest-checkpoint helper, largely vestigial — Strategy E routing uses `_checkpoint_plans` + per-intersection Manhattan distance instead) + `VehicleManager` (movement, collision detection, signal compliance, congestion-aware routing) |
| `i_group/i_group.py` | `TrafficSignalController` (demand-based GREEN allocation) + `InfrastructureManager` (entry point for V-Group) |
| `simulation.py` | `Simulation` class — coordinates the V↔I interaction loop |
| `visualization.py` | `Visualizer` — matplotlib animation of the simulation |
| `v_group/v_group_test.py` | Independent V-Group test suite with `MockInfrastructure`, `ConstraintVerifier`, stress tests, and scenario tests |
| `v_group/v_group_debug.py` | `VGroupDebugger` — step-by-step vehicle tracing and deadlock detection |
| `v_group/v_group_viz.py` | `VGroupTestVisualizer`, `VGroupTraceVisualizer`, `VGroupInspectVisualizer`, `VGroupDeadlockVisualizer` |
| `i_group/i_group_test.py` | Independent I-Group test suite: `MockVehicleManager` (supports violation modes), `IGroupConstraintVerifier`, `IGroupTestSuite`, `IGroupStressTest` |
| `i_group/i_group_viz.py` | `IGroupTestVisualizer` — animated view of i-group signals + mock vehicles; supports all violation modes |

### Per-Step Simulation Loop

1. Spawn vehicles probabilistically at Point A
2. V-Group → I-Group: send `VehicleState` list
3. I-Group → V-Group: return `InfrastructureState` (signal states)
4. V-Group updates vehicle positions respecting signals
5. Constraint verification

### Key Design Detail: Vehicles Never Occupy Intersection Nodes

Vehicles exist only on road-segment slots (`slot >= 1`). When a vehicle reaches the last slot of a segment and has a GREEN signal, it jumps directly to `slot=1` of the chosen exit road on the far side of the intersection in a single step. Checkpoint visits are detected during this crossing. The `COMPLETION_SENTINEL` (`Position(-1,0,0,WEST)`) is returned when a vehicle crosses back into Point A — it is never stored on the vehicle.

### Conflict Resolution

When multiple vehicles target the same `Position` in a step, the lowest-ID vehicle wins; others stay put. This is handled in `VehicleManager.update_vehicles()`.

### V-Group Routing Optimizations

One optimization is active in `VehicleManager`:

- **Strategy E — Alternating checkpoint order**: only two checkpoint orderings achieve the minimum 244-slot tour (B→C→D counterclockwise and D→C→B clockwise; all other orderings are 364 slots). Even-ID vehicles follow B→C→D and odd-ID vehicles follow D→C→B. This distributes vehicles across opposite sides of the grid after crossing (0,0), halving congestion on each outer-ring segment and reducing signal contention. `_checkpoint_plans` stores the pre-planned order per vehicle.

### Road Network

- 3x3 grid of intersections with coordinates `(x, y)` (x right, y down)
- **Point A** (spawn/destination): left of `(0,0)` — encoded as `x=-1, y=0`
- **Checkpoint B**: `(0,2)`, **C**: `(2,2)`, **D**: `(2,0)`
- Each vehicle must visit B, C, D in any order then return to A
- Road segments have directional slots; no two vehicles can share a slot
- `Position(x, y, slot, direction)` — `slot=0` is unused in practice (vehicles skip over intersections), `slot>0` means on a road segment; slot count per segment is in `RoadNetwork.SEGMENTS` (2 slots for A<->(0,0), 30 for all others)
- Westward roads exist only from `x>0` or from `(0,0)` to A; the `(0,1)` and `(0,2)` rows have no westward road

### Three Critical Constraints

1. **No Collision** — no two vehicles may occupy the same `Position`
2. **No Red Light Violation** — vehicles may only cross intersections on GREEN
3. **No U-turn** — vehicles cannot immediately reverse direction

These are enforced in `VehicleManager.verify_constraints()` and independently verified in `ConstraintVerifier` within the test suite.

### Signal Control

- **I-Group signals** use arrival direction at the destination intersection: key format `(x, y, direction)` -> `SignalState`, where `direction` is the direction the vehicle is traveling when it arrives
- Demand-based: GREEN goes to the direction with the most waiting vehicles, with starvation counters (`direction_wait_steps`) to prevent priority inversion
- Exactly one GREEN per intersection at any time

### MockInfrastructure Signal Strategies (for V-Group testing)

`"random"`, `"all_green"`, `"all_red"`, `"cyclic"`, `"smart"`, `"adversarial"` — passed to `MockInfrastructure(signal_strategy=...)` or `VGroupTestSuite(signal_strategy=...)`

### MockVehicleManager Violation Modes (for I-Group testing)

`"none"`, `"red_light"`, `"uturn"`, `"wrong_lane"`, `"all"` — passed to `MockVehicleManager(violation_mode=..., violation_rate=0.1)` or `IGroupTestSuite(violation_mode=...)`. Deliberately injects the named violation type at the given rate to verify `InfrastructureManager` detection.

### I-Group Violation Reporting

`InfrastructureManager` internally tracks violations across consecutive vehicle-state snapshots:
- **collision** — two vehicles at the same position
- **red_light** — vehicle crossed an intersection while its signal was RED
- **uturn** — vehicle reversed direction at an intersection
- **wrong_lane** — vehicle moved backward on a road segment (decreasing slot)

Access via `infra.get_violation_report()` or `infra.print_violation_report()`.

### Physical Scale

| Quantity | Value |
|---|---|
| 1 time step | 2 seconds |
| Intersection spacing | 0.5 miles |
| A → (0,0) distance | 1/30 mile |
| Slot length (all segments) | 1/60 mile ≈ 88 ft |
| Vehicle speed | 30 mph |
| Time to traverse one segment (30 slots) | 60 s (1 min) |
| Minimum green phase (2 steps) | 4 seconds |

Constants are defined in `common.py`: `TIME_STEP_SECONDS`, `INTERSECTION_SPACING_MILES`, `ENTRY_SEGMENT_MILES`, `SLOT_LENGTH_MILES`, `VEHICLE_SPEED_MPH`, `STEPS_PER_HOUR`.

**Throughput** is measured as vehicles completing the full A→B→C→D→A trip per hour (= per 1800 steps). All test suites and `simulation.py` default to 1800-step (1-hour) runs and report throughput in vehicles/hour.

### Key Configuration (in `simulation.py`)

```python
Simulation(max_vehicles=None, max_time_steps=STEPS_PER_HOUR)
# max_vehicles=None means no cap; spawn_rate is a hardcoded field (default 1.0)
```
