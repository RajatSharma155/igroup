# common.py - Shared definitions and utilities

from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional, Set, List

# ---------------------------------------------------------------------------
# Physical scale constants
# ---------------------------------------------------------------------------
# One simulation time step = 2 seconds of real time.
# Adjacent intersections are 0.5 miles apart (normal road segments, 30 slots).
# Point A to intersection (0,0) is 1/30 mile (entry segment, 2 slots).
# All slots are therefore 1/60 mile = 88 ft long.
# Vehicles advance one slot per step → speed = 30 mph.

TIME_STEP_SECONDS           = 2.0          # seconds per simulation step
INTERSECTION_SPACING_MILES  = 0.5          # miles between adjacent intersections
ENTRY_SEGMENT_MILES         = 1 / 30       # miles, A ↔ (0,0)
SLOT_LENGTH_MILES           = INTERSECTION_SPACING_MILES / 30  # 1/60 mi ≈ 88 ft
VEHICLE_SPEED_MPH           = (SLOT_LENGTH_MILES / TIME_STEP_SECONDS) * 3600  # 30 mph
STEPS_PER_HOUR              = int(3600 / TIME_STEP_SECONDS)    # 1800 steps = 1 hour
WARMUP_STEPS                = 300   # steps before steady-state (~10 min, ≥ min tour length)

class Direction(Enum):
    NORTH = 0  # Moving up (decreasing y)
    SOUTH = 1  # Moving down (increasing y)
    EAST = 2   # Moving right (increasing x)
    WEST = 3   # Moving left (decreasing x)
    
    def opposite(self):
        return {
            Direction.NORTH: Direction.SOUTH,
            Direction.SOUTH: Direction.NORTH,
            Direction.EAST: Direction.WEST,
            Direction.WEST: Direction.EAST
        }[self]

class SignalState(Enum):
    RED = 0
    GREEN = 1

@dataclass(frozen=True)
class Position:
    """Represents a position on the road network"""
    x: int  # Intersection x coordinate (0-2) or -1 for point A
    y: int  # Intersection y coordinate (0-2) or 0 for point A
    slot: int  # Slot number from the intersection
    direction: Direction
    
    def __hash__(self):
        return hash((self.x, self.y, self.slot, self.direction))
    
    def get_intersection(self) -> Tuple[int, int]:
        """Returns the source intersection coordinates for this road segment position"""
        return (self.x, self.y)

@dataclass
class Vehicle:
    id: int
    position: Position
    visited: Set[str]  # Set of checkpoint names visited
    completed: bool = False
    
    def needs_to_visit(self) -> Set[str]:
        checkpoints = {'B', 'C', 'D'}
        return checkpoints - self.visited

class RoadNetwork:
    """Defines the road network structure"""
    
    # Checkpoint locations
    CHECKPOINTS = {
        'A': (-1, 0),  # Start/End point
        'B': (0, 2),
        'C': (2, 2),
        'D': (2, 0)
    }
    
    # Road segments: (from_intersection, to_intersection, direction, slots)
    SEGMENTS = [
        # From A to Intersection-0,0
        ((-1, 0), (0, 0), Direction.EAST, 2),
        ((0, 0), (-1, 0), Direction.WEST, 2),
        
        # Row 0
        ((0, 0), (1, 0), Direction.EAST, 30),
        ((1, 0), (0, 0), Direction.WEST, 30),
        ((1, 0), (2, 0), Direction.EAST, 30),
        ((2, 0), (1, 0), Direction.WEST, 30),
        
        # Row 1
        ((0, 1), (1, 1), Direction.EAST, 30),
        ((1, 1), (0, 1), Direction.WEST, 30),
        ((1, 1), (2, 1), Direction.EAST, 30),
        ((2, 1), (1, 1), Direction.WEST, 30),
        
        # Row 2
        ((0, 2), (1, 2), Direction.EAST, 30),
        ((1, 2), (0, 2), Direction.WEST, 30),
        ((1, 2), (2, 2), Direction.EAST, 30),
        ((2, 2), (1, 2), Direction.WEST, 30),
        
        # Column 0
        ((0, 0), (0, 1), Direction.SOUTH, 30),
        ((0, 1), (0, 0), Direction.NORTH, 30),
        ((0, 1), (0, 2), Direction.SOUTH, 30),
        ((0, 2), (0, 1), Direction.NORTH, 30),
        
        # Column 1
        ((1, 0), (1, 1), Direction.SOUTH, 30),
        ((1, 1), (1, 0), Direction.NORTH, 30),
        ((1, 1), (1, 2), Direction.SOUTH, 30),
        ((1, 2), (1, 1), Direction.NORTH, 30),
        
        # Column 2
        ((2, 0), (2, 1), Direction.SOUTH, 30),
        ((2, 1), (2, 0), Direction.NORTH, 30),
        ((2, 1), (2, 2), Direction.SOUTH, 30),
        ((2, 2), (2, 1), Direction.NORTH, 30),
    ]
    
    @staticmethod
    def get_neighbors(x: int, y: int) -> List[Tuple[int, int, Direction]]:
        """Get neighboring intersections and the direction to reach them"""
        neighbors = []
        
        # East
        if x < 2:
            neighbors.append((x + 1, y, Direction.EAST))
        
        # West — road to A (-1,0) only exists from (0,0); other x=0 rows have no westward road
        if x > 0 or (x == 0 and y == 0):
            neighbors.append((x - 1, y, Direction.WEST))
        
        # South
        if y < 2:
            neighbors.append((x, y + 1, Direction.SOUTH))
        
        # North
        if y > 0:
            neighbors.append((x, y - 1, Direction.NORTH))
        
        return neighbors
    
    @staticmethod
    def get_valid_arrival_directions(x: int, y: int) -> Set[Direction]:
        """Directions from which vehicles can arrive at intersection (x, y).

        A direction d is a valid arrival iff there is a road from some
        neighbor into (x,y) traveling in direction d, i.e. it is the
        opposite of a valid exit direction.
        """
        exit_dirs = {d for _, _, d in RoadNetwork.get_neighbors(x, y)}
        return {d.opposite() for d in exit_dirs}

    @staticmethod
    def get_max_slots(x: int, y: int, direction: Direction) -> int:
        """Get the number of slots for a road segment"""
        # Special case for the 2-slot segments connecting Point A to intersection (0,0)
        if x == -1 or (x == 0 and y == 0 and direction == Direction.WEST):
            return 2
        return 30

@dataclass
class VehicleState:
    """Vehicle state information sent from v-group to i-group"""
    id: int
    position: Position
    intended_direction: Optional['Direction'] = None  # Desired exit direction at current intersection
    
@dataclass
class InfrastructureState:
    """Infrastructure state sent from i-group to v-group"""
    signals: dict  # {(x, y, direction): SignalState}
    time_step: int
