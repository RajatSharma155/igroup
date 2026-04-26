# v_group.py - Vehicle management software

import random
from typing import List, Dict, Set, Optional, Tuple
from common import *

class PathPlanner:
    """A* pathfinding for vehicles"""
    
    @staticmethod
    def heuristic(pos1: Tuple[int, int], pos2: Tuple[int, int]) -> int:
        return abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
    
    @staticmethod
    def find_path(start: Tuple[int, int], goals: Set[Tuple[int, int]], 
                  visited_goals: Set[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
        """Find the nearest unvisited goal"""
        remaining_goals = goals - visited_goals
        if not remaining_goals:
            return None
        
        # Simple greedy: choose nearest goal
        min_dist = float('inf')
        best_goal = None
        for goal in remaining_goals:
            dist = PathPlanner.heuristic(start, goal)
            if dist < min_dist:
                min_dist = dist
                best_goal = goal
        
        return best_goal

class VehicleManager:
    """Manages all vehicles in the system"""
    
    def __init__(self, max_vehicles: int = None):
        self.vehicles: Dict[int, Vehicle] = {}
        self.next_vehicle_id = 0
        self.max_vehicles = max_vehicles
        self.occupied_positions: Set[Position] = set()
        self.completed_vehicles = 0
        # Strategy E: pre-planned checkpoint order, alternating per vehicle ID.
        # Even IDs: B→C→D (counterclockwise outer ring).
        # Odd IDs:  D→C→B (clockwise outer ring).
        # Both orderings have the same total distance (244 slots), but alternating
        # directions distributes vehicles across opposite sides of the grid,
        # reducing segment congestion and signal contention.
        self._checkpoint_plans: Dict[int, List[str]] = {}

    def spawn_vehicle(self) -> Optional[Vehicle]:
        """Spawn a new vehicle at point A if possible"""
        if self.max_vehicles is not None and len(self.vehicles) >= self.max_vehicles:
            return None

        # Check if starting position is available
        start_pos = Position(-1, 0, 1, Direction.EAST)
        if start_pos in self.occupied_positions:
            return None
        
        vehicle = Vehicle(
            id=self.next_vehicle_id,
            position=start_pos,
            visited=set(),
            completed=False
        )
        self.vehicles[vehicle.id] = vehicle
        self.occupied_positions.add(start_pos)
        # Strategy E: assign alternating checkpoint order
        if vehicle.id % 2 == 0:
            self._checkpoint_plans[vehicle.id] = ['B', 'C', 'D']
        else:
            self._checkpoint_plans[vehicle.id] = ['D', 'C', 'B']
        self.next_vehicle_id += 1

        return vehicle
    
    # Sentinel returned by decide_vehicle_action when a vehicle completes its tour
    # by crossing back into Point A.  update_vehicles detects this and removes
    # the vehicle without ever storing this position on the vehicle object.
    COMPLETION_SENTINEL = Position(-1, 0, 0, Direction.WEST)

    def get_next_position(self, current: Position) -> Optional[Position]:
        """Advance one slot forward on the current road segment.
        Returns None when already at the last slot (crossing handled separately)."""
        next_slot = current.slot + 1
        max_slots = RoadNetwork.get_max_slots(current.x, current.y, current.direction)
        if next_slot <= max_slots:
            return Position(current.x, current.y, next_slot, current.direction)
        return None
    
    def is_position_occupied(self, pos: Position, exclude_vehicle_id: Optional[int] = None) -> bool:
        """Check if a road-segment slot is occupied by another vehicle."""
        for vid, vehicle in self.vehicles.items():
            if exclude_vehicle_id is not None and vid == exclude_vehicle_id:
                continue
            if vehicle.position == pos:
                return True
        return False
    
    def decide_vehicle_action(self, vehicle: Vehicle, infra_state: InfrastructureState) -> Optional[Position]:
        """Decide the next position for a vehicle.

        Vehicles never occupy an intersection node.  A vehicle at the last slot
        of a road segment either waits (red signal) or jumps in one step to
        slot 1 of the chosen exit road on the far side of the intersection.
        """
        current = vehicle.position

        # Determine target checkpoint
        # Strategy E: follow the pre-planned order (B→C→D or D→C→B) rather than
        # greedy nearest, guaranteeing an optimal route and distributing vehicles
        # across opposite sides of the grid.
        checkpoint_coords = {'B': (0, 2), 'C': (2, 2), 'D': (2, 0), 'A': (-1, 0)}
        if len(vehicle.visited) < 3:
            plan = self._checkpoint_plans.get(vehicle.id, ['B', 'C', 'D'])
            next_cp = next(cp for cp in plan if cp not in vehicle.visited)
            target_coord = checkpoint_coords[next_cp]
        else:
            target_coord = (-1, 0)

        max_slots = RoadNetwork.get_max_slots(current.x, current.y, current.direction)

        # Not at last slot: advance one slot on the current segment
        if current.slot < max_slots:
            next_pos = Position(current.x, current.y, current.slot + 1, current.direction)
            if self.is_position_occupied(next_pos, vehicle.id):
                return None
            return next_pos

        # At last slot: attempt to cross the upcoming intersection
        direction = current.direction
        if direction == Direction.EAST:
            dest_x, dest_y = current.x + 1, current.y
        elif direction == Direction.WEST:
            dest_x, dest_y = current.x - 1, current.y
        elif direction == Direction.SOUTH:
            dest_x, dest_y = current.x, current.y + 1
        else:  # NORTH
            dest_x, dest_y = current.x, current.y - 1

        # Check arrival-direction signal at the destination intersection
        signal_key = (dest_x, dest_y, direction)
        if signal_key in infra_state.signals:
            if infra_state.signals[signal_key] == SignalState.RED:
                return None  # Wait at last slot

        # Signal is green — special case: returning to Point A
        if (dest_x, dest_y) == (-1, 0):
            return self.COMPLETION_SENTINEL

        # Choose best exit road on the far side of the intersection.
        # Pick the exit with the shortest Manhattan distance to target.
        possible_exits = []
        for nx, ny, exit_dir in RoadNetwork.get_neighbors(dest_x, dest_y):
            if exit_dir == direction.opposite():
                continue  # No U-turn
            next_pos = Position(dest_x, dest_y, 1, exit_dir)
            if self.is_position_occupied(next_pos, vehicle.id):
                continue
            dist = PathPlanner.heuristic((nx, ny), target_coord)
            possible_exits.append((dist, next_pos))

        if not possible_exits:
            return None  # All exits blocked; wait

        possible_exits.sort(key=lambda e: e[0])
        return possible_exits[0][1]
    
    def update_vehicles(self, infra_state: InfrastructureState):
        """Update all vehicle positions."""

        new_positions: Dict[int, Position] = {}
        for vehicle_id, vehicle in self.vehicles.items():
            next_pos = self.decide_vehicle_action(vehicle, infra_state)
            if next_pos is not None:
                new_positions[vehicle_id] = next_pos

        # Resolve conflicts: only one vehicle may occupy any given road-segment slot.
        # The vehicle with the lowest ID wins; others stay put this step.
        destination_count: Dict[Position, List[int]] = {}
        for vid, pos in new_positions.items():
            if pos is self.COMPLETION_SENTINEL:
                continue  # Completions never conflict with road positions
            destination_count.setdefault(pos, []).append(vid)
        for pos, vids in destination_count.items():
            if len(vids) > 1:
                vids.sort()
                for vid in vids[1:]:
                    del new_positions[vid]

        # Apply movements and detect checkpoint crossings / tour completion
        checkpoint_coords = {'B': (0, 2), 'C': (2, 2), 'D': (2, 0)}
        vehicles_to_remove: List[int] = []

        for vehicle_id, next_pos in new_positions.items():
            vehicle = self.vehicles[vehicle_id]
            prev_pos = vehicle.position

            # Tour completion: vehicle crossed back into Point A
            if next_pos is self.COMPLETION_SENTINEL:
                vehicles_to_remove.append(vehicle_id)
                self.completed_vehicles += 1
                continue  # Don't update position; vehicle is removed below

            vehicle.position = next_pos

            # Detect intersection crossing: vehicle moved from last slot of one road
            # to slot 1 of the next road.  The crossed intersection is (next_pos.x, next_pos.y).
            prev_max = RoadNetwork.get_max_slots(prev_pos.x, prev_pos.y, prev_pos.direction)
            if prev_pos.slot == prev_max and next_pos.slot == 1:
                crossed = (next_pos.x, next_pos.y)
                for cp_name, cp_coord in checkpoint_coords.items():
                    if crossed == cp_coord:
                        vehicle.visited.add(cp_name)

        for vehicle_id in vehicles_to_remove:
            del self.vehicles[vehicle_id]
            self._checkpoint_plans.pop(vehicle_id, None)   # Strategy E: clean up

        self.occupied_positions = {v.position for v in self.vehicles.values()}
    
    def verify_constraints(self) -> Tuple[bool, str]:
        """Verify no two vehicles share the same road-segment slot."""
        positions = [v.position for v in self.vehicles.values()]
        if len(positions) != len(set(positions)):
            return False, "Collision detected on road segment"
        return True, "OK"

    def get_vehicle_states(self) -> List[VehicleState]:
        """Get current state of all vehicles for i-group."""
        return [VehicleState(id=v.id, position=v.position) for v in self.vehicles.values()]
