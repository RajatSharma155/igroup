┌─────────────────────────────────────────────────────────┐
│                    V-Group Test Suite                    │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐      ┌─────────────────┐             │
│  │ VehicleManager│◄────┤MockInfrastructure│             │
│  │ (v_group.py)  │      │ (Signals)       │             │
│  └───────┬───────┘      └─────────────────┘             │
│          │                                               │
│          │ ┌──────────────────────────────┐             │
│          └─┤ ConstraintVerifier           │             │
│            │ (Built into VehicleManager)  │             │
│            └──────────────────────────────┘             │
│                                                           │
│  ┌────────────────┐      ┌──────────────┐               │
│  │ VGroupTestSuite│      │ VGroupDebugger│              │
│  │ (Test Runner)  │      │ (Debug Tools) │              │
│  └────────────────┘      └──────────────┘               │
└─────────────────────────────────────────────────────────┘

1. MockInfrastructure → Generate Signals
2. VehicleManager → Get Vehicle States
3. VehicleManager → Update Positions (respecting signals)
4. VehicleManager → Verify Constraints (built-in)
5. TestSuite → Collect and Report Results


# V-Group Independent Test Setup - Usage Guide
---

## Overview

The V-Group Independent Test Setup provides a comprehensive testing framework for the vehicle management software (V-Group) that operates independently from the infrastructure software (I-Group). It includes built-in constraint verification, multiple testing strategies, and debugging tools to ensure robust vehicle behavior under any traffic signal conditions.

**Purpose**: Verify that V-Group maintains all safety constraints regardless of infrastructure signal patterns.

---

## Key Features

### ✅ Independent Testing
- Test V-Group without requiring I-Group implementation
- Mock infrastructure provides configurable signal patterns
- Complete simulation environment included

### ✅ Built-in Constraint Verification
All verification integrated directly into `VehicleManager`:

1. **No Collisions**
   - Ensures no two vehicles occupy the same position
   - Validates one vehicle per slot rule
   - Checks intersection occupancy

2. **No Red Light Violations**
   - Vehicles respect traffic signals
   - No entering intersections on red
   - No exiting intersections on red

3. **No Opposite Direction Violations**
   - Prevents U-turns
   - No direction reversals
   - No backward movement in lanes

### ✅ Multiple Signal Strategies

| Strategy | Description | Use Case |
|----------|-------------|----------|
| `random` | Random signal patterns at each intersection | General robustness testing |
| `all_green` | All signals green (enforced to one per intersection) | Maximum flow testing |
| `all_red` | All signals red | Deadlock prevention testing |
| `cyclic` | Time-based rotation through directions | Realistic traffic patterns |
| `smart` | Demand-based signal optimization | Optimal conditions testing |
| `adversarial` | Signals that block waiting vehicles | Worst-case scenario testing |

### ✅ Comprehensive Testing Modes
- **Single Test**: Test specific signal strategy
- **Stress Test**: Compare all strategies
- **Scenario Tests**: High density, adversarial, all-red
- **Custom Tests**: Create your own test scenarios

### ✅ Debug Tools
- **Vehicle Tracing**: Follow individual vehicle journey
- **Intersection Monitoring**: Watch intersection activity
- **Deadlock Detection**: Identify stuck vehicles
- **Step-by-step Logging**: Detailed execution trace

### ✅ Detailed Reporting
- Per-constraint violation counts
- Vehicle completion statistics
- Comparative analysis across strategies
- Performance metrics

---

## Installation

### Prerequisites
