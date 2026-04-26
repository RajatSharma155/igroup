# i_group/i_group_test.py - Independent test setup for I-Group
#
# Provides a MockVehicleManager that generates realistic traffic
# (A → B/C/D → A) and feeds it to InfrastructureManager.  A
# ConstraintVerifier then checks the three system invariants:
#   1. No collision       — no two vehicles share a road-segment slot
#   2. No red-light cross — vehicles only cross intersections on GREEN
#   3. No U-turn / back   — vehicles never reverse direction or slot
#
# The i-group-specific signal invariant (≤1 GREEN per intersection) is
# also verified after every call to process_vehicle_states().

import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from common import *
from i_group.i_group import InfrastructureManager


# ---------------------------------------------------------------------------
# Mock vehicle simulator
# ---------------------------------------------------------------------------

@dataclass
class MockVehicle:
    id: int
    position: Position
    visited: Set[str] = field(default_factory=set)

    def needs_to_visit(self) -> Set[str]:
        return {'B', 'C', 'D'} - self.visited


class MockVehicleManager:
    """Simulates realistic vehicle traffic for i-group testing.

    Vehicles spawn at Point A, visit checkpoints B/C/D in nearest-first
    order, then return to A.  Movement respects signal states returned by
    InfrastructureManager: a vehicle at the last slot of a segment waits
    when the signal ahead is RED and crosses when it is GREEN.

    Collision avoidance: when two vehicles would enter the same slot, the
    lower-ID vehicle takes priority and the other waits one step.

    Violation modes (deliberate rule-breaking for testing i-group detection):
      "none"        — fully law-abiding (default)
      "red_light"   — occasionally run RED signals at intersections
      "uturn"       — occasionally make a U-turn at an intersection
      "wrong_lane"  — occasionally move backward on a road segment
      "all"         — all three violation types simultaneously

    violation_rate controls how often a violation is attempted per eligible
    decision (0.0 = never, 1.0 = always).
    """

    _CHECKPOINTS: Dict[str, Tuple[int, int]] = {
        'A': (-1, 0), 'B': (0, 2), 'C': (2, 2), 'D': (2, 0)
    }
    # Sentinel position returned when a vehicle completes its tour.
    # Never stored on the vehicle; detected by update() and removed.
    _DONE = Position(-1, 0, 0, Direction.WEST)

    def __init__(self, max_vehicles: int = None,
                 violation_mode: str = "none",
                 violation_rate: float = 0.1):
        self.vehicles: Dict[int, MockVehicle] = {}
        self._next_id = 0
        self.max_vehicles = max_vehicles
        self.completed = 0
        self.violation_mode = violation_mode
        self.violation_rate = violation_rate
        self._active_violations: Set[str] = self._resolve_modes(violation_mode)

    @staticmethod
    def _resolve_modes(mode: str) -> Set[str]:
        if mode == "all":
            return {"red_light", "uturn", "wrong_lane"}
        if mode in ("red_light", "uturn", "wrong_lane"):
            return {mode}
        return set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def spawn_vehicle(self) -> Optional[MockVehicle]:
        """Attempt to spawn a new vehicle at Point A (slot 1, EAST)."""
        if self.max_vehicles is not None and len(self.vehicles) >= self.max_vehicles:
            return None
        start = Position(-1, 0, 1, Direction.EAST)
        for v in self.vehicles.values():
            if v.position == start:
                return None
        vehicle = MockVehicle(id=self._next_id, position=start)
        self.vehicles[self._next_id] = vehicle
        self._next_id += 1
        return vehicle

    def get_vehicle_states(self) -> List[VehicleState]:
        return [VehicleState(id=v.id, position=v.position)
                for v in self.vehicles.values()]

    def update(self, infra_state: InfrastructureState):
        """Advance all vehicles one step according to infra_state signals."""
        occupied: Set[Position] = {v.position for v in self.vehicles.values()}

        # Compute intended moves for every vehicle
        moves: Dict[int, Optional[Position]] = {}
        for vid, vehicle in self.vehicles.items():
            moves[vid] = self._decide(vehicle, infra_state,
                                      occupied - {vehicle.position})

        # Conflict resolution: only one vehicle may enter any slot per step.
        # Lower ID wins; others stay put.
        dest_claims: Dict[Position, List[int]] = defaultdict(list)
        for vid, pos in moves.items():
            if pos is None or pos is self._DONE:
                continue
            dest_claims[pos].append(vid)
        for pos, vids in dest_claims.items():
            if len(vids) > 1:
                for loser in sorted(vids)[1:]:
                    moves[loser] = None

        # Apply moves, detect checkpoint crossings and tour completions
        cp_coords = {'B': (0, 2), 'C': (2, 2), 'D': (2, 0)}
        to_remove: List[int] = []

        for vid, next_pos in moves.items():
            if next_pos is None:
                continue
            vehicle = self.vehicles[vid]
            prev = vehicle.position

            if next_pos is self._DONE:
                to_remove.append(vid)
                self.completed += 1
                continue

            vehicle.position = next_pos

            # Checkpoint visit: vehicle jumped from last slot of one segment
            # to slot 1 of the next; the crossed intersection is next_pos.(x,y)
            prev_max = RoadNetwork.get_max_slots(prev.x, prev.y, prev.direction)
            if prev.slot == prev_max and next_pos.slot == 1:
                crossed = (next_pos.x, next_pos.y)
                for cp, coord in cp_coords.items():
                    if crossed == coord:
                        vehicle.visited.add(cp)

        for vid in to_remove:
            del self.vehicles[vid]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _nearest_target(self, xy: Tuple[int, int],
                        visited: Set[str]) -> Tuple[int, int]:
        """Return the coordinates of the nearest unvisited checkpoint."""
        remaining = {'B', 'C', 'D'} - visited
        if not remaining:
            return (-1, 0)  # All visited → head back to A
        return min(
            (self._CHECKPOINTS[cp] for cp in remaining),
            key=lambda t: abs(t[0] - xy[0]) + abs(t[1] - xy[1])
        )

    def _decide(self, vehicle: MockVehicle,
                infra_state: InfrastructureState,
                occupied: Set[Position]) -> Optional[Position]:
        """Return the position this vehicle should move to, or None to wait.

        When self._active_violations is non-empty, the vehicle may deliberately
        break rules according to self.violation_rate:
          wrong_lane  — go backward (slot - 1) instead of forward mid-segment
          red_light   — cross an intersection even when the signal is RED
          uturn       — enter the intersection going the opposite direction
        """
        pos = vehicle.position
        max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)

        # ----- Wrong-lane violation: move backward mid-segment ----------
        if ("wrong_lane" in self._active_violations
                and pos.slot < max_slots   # mid-segment
                and pos.slot > 1           # slot 0 is unused; can't go below 1
                and random.random() < self.violation_rate):
            back = Position(pos.x, pos.y, pos.slot - 1, pos.direction)
            if back not in occupied:
                return back

        # Mid-segment normal advance
        if pos.slot < max_slots:
            next_pos = Position(pos.x, pos.y, pos.slot + 1, pos.direction)
            return None if next_pos in occupied else next_pos

        # ---- At last slot: compute destination intersection -------------
        d = pos.direction
        if d == Direction.EAST:    dest = (pos.x + 1, pos.y)
        elif d == Direction.WEST:  dest = (pos.x - 1, pos.y)
        elif d == Direction.SOUTH: dest = (pos.x, pos.y + 1)
        else:                      dest = (pos.x, pos.y - 1)

        # ----- Red-light violation: cross even when signal is RED -------
        signal = infra_state.signals.get((dest[0], dest[1], d))
        if signal == SignalState.RED:
            if ("red_light" not in self._active_violations
                    or random.random() >= self.violation_rate):
                return None  # Obey RED
            # else: deliberately run the red light — fall through

        # Returning to Point A?
        if dest == (-1, 0):
            return self._DONE

        # ----- U-turn violation: reverse direction at intersection ------
        if "uturn" in self._active_violations and random.random() < self.violation_rate:
            uturn_dir = d.opposite()
            valid_exits = {exit_dir for _, _, exit_dir
                           in RoadNetwork.get_neighbors(dest[0], dest[1])}
            if uturn_dir in valid_exits:
                uturn_pos = Position(dest[0], dest[1], 1, uturn_dir)
                if uturn_pos not in occupied:
                    return uturn_pos

        # Normal routing: greedy nearest-checkpoint exit (no U-turn)
        target = self._nearest_target(dest, vehicle.visited)
        candidates = []
        for nx, ny, exit_dir in RoadNetwork.get_neighbors(dest[0], dest[1]):
            if exit_dir == d.opposite():
                continue  # No U-turn in normal routing
            next_pos = Position(dest[0], dest[1], 1, exit_dir)
            if next_pos in occupied:
                continue
            dist = abs(nx - target[0]) + abs(ny - target[1])
            candidates.append((dist, next_pos))

        if not candidates:
            return None  # All exits blocked; wait
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]


# ---------------------------------------------------------------------------
# Constraint verifier
# ---------------------------------------------------------------------------

class IGroupConstraintVerifier:
    """Verifies the three traffic constraints and the i-group signal invariant."""

    # ------------------------------------------------------------------
    # Signal invariant (i-group specific)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_signal_invariant(infra_state: InfrastructureState) -> Tuple[bool, List[str]]:
        """Verify at most one GREEN signal per intersection."""
        violations = []
        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue
                greens = [
                    d for d in RoadNetwork.get_valid_arrival_directions(x, y)
                    if infra_state.signals.get((x, y, d)) == SignalState.GREEN
                ]
                if len(greens) > 1:
                    violations.append(
                        f"SIGNAL INVARIANT: ({x},{y}) has {len(greens)} GREEN signals: "
                        f"{[d.name for d in greens]}"
                    )
        return len(violations) == 0, violations

    # ------------------------------------------------------------------
    # Traffic constraints
    # ------------------------------------------------------------------

    @staticmethod
    def verify_no_collision(vm: MockVehicleManager) -> Tuple[bool, List[str]]:
        """No two vehicles may share the same road-segment slot."""
        violations = []
        seen: Dict[Position, int] = {}
        for v in vm.vehicles.values():
            if v.position in seen:
                violations.append(
                    f"COLLISION: V{v.id} and V{seen[v.position]} "
                    f"both at ({v.position.x},{v.position.y}) "
                    f"slot={v.position.slot} dir={v.position.direction.name}"
                )
            else:
                seen[v.position] = v.id
        return len(violations) == 0, violations

    @staticmethod
    def _crossed_intersection(prev_pos: Position) -> Optional[Tuple[int, int]]:
        """Return the intersection crossed if prev_pos was at the last slot, else None."""
        max_slots = RoadNetwork.get_max_slots(
            prev_pos.x, prev_pos.y, prev_pos.direction)
        if prev_pos.slot != max_slots:
            return None
        d = prev_pos.direction
        if d == Direction.EAST:   return (prev_pos.x + 1, prev_pos.y)
        if d == Direction.WEST:   return (prev_pos.x - 1, prev_pos.y)
        if d == Direction.SOUTH:  return (prev_pos.x, prev_pos.y + 1)
        return (prev_pos.x, prev_pos.y - 1)

    @staticmethod
    def verify_no_red_light(
            vm: MockVehicleManager,
            prev_state: Dict[int, Position],
            infra_state: InfrastructureState,
            completed_ids: Set[int] = None) -> Tuple[bool, List[str]]:
        """No vehicle may cross an intersection while the signal is RED.

        Checks active vehicles (prev slot == max, curr slot == 1) and
        vehicles that completed their tour this step (prev at last slot,
        then crossed back to Point A).
        """
        violations = []

        def check_crossing(vid: int, prev_pos: Position) -> Optional[str]:
            crossed = IGroupConstraintVerifier._crossed_intersection(prev_pos)
            if crossed is None:
                return None
            sig = infra_state.signals.get((crossed[0], crossed[1], prev_pos.direction))
            if sig == SignalState.RED:
                return (
                    f"RED LIGHT: V{vid} crossed ({crossed[0]},{crossed[1]}) "
                    f"arriving {prev_pos.direction.name} on RED"
                )
            return None

        # Active vehicles that crossed an intersection this step
        for v in vm.vehicles.values():
            if v.id not in prev_state:
                continue
            prev_pos = prev_state[v.id]
            if prev_pos.slot == RoadNetwork.get_max_slots(
                    prev_pos.x, prev_pos.y, prev_pos.direction) and v.position.slot == 1:
                msg = check_crossing(v.id, prev_pos)
                if msg:
                    violations.append(msg)

        # Vehicles that completed (crossed back to A) this step
        if completed_ids:
            for vid in completed_ids:
                if vid in prev_state:
                    msg = check_crossing(vid, prev_state[vid])
                    if msg:
                        violations.append(msg)

        return len(violations) == 0, violations

    @staticmethod
    def verify_no_opposite_direction(
            vm: MockVehicleManager,
            prev_state: Dict[int, Position]) -> Tuple[bool, List[str]]:
        """No vehicle may make a U-turn or move backwards on its segment."""
        violations = []
        for v in vm.vehicles.values():
            if v.id not in prev_state:
                continue
            prev = prev_state[v.id]
            curr = v.position

            if curr.direction == prev.direction.opposite():
                violations.append(
                    f"U-TURN: V{v.id} reversed "
                    f"{prev.direction.name}→{curr.direction.name} "
                    f"at ({curr.x},{curr.y})"
                )

            if (prev.direction == curr.direction
                    and prev.x == curr.x and prev.y == curr.y
                    and curr.slot < prev.slot):
                violations.append(
                    f"BACKWARD: V{v.id} slot {prev.slot}→{curr.slot} "
                    f"on ({curr.x},{curr.y}) {curr.direction.name}"
                )

        return len(violations) == 0, violations

    @staticmethod
    def verify_all(
            vm: MockVehicleManager,
            prev_state: Dict[int, Position],
            infra_state: InfrastructureState,
            completed_ids: Set[int] = None) -> Tuple[bool, Dict[str, List[str]]]:
        """Run all four checks and return (all_ok, {category: [messages]})."""
        all_violations: Dict[str, List[str]] = {}

        _, sig_v = IGroupConstraintVerifier.verify_signal_invariant(infra_state)
        if sig_v:
            all_violations['signal_invariant'] = sig_v

        _, coll_v = IGroupConstraintVerifier.verify_no_collision(vm)
        if coll_v:
            all_violations['collision'] = coll_v

        _, red_v = IGroupConstraintVerifier.verify_no_red_light(
            vm, prev_state, infra_state, completed_ids)
        if red_v:
            all_violations['red_light'] = red_v

        _, opp_v = IGroupConstraintVerifier.verify_no_opposite_direction(vm, prev_state)
        if opp_v:
            all_violations['opposite_direction'] = opp_v

        return len(all_violations) == 0, all_violations


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class IGroupTestSuite:
    """Runs InfrastructureManager against MockVehicleManager traffic
    and verifies all constraints after every step."""

    def __init__(self, max_vehicles: int = None, verbose: bool = True,
                 violation_mode: str = "none", violation_rate: float = 0.1):
        self.vm = MockVehicleManager(max_vehicles,
                                     violation_mode=violation_mode,
                                     violation_rate=violation_rate)
        self.infra = InfrastructureManager()
        self.verifier = IGroupConstraintVerifier()
        self.verbose = verbose
        self.results = {
            'steps': 0, 'completed': 0,
            'signal_invariant': 0, 'collision': 0,
            'red_light': 0, 'opposite_direction': 0,
            'total_violations': 0,
            'warmup_completed': 0,
        }

    def log(self, msg: str, level: str = "INFO"):
        if self.verbose:
            print(f"[{level}] {msg}")

    def run(self, num_steps: int = 500, spawn_rate: float = 0.3):
        mode_str = self.vm.violation_mode
        rate_str = f"{self.vm.violation_rate:.0%}" if mode_str != "none" else "—"
        self.log(f"Starting I-Group Test: {num_steps} steps, "
                 f"max_vehicles={self.vm.max_vehicles}, spawn_rate={spawn_rate}, "
                 f"violation_mode={mode_str}, rate={rate_str}")
        self.log("=" * 70)

        for step in range(num_steps):
            self.results['steps'] = step + 1

            # Spawn
            if random.random() < spawn_rate:
                v = self.vm.spawn_vehicle()
                if v:
                    self.log(f"Step {step}: Spawned V{v.id}", "SPAWN")

            # Snapshot
            prev_positions = {v.id: v.position for v in self.vm.vehicles.values()}
            prev_ids = set(self.vm.vehicles.keys())

            # I-Group: process states → produce signals
            vehicle_states = self.vm.get_vehicle_states()
            infra_state = self.infra.process_vehicle_states(vehicle_states)

            # Mock vehicles move according to signals
            self.vm.update(infra_state)

            completed_ids = prev_ids - set(self.vm.vehicles.keys())

            # Verify all constraints
            all_ok, violations = self.verifier.verify_all(
                self.vm, prev_positions, infra_state, completed_ids)

            if not all_ok:
                self.results['total_violations'] += 1
                for vtype, msgs in violations.items():
                    self.results[vtype] += len(msgs)
                    for m in msgs:
                        self.log(f"Step {step}: {m}", "VIOLATION")

            if step % 50 == 0:
                self._log_status(step)

            # Snapshot completions at end of warm-up period
            if step == WARMUP_STEPS - 1:
                self.results['warmup_completed'] = self.vm.completed

            if self.results['total_violations'] > 10:
                self.log("Too many violations — stopping", "ERROR")
                break

        self.results['completed'] = self.vm.completed
        self._print_report()

    def _log_status(self, step: int):
        active = len(self.vm.vehicles)
        self.log("-" * 70)
        self.log(f"Step {step}: Active={active}, "
                 f"Completed={self.vm.completed}, "
                 f"Violations={self.results['total_violations']}")
        for v in list(self.vm.vehicles.values())[:3]:
            pos = v.position
            visited = ','.join(sorted(v.visited)) or 'None'
            self.log(f"  V{v.id}: ({pos.x},{pos.y}) slot={pos.slot} "
                     f"dir={pos.direction.name} visited=[{visited}]")

    def _print_report(self):
        self.log("=" * 70)
        self.log("FINAL REPORT", "REPORT")
        self.log("=" * 70)
        steps = self.results['steps']
        completed = self.results['completed']
        hours = steps * TIME_STEP_SECONDS / 3600
        throughput = completed / hours if hours > 0 else 0

        ss_steps = max(steps - WARMUP_STEPS, 0)
        ss_hours = ss_steps * TIME_STEP_SECONDS / 3600
        ss_completed = completed - self.results['warmup_completed']
        ss_throughput = ss_completed / ss_hours if ss_hours > 0 else 0

        self.log(f"Steps:             {steps}  ({hours:.2f} hours simulated)")
        self.log(f"Completed vehicles:{completed}")
        self.log(f"Throughput (overall):      {throughput:.1f} vehicles/hour")
        self.log(f"Throughput (steady-state): {ss_throughput:.1f} vehicles/hour"
                 f"  (after {WARMUP_STEPS}-step warm-up)")
        self.log(f"Active vehicles:   {len(self.vm.vehicles)}")
        self.log("")
        self.log("CONSTRAINT VIOLATIONS (test-suite verifier):")
        self.log(f"  Signal invariant: {self.results['signal_invariant']}")
        self.log(f"  Collisions:       {self.results['collision']}")
        self.log(f"  Red lights:       {self.results['red_light']}")
        self.log(f"  Opposite dir:     {self.results['opposite_direction']}")
        self.log(f"  Total events:     {self.results['total_violations']}")
        self.log("")
        igr = self.infra.get_violation_report()
        self.log("VIOLATIONS REPORTED BY I-GROUP (InfrastructureManager):")
        self.log(f"  Collisions:       {igr['collision']}")
        self.log(f"  Red-light runs:   {igr['red_light']}")
        self.log(f"  U-turns:          {igr['uturn']}")
        self.log(f"  Wrong lane:       {igr['wrong_lane']}")
        self.log(f"  Total:            {igr['total']}")
        self.log("")
        if self.results['total_violations'] == 0:
            self.log("✓ ALL CONSTRAINTS SATISFIED", "SUCCESS")
        else:
            self.log("✗ VIOLATIONS DETECTED", "FAILURE")
        self.log("=" * 70)
        return self.results['total_violations'] == 0


# ---------------------------------------------------------------------------
# Stress test
# ---------------------------------------------------------------------------

class IGroupStressTest:
    """Runs IGroupTestSuite across low/medium/high vehicle density configs."""

    def __init__(self):
        self.results: Dict[str, dict] = {}

    def run(self, steps: int = STEPS_PER_HOUR):
        configs = [
            ("low_density",    None, 0.2),
            ("medium_density", None, 0.4),
            ("high_density",   None, 0.8),
        ]

        print("\n" + "=" * 70)
        print("I-GROUP STRESS TEST")
        print("=" * 70)

        for name, max_v, rate in configs:
            cap_str = str(max_v) if max_v is not None else "None"
            print(f"\n{'='*70}")
            print(f"Config: {name.upper()}  (max_vehicles={cap_str}, spawn_rate={rate})")
            print("=" * 70)
            suite = IGroupTestSuite(max_vehicles=max_v, verbose=False)
            suite.run(num_steps=steps, spawn_rate=rate)
            r = suite.results.copy()
            r['_igr'] = suite.infra.get_violation_report()
            self.results[name] = r

        self._print_comparative()

    def _print_comparative(self):
        print("\n" + "=" * 70)
        print("COMPARATIVE REPORT")
        print("=" * 70)

        print(f"\n{'Config':<20} {'Steps':<8} {'Completed':<12} {'Veh/hr (SS)':<14} {'Violations':<12}")
        print("-" * 78)
        for name, r in self.results.items():
            ss_steps = max(r['steps'] - WARMUP_STEPS, 0)
            ss_hours = ss_steps * TIME_STEP_SECONDS / 3600
            ss_completed = r['completed'] - r.get('warmup_completed', 0)
            ss_throughput = ss_completed / ss_hours if ss_hours > 0 else 0
            print(f"{name:<20} {r['steps']:<8} {r['completed']:<12} "
                  f"{ss_throughput:<14.1f} {r['total_violations']:<12}")

        print(f"\n{'Config':<20} {'Sig.Inv':<10} {'Collision':<12} "
              f"{'Red Light':<12} {'Opp.Dir':<12}")
        print("-" * 70)
        for name, r in self.results.items():
            print(f"{name:<20} {r['signal_invariant']:<10} {r['collision']:<12} "
                  f"{r['red_light']:<12} {r['opposite_direction']:<12}")

        print(f"\nI-GROUP INTERNAL REPORT (InfrastructureManager counts):")
        print(f"{'Config':<20} {'Collision':<12} {'Red Light':<12} {'U-turn':<12} {'Wrong Lane':<12} {'Total':<10}")
        print("-" * 76)
        for name, r in self.results.items():
            igr = r.get('_igr', {})
            print(f"{name:<20} {igr.get('collision',0):<12} {igr.get('red_light',0):<12} "
                  f"{igr.get('uturn',0):<12} {igr.get('wrong_lane',0):<12} {igr.get('total',0):<10}")

        total = sum(r['total_violations'] for r in self.results.values())
        passed = sum(1 for r in self.results.values() if r['total_violations'] == 0)
        print(f"\nConfigs Passed: {passed}/{len(self.results)}")
        print(f"Total Violations: {total}")
        if total == 0:
            print("\n✓ ALL CONFIGS PASSED — I-GROUP IS ROBUST")
        else:
            print("\n✗ SOME CONFIGS FAILED — I-GROUP NEEDS IMPROVEMENT")
        print("=" * 70 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 70)
    print("I-GROUP INDEPENDENT TEST SUITE")
    print("=" * 70)

    print("\nSelect test mode:")
    print("--- Law-abiding traffic ---")
    print("1. Single test — low density  (spawn_rate=0.2)")
    print("2. Single test — medium density (spawn_rate=0.4)")
    print("3. Single test — high density (spawn_rate=0.8)")
    print("4. Stress test (all density configs)")
    print("--- Violation modes (spawn_rate=0.4, 20% violation rate) ---")
    print("5. Red-light violations only")
    print("6. U-turn violations only")
    print("7. Wrong-lane (backward) violations only")
    print("8. All violations combined")

    choice = input("\nEnter choice (1-8): ").strip()

    if choice == "1":
        IGroupTestSuite().run(num_steps=STEPS_PER_HOUR, spawn_rate=0.2)
    elif choice == "2":
        IGroupTestSuite().run(num_steps=STEPS_PER_HOUR, spawn_rate=0.4)
    elif choice == "3":
        IGroupTestSuite().run(num_steps=STEPS_PER_HOUR, spawn_rate=0.8)
    elif choice == "4":
        IGroupStressTest().run()
    elif choice == "5":
        IGroupTestSuite(violation_mode="red_light",
                        violation_rate=0.2).run(num_steps=STEPS_PER_HOUR, spawn_rate=0.4)
    elif choice == "6":
        IGroupTestSuite(violation_mode="uturn",
                        violation_rate=0.2).run(num_steps=STEPS_PER_HOUR, spawn_rate=0.4)
    elif choice == "7":
        IGroupTestSuite(violation_mode="wrong_lane",
                        violation_rate=0.2).run(num_steps=STEPS_PER_HOUR, spawn_rate=0.4)
    elif choice == "8":
        IGroupTestSuite(violation_mode="all",
                        violation_rate=0.2).run(num_steps=STEPS_PER_HOUR, spawn_rate=0.4)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
