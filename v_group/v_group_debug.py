# v_group_debug.py - Debugging utilities for V-Group

from typing import List, Dict
from common import *
from v_group.v_group import VehicleManager
from v_group.v_group_test import MockInfrastructure, ConstraintVerifier

class VGroupDebugger:
    """Debugging tools for V-Group"""
    
    def __init__(self):
        self.vehicle_manager = VehicleManager(max_vehicles=5)
        self.mock_infra = MockInfrastructure(signal_strategy="random")
        self.history = []
    
    def trace_vehicle(self, steps: int = 50):
        """Trace a single vehicle's journey from spawn to completion"""

        # Spawn vehicle
        vehicle = self.vehicle_manager.spawn_vehicle()
        if not vehicle:
            print("Failed to spawn vehicle")
            return

        target_id = vehicle.id

        print(f"\n{'='*70}")
        print(f"TRACING VEHICLE {target_id}")
        print('='*70)

        for step in range(steps):
            # Find target vehicle
            target = self.vehicle_manager.vehicles.get(target_id)
            if not target:
                break

            vehicle_states = self.vehicle_manager.get_vehicle_states()
            infra_state = self.mock_infra.generate_signals(vehicle_states)

            # Print state before update
            pos = target.position
            visited = ','.join(sorted(target.visited)) if target.visited else 'None'

            # Get signal info: show signals at the intersection ahead if at last slot
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
            if pos.slot == max_slots:
                # At last slot, show signals for the upcoming intersection
                if pos.direction == Direction.EAST:
                    next_int = (pos.x + 1, pos.y)
                elif pos.direction == Direction.WEST:
                    next_int = (pos.x - 1, pos.y)
                elif pos.direction == Direction.SOUTH:
                    next_int = (pos.x, pos.y + 1)
                else:
                    next_int = (pos.x, pos.y - 1)
                sig = infra_state.signals.get((next_int[0], next_int[1], pos.direction), SignalState.RED)
                signal_str = f"{sig.name} at ({next_int[0]},{next_int[1]})"
            else:
                signal_str = "N/A (mid-segment)"

            print(f"\nStep {step}:")
            print(f"  Position: ({pos.x},{pos.y}) slot={pos.slot} dir={pos.direction.name}")
            print(f"  Visited: [{visited}]")
            print(f"  Signals: {signal_str}")

            # Update
            self.vehicle_manager.update_vehicles(infra_state)

            # Check if moved or completed
            new_target = self.vehicle_manager.vehicles.get(target_id)
            if not new_target:
                print(f"  → Completed tour at step {step}")
            elif new_target.position != pos:
                new_pos = new_target.position
                print(f"  → Moved to ({new_pos.x},{new_pos.y}) slot={new_pos.slot} dir={new_pos.direction.name}")
            else:
                print(f"  → Stayed (blocked or waiting)")
    
    def inspect_intersection(self, x: int, y: int, steps: int = 20):
        """Inspect activity at a specific intersection"""
        
        print(f"\n{'='*70}")
        print(f"INSPECTING INTERSECTION ({x}, {y})")
        print('='*70)
        
        # Spawn some vehicles
        for _ in range(3):
            self.vehicle_manager.spawn_vehicle()
        
        for step in range(steps):
            vehicle_states = self.vehicle_manager.get_vehicle_states()
            infra_state = self.mock_infra.generate_signals(vehicle_states)
            
            # Find vehicles approaching or departing this intersection
            nearby_vehicles = []
            for v in self.vehicle_manager.vehicles.values():
                pos = v.position
                max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
                # Vehicle on a segment originating from this intersection
                if pos.get_intersection() == (x, y):
                    if pos.slot <= 3:
                        nearby_vehicles.append((v, "DEPARTING"))
                # Vehicle approaching this intersection (at last slots of inbound segment)
                elif pos.slot > max_slots - 3:
                    if pos.direction == Direction.EAST and (pos.x + 1, pos.y) == (x, y):
                        nearby_vehicles.append((v, "APPROACHING"))
                    elif pos.direction == Direction.WEST and (pos.x - 1, pos.y) == (x, y):
                        nearby_vehicles.append((v, "APPROACHING"))
                    elif pos.direction == Direction.SOUTH and (pos.x, pos.y + 1) == (x, y):
                        nearby_vehicles.append((v, "APPROACHING"))
                    elif pos.direction == Direction.NORTH and (pos.x, pos.y - 1) == (x, y):
                        nearby_vehicles.append((v, "APPROACHING"))
            
            if nearby_vehicles or step % 5 == 0:
                print(f"\nStep {step}:")
                
                # Show signals (only valid arrival directions for this intersection)
                signals = []
                for direction in sorted(RoadNetwork.get_valid_arrival_directions(x, y), key=lambda d: d.value):
                    sig = infra_state.signals.get((x, y, direction), SignalState.RED)
                    signals.append(f"{direction.name}:{sig.name}")
                print(f"  Signals: {', '.join(signals)}")
                
                # Show vehicles
                if nearby_vehicles:
                    print(f"  Vehicles:")
                    for vehicle, status in nearby_vehicles:
                        pos = vehicle.position
                        print(f"    V{vehicle.id} {status}: slot={pos.slot} dir={pos.direction.name}")
                else:
                    print(f"  No vehicles nearby")
            
            self.vehicle_manager.update_vehicles(infra_state)
    
    def detect_deadlock(self, steps: int = 100, target_vehicles: int = 5) -> bool:
        """Detect if vehicles are deadlocked"""

        print(f"\n{'='*70}")
        print("DEADLOCK DETECTION TEST")
        print('='*70)

        stall_count = {}

        for step in range(steps):
            # Try to spawn until we have enough vehicles in the system
            if len(self.vehicle_manager.vehicles) < target_vehicles:
                self.vehicle_manager.spawn_vehicle()

            vehicle_states = self.vehicle_manager.get_vehicle_states()
            infra_state = self.mock_infra.generate_signals(vehicle_states)

            # Record positions before update
            prev_positions = {v.id: v.position for v in self.vehicle_manager.vehicles.values()}

            self.vehicle_manager.update_vehicles(infra_state)

            # Check if vehicles moved
            for v_id, prev_pos in prev_positions.items():
                if v_id not in self.vehicle_manager.vehicles:
                    stall_count.pop(v_id, None)
                    continue

                curr_pos = self.vehicle_manager.vehicles[v_id].position

                if curr_pos == prev_pos:
                    stall_count[v_id] = stall_count.get(v_id, 0) + 1
                else:
                    stall_count[v_id] = 0

                # Deadlock if vehicle hasn't moved in 20 steps
                if stall_count[v_id] > 20:
                    print(f"\n⚠ POTENTIAL DEADLOCK DETECTED!")
                    print(f"  Vehicle {v_id} hasn't moved for {stall_count[v_id]} steps")
                    print(f"  Position: ({curr_pos.x},{curr_pos.y}) slot={curr_pos.slot} dir={curr_pos.direction.name}")
                    return True

            if step % 20 == 0:
                print(f"\nStep {step}: {len(self.vehicle_manager.vehicles)} active vehicles")
                for v_id, count in stall_count.items():
                    if count > 5:
                        print(f"  Vehicle {v_id} stalled for {count} steps")

        print("\n✓ No deadlock detected")
        return False


def run_debug_tests():
    """Run all debug tests"""
    
    print("\n" + "=" * 70)
    print("V-GROUP DEBUG TEST SUITE")
    print("=" * 70)
    
    debugger = VGroupDebugger()
    
    # Test 1: Trace single vehicle
    print("\n### TEST 1: Vehicle Tracing ###")
    debugger.trace_vehicle(steps=30)
    
    # Test 2: Inspect intersection
    print("\n### TEST 2: Intersection Inspection ###")
    debugger = VGroupDebugger()  # Reset
    debugger.inspect_intersection(1, 1, steps=30)
    
    # Test 3: Deadlock detection
    print("\n### TEST 3: Deadlock Detection ###")
    debugger = VGroupDebugger()  # Reset
    debugger.mock_infra.signal_strategy = "all_red"  # Likely to cause stalls
    debugger.detect_deadlock(steps=50)


if __name__ == "__main__":
    run_debug_tests()
