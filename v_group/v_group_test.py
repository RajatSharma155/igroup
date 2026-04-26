# v_group_test.py - Independent test setup for V-Group

import random
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from common import *
from v_group.v_group import VehicleManager

class MockInfrastructure:
    """Mock infrastructure for testing v-group independently"""
    
    def __init__(self, signal_strategy: str = "random"):
        """
        Args:
            signal_strategy: "random", "all_green", "all_red", "cyclic", "smart"
        """
        self.signal_strategy = signal_strategy
        self.time_step = 0
        self.cyclic_state = {}  # For cyclic strategy
        self.cycle_duration = 10
        
    def generate_signals(self, vehicle_states: List[VehicleState]) -> InfrastructureState:
        """Generate traffic signals based on strategy"""
        
        signals = {}
        
        if self.signal_strategy == "random":
            signals = self._random_signals()
        elif self.signal_strategy == "all_green":
            signals = self._all_green_signals()
        elif self.signal_strategy == "all_red":
            # Return directly — skip enforcement so signals stay fully RED.
            # _enforce_one_green_per_intersection would otherwise add a random
            # GREEN at every intersection (since zero GREENs triggers its
            # fallback), turning all_red into random.
            signals = self._all_red_signals()
            self.time_step += 1
            return InfrastructureState(signals=signals, time_step=self.time_step)
        elif self.signal_strategy == "cyclic":
            signals = self._cyclic_signals()
        elif self.signal_strategy == "smart":
            signals = self._smart_signals(vehicle_states)
        elif self.signal_strategy == "adversarial":
            signals = self._adversarial_signals(vehicle_states)
        else:
            signals = self._random_signals()

        # Ensure only one green per intersection
        signals = self._enforce_one_green_per_intersection(signals)
        
        self.time_step += 1
        
        return InfrastructureState(signals=signals, time_step=self.time_step)
    
    def _random_signals(self) -> Dict:
        """Randomly assign one green signal per intersection"""
        signals = {}

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                valid_arrivals = list(RoadNetwork.get_valid_arrival_directions(x, y))
                green_direction = random.choice(valid_arrivals)

                for direction in valid_arrivals:
                    signals[(x, y, direction)] = (
                        SignalState.GREEN if direction == green_direction else SignalState.RED
                    )

        return signals

    def _all_green_signals(self) -> Dict:
        """All valid-arrival signals green (enforced to one per intersection later)"""
        signals = {}

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                for direction in RoadNetwork.get_valid_arrival_directions(x, y):
                    signals[(x, y, direction)] = SignalState.GREEN

        return signals

    def _all_red_signals(self) -> Dict:
        """All signals red"""
        signals = {}

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                for direction in RoadNetwork.get_valid_arrival_directions(x, y):
                    signals[(x, y, direction)] = SignalState.RED

        return signals

    def _cyclic_signals(self) -> Dict:
        """Cycle through valid arrival directions at each intersection"""
        signals = {}

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                valid_arrivals = sorted(
                    RoadNetwork.get_valid_arrival_directions(x, y), key=lambda d: d.value
                )
                cycle_position = (self.time_step // self.cycle_duration) % len(valid_arrivals)
                green_direction = valid_arrivals[cycle_position]

                for direction in valid_arrivals:
                    signals[(x, y, direction)] = (
                        SignalState.GREEN if direction == green_direction else SignalState.RED
                    )

        return signals

    def _smart_signals(self, vehicle_states: List[VehicleState]) -> Dict:
        """Smart signals based on vehicle positions"""
        signals = {}

        from collections import defaultdict
        demand = defaultdict(int)

        # Demand comes from vehicles at the last slot, about to cross an intersection
        for vs in vehicle_states:
            pos = vs.position
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
            if pos.slot == max_slots:
                if pos.direction == Direction.EAST:
                    next_int = (pos.x + 1, pos.y)
                elif pos.direction == Direction.WEST:
                    next_int = (pos.x - 1, pos.y)
                elif pos.direction == Direction.SOUTH:
                    next_int = (pos.x, pos.y + 1)
                else:  # NORTH
                    next_int = (pos.x, pos.y - 1)
                demand[(next_int, pos.direction)] += 1

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                intersection = (x, y)
                valid_arrivals = list(RoadNetwork.get_valid_arrival_directions(x, y))

                max_demand = 0
                best_direction = valid_arrivals[0]

                for direction in valid_arrivals:
                    d = demand.get((intersection, direction), 0)
                    if d > max_demand:
                        max_demand = d
                        best_direction = direction

                if max_demand == 0:
                    best_direction = random.choice(valid_arrivals)

                for direction in valid_arrivals:
                    signals[(x, y, direction)] = (
                        SignalState.GREEN if direction == best_direction else SignalState.RED
                    )

        return signals

    def _adversarial_signals(self, vehicle_states: List[VehicleState]) -> Dict:
        """Adversarial signals - try to block vehicles"""
        signals = {}

        # Find directions vehicles are waiting to cross at each intersection
        vehicle_directions = set()
        for vs in vehicle_states:
            pos = vs.position
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
            if pos.slot == max_slots:
                if pos.direction == Direction.EAST:
                    next_int = (pos.x + 1, pos.y)
                elif pos.direction == Direction.WEST:
                    next_int = (pos.x - 1, pos.y)
                elif pos.direction == Direction.SOUTH:
                    next_int = (pos.x, pos.y + 1)
                else:  # NORTH
                    next_int = (pos.x, pos.y - 1)
                vehicle_directions.add((next_int[0], next_int[1], pos.direction))

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                valid_arrivals = list(RoadNetwork.get_valid_arrival_directions(x, y))
                # Prefer a direction that doesn't help any waiting vehicle
                available = [d for d in valid_arrivals if (x, y, d) not in vehicle_directions]
                green_direction = random.choice(available if available else valid_arrivals)

                for direction in valid_arrivals:
                    signals[(x, y, direction)] = (
                        SignalState.GREEN if direction == green_direction else SignalState.RED
                    )

        return signals

    def _enforce_one_green_per_intersection(self, signals: Dict) -> Dict:
        """Ensure only one green signal per intersection (among valid arrival directions)"""

        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue

                valid_arrivals = list(RoadNetwork.get_valid_arrival_directions(x, y))
                green_directions = [
                    d for d in valid_arrivals if signals.get((x, y, d)) == SignalState.GREEN
                ]

                if len(green_directions) > 1:
                    keep_green = random.choice(green_directions)
                    for direction in green_directions:
                        if direction != keep_green:
                            signals[(x, y, direction)] = SignalState.RED

                elif len(green_directions) == 0:
                    signals[(x, y, random.choice(valid_arrivals))] = SignalState.GREEN

        return signals


class ConstraintVerifier:
    """Verify all v-group constraints"""
    
    @staticmethod
    def verify_no_collision(vehicle_manager: VehicleManager) -> Tuple[bool, List[str]]:
        """Verify no two vehicles occupy the same position"""
        violations = []
        
        position_map = {}
        for vehicle in vehicle_manager.vehicles.values():
            pos = vehicle.position
            
            if pos in position_map:
                other_id = position_map[pos]
                violations.append(
                    f"COLLISION: Vehicle {vehicle.id} and Vehicle {other_id} "
                    f"both at position ({pos.x}, {pos.y}) slot={pos.slot} dir={pos.direction.name}"
                )
            else:
                position_map[pos] = vehicle.id
        
        return len(violations) == 0, violations
    
    @staticmethod
    def _check_crossing_signal(vehicle_id: int, prev_pos: Position,
                               infra_state: InfrastructureState) -> Optional[str]:
        """Check if a vehicle crossing an intersection violated a red light.

        Returns a violation string if the signal was RED, else None.
        The caller must have already determined that prev_pos was at the
        last slot of a segment and the vehicle crossed the next intersection.
        """
        if prev_pos.direction == Direction.EAST:
            crossed = (prev_pos.x + 1, prev_pos.y)
        elif prev_pos.direction == Direction.WEST:
            crossed = (prev_pos.x - 1, prev_pos.y)
        elif prev_pos.direction == Direction.SOUTH:
            crossed = (prev_pos.x, prev_pos.y + 1)
        else:  # NORTH
            crossed = (prev_pos.x, prev_pos.y - 1)

        signal_key = (crossed[0], crossed[1], prev_pos.direction)
        if signal_key in infra_state.signals:
            if infra_state.signals[signal_key] == SignalState.RED:
                return (
                    f"RED LIGHT VIOLATION: Vehicle {vehicle_id} crossed "
                    f"intersection ({crossed[0]}, {crossed[1]}) from direction "
                    f"{prev_pos.direction.name} on RED signal"
                )
        return None

    @staticmethod
    def verify_no_red_light_violation(vehicle_manager: VehicleManager,
                                      prev_state: Dict[int, Position],
                                      infra_state: InfrastructureState,
                                      completed_ids: Set[int] = None) -> Tuple[bool, List[str]]:
        """Verify vehicles don't cross intersections on red lights.

        An intersection crossing is detected when a vehicle moves from the
        last slot of one road segment to slot 1 of the next segment.  The
        crossed intersection is computed from the travel direction.

        completed_ids: vehicles that completed their tour this step (removed
        from vehicle_manager).  Their final crossing back to Point A is also
        verified.
        """
        violations = []

        # Check vehicles still active
        for vehicle in vehicle_manager.vehicles.values():
            if vehicle.id not in prev_state:
                continue

            prev_pos = prev_state[vehicle.id]
            curr_pos = vehicle.position

            # Detect intersection crossing: prev at last slot, curr at slot 1
            prev_max = RoadNetwork.get_max_slots(prev_pos.x, prev_pos.y, prev_pos.direction)
            if prev_pos.slot == prev_max and curr_pos.slot == 1:
                msg = ConstraintVerifier._check_crossing_signal(
                    vehicle.id, prev_pos, infra_state
                )
                if msg:
                    violations.append(msg)

        # Check vehicles that completed this step (crossed back to Point A)
        if completed_ids:
            for vid in completed_ids:
                if vid not in prev_state:
                    continue
                prev_pos = prev_state[vid]
                prev_max = RoadNetwork.get_max_slots(prev_pos.x, prev_pos.y, prev_pos.direction)
                if prev_pos.slot == prev_max:
                    msg = ConstraintVerifier._check_crossing_signal(
                        vid, prev_pos, infra_state
                    )
                    if msg:
                        violations.append(msg)

        return len(violations) == 0, violations
    
    @staticmethod
    def verify_no_opposite_direction(vehicle_manager: VehicleManager,
                                     prev_state: Dict[int, Position]) -> Tuple[bool, List[str]]:
        """Verify vehicles don't make U-turns or move backwards"""
        violations = []

        for vehicle in vehicle_manager.vehicles.values():
            if vehicle.id not in prev_state:
                continue

            prev_pos = prev_state[vehicle.id]
            curr_pos = vehicle.position

            # Check if vehicle changed to opposite direction (U-turn)
            if curr_pos.direction == prev_pos.direction.opposite():
                violations.append(
                    f"OPPOSITE DIRECTION: Vehicle {vehicle.id} changed from "
                    f"{prev_pos.direction.name} to {curr_pos.direction.name} "
                    f"at position ({curr_pos.x}, {curr_pos.y})"
                )

            # Check for backward movement on the same segment
            if prev_pos.direction == curr_pos.direction:
                if prev_pos.x == curr_pos.x and prev_pos.y == curr_pos.y:
                    if curr_pos.slot < prev_pos.slot:
                        violations.append(
                            f"BACKWARD MOVEMENT: Vehicle {vehicle.id} moved backwards "
                            f"from slot {prev_pos.slot} to {curr_pos.slot}"
                        )

        return len(violations) == 0, violations
    
    @staticmethod
    def verify_all(vehicle_manager: VehicleManager,
                  prev_state: Dict[int, Position],
                  infra_state: InfrastructureState,
                  completed_ids: Set[int] = None) -> Tuple[bool, Dict[str, List[str]]]:
        """Verify all constraints"""

        all_violations = {}

        # Check collision
        collision_ok, collision_violations = ConstraintVerifier.verify_no_collision(vehicle_manager)
        if collision_violations:
            all_violations['collision'] = collision_violations

        # Check red light violations (including completed vehicles)
        red_light_ok, red_light_violations = ConstraintVerifier.verify_no_red_light_violation(
            vehicle_manager, prev_state, infra_state, completed_ids
        )
        if red_light_violations:
            all_violations['red_light'] = red_light_violations

        # Check opposite direction
        opposite_ok, opposite_violations = ConstraintVerifier.verify_no_opposite_direction(
            vehicle_manager, prev_state
        )
        if opposite_violations:
            all_violations['opposite_direction'] = opposite_violations

        return len(all_violations) == 0, all_violations


class VGroupTestSuite:
    """Comprehensive test suite for V-Group"""
    
    def __init__(self, signal_strategy: str = "random", verbose: bool = True):
        self.vehicle_manager = VehicleManager()
        self.mock_infra = MockInfrastructure(signal_strategy)
        self.verifier = ConstraintVerifier()
        self.verbose = verbose
        self.test_results = {
            'collision': 0,
            'red_light': 0,
            'opposite_direction': 0,
            'total_violations': 0,
            'steps': 0,
            'warmup_completed': 0,
        }
    
    def log(self, message: str, level: str = "INFO"):
        """Log message if verbose"""
        if self.verbose:
            prefix = f"[{level}]"
            print(f"{prefix} {message}")
    
    def run_test(self, num_steps: int = 500, spawn_rate: float = 1.0):
        """Run the test simulation"""

        self.log(f"Starting V-Group Test with {num_steps} steps")
        self.log(f"Signal Strategy: {self.mock_infra.signal_strategy}")
        self.log("=" * 70)

        prev_positions = {}

        for step in range(num_steps):
            self.test_results['steps'] = step + 1

            # Spawn vehicles
            if random.random() < spawn_rate:
                vehicle = self.vehicle_manager.spawn_vehicle()
                if vehicle:
                    self.log(f"Step {step}: Spawned vehicle {vehicle.id}", "SPAWN")

            # Save previous state
            prev_positions = {
                v.id: v.position
                for v in self.vehicle_manager.vehicles.values()
            }
            prev_vehicle_ids = set(self.vehicle_manager.vehicles.keys())

            # Get vehicle states
            vehicle_states = self.vehicle_manager.get_vehicle_states()

            # Generate infrastructure state (signals)
            infra_state = self.mock_infra.generate_signals(vehicle_states)

            # Update vehicles
            self.vehicle_manager.update_vehicles(infra_state)

            # Detect vehicles that completed this step
            completed_ids = prev_vehicle_ids - set(self.vehicle_manager.vehicles.keys())

            # Verify constraints (including completed vehicles' final crossing)
            all_ok, violations = self.verifier.verify_all(
                self.vehicle_manager, prev_positions, infra_state, completed_ids
            )

            if not all_ok:
                self.test_results['total_violations'] += 1

                for constraint_type, violation_list in violations.items():
                    self.test_results[constraint_type] += len(violation_list)

                    for violation in violation_list:
                        self.log(f"Step {step}: {violation}", "VIOLATION")

            # Snapshot completions at end of warm-up period
            if step == WARMUP_STEPS - 1:
                self.test_results['warmup_completed'] = self.vehicle_manager.completed_vehicles

            # Log status periodically
            if step % 50 == 0:
                self.log_status(step)

            # Stop if too many violations (test failure)
            if self.test_results['total_violations'] > 10:
                self.log("Too many violations - stopping test", "ERROR")
                break

        self.test_results['completed'] = self.vehicle_manager.completed_vehicles
        self.print_final_report()
    
    def log_status(self, step: int):
        """Log current status"""
        active = len(self.vehicle_manager.vehicles)
        completed = self.vehicle_manager.completed_vehicles
        violations = self.test_results['total_violations']
        
        self.log("-" * 70)
        self.log(f"Step {step}: Active={active}, Completed={completed}, Violations={violations}")
        
        # Show sample vehicles
        for i, vehicle in enumerate(list(self.vehicle_manager.vehicles.values())[:3]):
            pos = vehicle.position
            visited = ','.join(sorted(vehicle.visited)) if vehicle.visited else 'None'
            self.log(f"  Vehicle {vehicle.id}: ({pos.x},{pos.y}) slot={pos.slot} "
                    f"dir={pos.direction.name} visited=[{visited}]")
    
    def print_final_report(self):
        """Print final test report"""
        self.log("=" * 70)
        self.log("FINAL TEST REPORT", "REPORT")
        self.log("=" * 70)

        steps = self.test_results['steps']
        completed = self.vehicle_manager.completed_vehicles
        hours = steps * TIME_STEP_SECONDS / 3600
        throughput = completed / hours if hours > 0 else 0

        ss_steps = max(steps - WARMUP_STEPS, 0)
        ss_hours = ss_steps * TIME_STEP_SECONDS / 3600
        ss_completed = completed - self.test_results['warmup_completed']
        ss_throughput = ss_completed / ss_hours if ss_hours > 0 else 0

        self.log(f"Signal Strategy: {self.mock_infra.signal_strategy}")
        self.log(f"Total Steps:        {steps}  ({hours:.2f} hours simulated)")
        self.log(f"Completed Vehicles: {completed}")
        self.log(f"Active Vehicles:    {len(self.vehicle_manager.vehicles)}")
        self.log(f"Throughput (overall):      {throughput:.1f} vehicles/hour")
        self.log(f"Throughput (steady-state): {ss_throughput:.1f} vehicles/hour"
                 f"  (after {WARMUP_STEPS}-step warm-up)")
        self.log("")
        self.log("CONSTRAINT VIOLATIONS:")
        self.log(f"  Collisions: {self.test_results['collision']}")
        self.log(f"  Red Light Violations: {self.test_results['red_light']}")
        self.log(f"  Opposite Direction: {self.test_results['opposite_direction']}")
        self.log(f"  Total Violation Events: {self.test_results['total_violations']}")
        self.log("")

        if self.test_results['total_violations'] == 0:
            self.log("✓ ALL TESTS PASSED - NO VIOLATIONS DETECTED", "SUCCESS")
        else:
            self.log("✗ TEST FAILED - VIOLATIONS DETECTED", "FAILURE")

        self.log("=" * 70)

        return self.test_results['total_violations'] == 0


class VGroupStressTest:
    """Stress testing for V-Group"""
    
    def __init__(self):
        self.results = {}
    
    def run_all_strategies(self, steps: int = STEPS_PER_HOUR):
        """Test with all signal strategies"""
        strategies = ["random", "all_red", "cyclic", "smart", "adversarial"]
        
        print("\n" + "=" * 70)
        print("V-GROUP STRESS TEST - ALL STRATEGIES")
        print("=" * 70 + "\n")
        
        for strategy in strategies:
            print(f"\n{'='*70}")
            print(f"Testing Strategy: {strategy.upper()}")
            print('='*70)
            
            test = VGroupTestSuite(signal_strategy=strategy, verbose=False)
            test.run_test(num_steps=steps, spawn_rate=1.0)
            
            self.results[strategy] = test.test_results
        
        self.print_comparative_report()
    
    def print_comparative_report(self):
        """Print comparative report across all strategies"""
        print("\n" + "=" * 70)
        print("COMPARATIVE REPORT - ALL STRATEGIES")
        print("=" * 70)
        
        print(f"\n{'Strategy':<20} {'Steps':<10} {'Completed':<12} {'Veh/hr (SS)':<14} {'Violations':<12}")
        print("-" * 78)

        for strategy, results in self.results.items():
            steps = results['steps']
            completed = results.get('completed', 0)
            ss_steps = max(steps - WARMUP_STEPS, 0)
            ss_hours = ss_steps * TIME_STEP_SECONDS / 3600
            ss_completed = completed - results.get('warmup_completed', 0)
            ss_throughput = ss_completed / ss_hours if ss_hours > 0 else 0
            print(f"{strategy:<20} {steps:<10} {completed:<12} "
                  f"{ss_throughput:<14.1f} {results['total_violations']:<12}")
        
        print("\n" + "=" * 70)
        print("DETAILED VIOLATIONS BY TYPE")
        print("=" * 70)
        
        print(f"\n{'Strategy':<20} {'Collision':<12} {'Red Light':<12} {'Opposite Dir':<12}")
        print("-" * 70)
        
        for strategy, results in self.results.items():
            print(f"{strategy:<20} {results['collision']:<12} "
                  f"{results['red_light']:<12} "
                  f"{results['opposite_direction']:<12}")
        
        # Summary
        total_violations = sum(r['total_violations'] for r in self.results.values())
        passed_strategies = sum(1 for r in self.results.values() if r['total_violations'] == 0)
        
        print("\n" + "=" * 70)
        print(f"Strategies Passed: {passed_strategies}/{len(self.results)}")
        print(f"Total Violations: {total_violations}")
        
        if total_violations == 0:
            print("\n✓ ALL STRATEGIES PASSED - V-GROUP IS ROBUST")
        else:
            print("\n✗ SOME STRATEGIES FAILED - V-GROUP NEEDS IMPROVEMENT")
        
        print("=" * 70 + "\n")


class ScenarioTest:
    """Specific scenario testing"""
    
    @staticmethod
    def test_high_density():
        """Test with high vehicle density"""
        print("\n" + "=" * 70)
        print("SCENARIO TEST: HIGH DENSITY")
        print("=" * 70)
        
        test = VGroupTestSuite(signal_strategy="smart", verbose=True)
        test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)
    
    @staticmethod
    def test_adversarial():
        """Test with adversarial signals"""
        print("\n" + "=" * 70)
        print("SCENARIO TEST: ADVERSARIAL SIGNALS")
        print("=" * 70)
        
        test = VGroupTestSuite(signal_strategy="adversarial", verbose=True)
        test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)
    
    @staticmethod
    def test_all_red():
        """Test with all red signals (should vehicles wait?)"""
        print("\n" + "=" * 70)
        print("SCENARIO TEST: ALL RED SIGNALS")
        print("=" * 70)
        
        test = VGroupTestSuite(signal_strategy="all_red", verbose=True)
        test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)


def main():
    """Main test entry point"""
    
    print("\n" + "=" * 70)
    print("V-GROUP INDEPENDENT TEST SUITE")
    print("=" * 70)
    
    # Menu
    print("\nSelect test mode:")
    print("1. Single test with random signals")
    print("2. Single test with smart signals")
    print("3. Stress test (all strategies)")
    print("4. High density scenario")
    print("5. Adversarial scenario")
    print("6. All red signals scenario")
    print("7. Run all tests")
    
    choice = input("\nEnter choice (1-7): ").strip()
    
    if choice == "1":
        test = VGroupTestSuite(signal_strategy="random", verbose=True)
        test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)

    elif choice == "2":
        test = VGroupTestSuite(signal_strategy="smart", verbose=True)
        test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)

    elif choice == "3":
        stress = VGroupStressTest()
        stress.run_all_strategies()
    
    elif choice == "4":
        ScenarioTest.test_high_density()
    
    elif choice == "5":
        ScenarioTest.test_adversarial()
    
    elif choice == "6":
        ScenarioTest.test_all_red()
    
    elif choice == "7":
        print("\n" + "=" * 70)
        print("RUNNING ALL TESTS")
        print("=" * 70)
        
        # Run all scenarios
        for strategy in ["random", "smart"]:
            test = VGroupTestSuite(signal_strategy=strategy, verbose=False)
            test.run_test(num_steps=STEPS_PER_HOUR, spawn_rate=1.0)

        ScenarioTest.test_high_density()
        ScenarioTest.test_adversarial()

        stress = VGroupStressTest()
        stress.run_all_strategies()
    
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
