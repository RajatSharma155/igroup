# v_group/v_group_viz.py - Animated visualization for V-Group test and debug tools

import random
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation
from matplotlib.gridspec import GridSpec
from typing import Dict, List, Optional, Set, Tuple
from common import *
from v_group.v_group import VehicleManager
from v_group.v_group_test import MockInfrastructure, ConstraintVerifier


# ---------------------------------------------------------------------------
# Shared drawing helpers
# ---------------------------------------------------------------------------

_SIGNAL_OFFSET = 0.18
_SIGNAL_RADIUS = 0.045
_DIR_OFFSETS = {
    Direction.NORTH: (0,  -_SIGNAL_OFFSET),
    Direction.SOUTH: (0,   _SIGNAL_OFFSET),
    Direction.EAST:  ( _SIGNAL_OFFSET, 0),
    Direction.WEST:  (-_SIGNAL_OFFSET, 0),
}
_CHECKPOINT_INTERSECTIONS = {(0, 2), (2, 2), (2, 0)}


def _vehicle_visual_pos(pos: Position) -> Tuple[float, float]:
    """Convert a road-segment Position to (x, y) plot coordinates."""
    max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
    frac = pos.slot / max_slots
    if pos.direction == Direction.EAST:
        return pos.x + frac, pos.y + 0.05
    elif pos.direction == Direction.WEST:
        return pos.x - frac, pos.y - 0.05
    elif pos.direction == Direction.SOUTH:
        return pos.x - 0.05, pos.y + frac
    else:  # NORTH
        return pos.x + 0.05, pos.y - frac


def _draw_network(ax, signals: Dict, highlight_intersection=None):
    """Draw the static road network: intersections, roads, and signal dots."""
    ax.clear()
    ax.set_xlim(-2, 4)
    ax.set_ylim(-1, 4)
    ax.set_aspect('equal')
    ax.invert_yaxis()

    # Intersections
    for x in range(3):
        for y in range(3):
            if (x, y) == highlight_intersection:
                color, zorder = '#ff8800', 5
            elif (x, y) in _CHECKPOINT_INTERSECTIONS:
                color, zorder = '#2255cc', 4
            else:
                color, zorder = 'black', 4
            ax.add_patch(plt.Circle((x, y), 0.1, color=color, fill=True, zorder=zorder))
            ax.text(x, y - 0.25, f"({x},{y})", ha='center', va='top',
                    fontsize=7, color='#444444')

    # Point A
    sq = 0.18
    ax.add_patch(patches.Rectangle(
        (-1 - sq, -sq), sq * 2, sq * 2,
        linewidth=1.5, edgecolor='#aa0000', facecolor='#ffcccc', zorder=4
    ))
    ax.text(-1, 0, "A", ha='center', va='center',
            fontsize=13, fontweight='bold', color='#aa0000', zorder=5)

    # Checkpoint labels
    for name, (x, y) in {'B': (0, 2), 'C': (2, 2), 'D': (2, 0)}.items():
        ax.text(x + 0.28, y - 0.28, name, ha='center', va='center',
                fontsize=13, fontweight='bold', color='white',
                bbox=dict(boxstyle='round,pad=0.2', facecolor='#2255cc',
                          edgecolor='none', alpha=0.85),
                zorder=5)

    # Roads
    for x in range(-1, 3):
        for y in range(3):
            if x == -1 and y != 0:
                continue
            for nx, ny, direction in RoadNetwork.get_neighbors(x, y):
                if x == -1 and direction != Direction.EAST:
                    continue
                kw = dict(head_width=0.05, head_length=0.05, fc='gray', ec='gray', alpha=0.5)
                if direction == Direction.EAST:
                    ax.arrow(x + 0.1, y + 0.05, nx - x - 0.2, 0, **kw)
                elif direction == Direction.WEST:
                    ax.arrow(x - 0.1, y - 0.05, nx - x + 0.2, 0, **kw)
                elif direction == Direction.SOUTH:
                    ax.arrow(x - 0.05, y + 0.1, 0, ny - y - 0.2, **kw)
                elif direction == Direction.NORTH:
                    ax.arrow(x + 0.05, y - 0.1, 0, ny - y + 0.2, **kw)

    # Signal dots
    for x in range(3):
        for y in range(3):
            for direction in RoadNetwork.get_valid_arrival_directions(x, y):
                dx, dy = _DIR_OFFSETS[direction]
                state = signals.get((x, y, direction), SignalState.RED)
                color = '#00dd00' if state == SignalState.GREEN else '#dd0000'
                ax.add_patch(plt.Circle((x + dx, y + dy), _SIGNAL_RADIUS,
                                        color=color, fill=True, zorder=5))


def _draw_vehicles(ax, vehicle_manager: VehicleManager,
                   traced_id: Optional[int] = None,
                   trail: Optional[List[Tuple[float, float]]] = None,
                   stall_counts: Optional[Dict[int, int]] = None,
                   violation_ids: Optional[Set[int]] = None):
    """Draw all vehicles; optionally draw a trail and apply stall/violation colours."""
    violation_ids = violation_ids or set()
    stall_counts = stall_counts or {}

    # Trail for traced vehicle
    if trail and len(trail) > 1:
        xs, ys = zip(*trail)
        ax.plot(xs, ys, '-', color='#8888ff', linewidth=1.2, alpha=0.45, zorder=3)
        # Fading dots along trail
        for i, (tx, ty) in enumerate(trail):
            alpha = 0.15 + 0.5 * (i / len(trail))
            ax.add_patch(plt.Circle((tx, ty), 0.03, color='#6666ff',
                                    alpha=alpha, zorder=3))

    for vehicle in vehicle_manager.vehicles.values():
        vx, vy = _vehicle_visual_pos(vehicle.position)

        if vehicle.id in violation_ids:
            color = '#ff0000'
        elif vehicle.id == traced_id:
            color = '#aa44ff'
        else:
            stall = stall_counts.get(vehicle.id, 0)
            if stall > 10:
                # Heat: orange → red as stall grows
                ratio = min(stall / 30, 1.0)
                r = int(255)
                g = int(165 * (1 - ratio))
                color = f'#{r:02x}{g:02x}00'
            elif len(vehicle.visited) == 3:
                color = '#22aa22'
            else:
                color = '#ff8c00'

        ax.add_patch(plt.Circle((vx, vy), 0.08, color=color, fill=True,
                                alpha=0.85, zorder=6))
        ax.text(vx, vy, str(vehicle.id), ha='center', va='center',
                fontsize=6, color='white', fontweight='bold', zorder=7)


# ---------------------------------------------------------------------------
# Test suite visualizer
# ---------------------------------------------------------------------------

class VGroupTestVisualizer:
    """Animated visualization of a VGroupTestSuite run with a side stats panel."""

    def __init__(self, signal_strategy: str = "smart", max_vehicles: int = None,
                 spawn_rate: float = 1.0):
        self.vehicle_manager = VehicleManager(max_vehicles=max_vehicles)
        self.mock_infra = MockInfrastructure(signal_strategy)
        self.verifier = ConstraintVerifier()
        self.spawn_rate = spawn_rate
        self._signals: Dict = {}
        self._step = 0
        self._stats = {'completed': 0, 'collisions': 0, 'red_lights': 0,
                       'opposite': 0, 'total_events': 0}
        self._recent_violations: List[str] = []

        self.fig = plt.figure(figsize=(15, 8))
        gs = GridSpec(1, 2, width_ratios=[3, 1], figure=self.fig,
                      left=0.04, right=0.97, wspace=0.05)
        self.ax_net = self.fig.add_subplot(gs[0])
        self.ax_info = self.fig.add_subplot(gs[1])
        self.ax_info.axis('off')

    def _draw_info(self, violations: Dict):
        self.ax_info.clear()
        self.ax_info.axis('off')

        lines = [
            f"Strategy: {self.mock_infra.signal_strategy}",
            f"Step:      {self._step}",
            f"Active:    {len(self.vehicle_manager.vehicles)}",
            f"Completed: {self.vehicle_manager.completed_vehicles}",
            "",
            "─── Cumulative ───",
            f"Collisions:  {self._stats['collisions']}",
            f"Red lights:  {self._stats['red_lights']}",
            f"Opp. dir:    {self._stats['opposite']}",
            f"Events:      {self._stats['total_events']}",
            "",
            "─── This step ───",
        ]
        if violations:
            for vtype, msgs in violations.items():
                for m in msgs:
                    lines.append(f"• {m[:36]}")
        else:
            lines.append("✓ No violations")

        # Keep only last 8 recent violation lines
        self._recent_violations = (self._recent_violations + lines[-8:])[-16:]

        status_color = '#ffeeee' if violations else '#eeffee'
        self.ax_info.text(
            0.05, 0.97, "\n".join(lines),
            transform=self.ax_info.transAxes,
            fontsize=8.5, va='top', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=status_color, alpha=0.9)
        )

    def _animate(self, frame):
        self._step = frame

        if random.random() < self.spawn_rate:
            self.vehicle_manager.spawn_vehicle()

        prev_positions = {v.id: v.position for v in self.vehicle_manager.vehicles.values()}
        prev_ids = set(self.vehicle_manager.vehicles.keys())

        vehicle_states = self.vehicle_manager.get_vehicle_states()
        infra_state = self.mock_infra.generate_signals(vehicle_states)
        self._signals = infra_state.signals

        self.vehicle_manager.update_vehicles(infra_state)

        completed_ids = prev_ids - set(self.vehicle_manager.vehicles.keys())

        all_ok, violations = self.verifier.verify_all(
            self.vehicle_manager, prev_positions, infra_state, completed_ids
        )
        if not all_ok:
            self._stats['total_events'] += 1
            self._stats['collisions'] += len(violations.get('collision', []))
            self._stats['red_lights'] += len(violations.get('red_light', []))
            self._stats['opposite'] += len(violations.get('opposite_direction', []))
        else:
            violations = {}

        _draw_network(self.ax_net, self._signals)
        _draw_vehicles(self.ax_net, self.vehicle_manager)
        self._draw_info(violations)
        self.ax_net.set_title(
            f"V-Group Test  |  strategy={self.mock_infra.signal_strategy}"
            f"  |  step={frame}  |  active={len(self.vehicle_manager.vehicles)}"
            f"  |  completed={self.vehicle_manager.completed_vehicles}",
            fontsize=10
        )

    def run(self, num_steps: int = 500, interval: int = 100):
        self._anim = FuncAnimation(self.fig, self._animate, frames=num_steps,
                                   interval=interval, repeat=False)
        plt.show()


# ---------------------------------------------------------------------------
# Debug visualizers
# ---------------------------------------------------------------------------

class VGroupTraceVisualizer:
    """Animate a single vehicle's journey with a fading trail."""

    def __init__(self, signal_strategy: str = "random"):
        self.vehicle_manager = VehicleManager(max_vehicles=1)
        self.mock_infra = MockInfrastructure(signal_strategy)
        self._signals: Dict = {}
        self._traced_id: Optional[int] = None
        self._trail: List[Tuple[float, float]] = []
        self._step = 0
        self._done = False

        self.fig, self.ax = plt.subplots(figsize=(10, 10))

    def _animate(self, frame):
        self._step = frame

        if self._done:
            return

        target = self.vehicle_manager.vehicles.get(self._traced_id)
        if not target:
            self._done = True
            _draw_network(self.ax, self._signals)
            self.ax.set_title(
                f"Vehicle {self._traced_id} completed tour at step {frame}",
                fontsize=11, color='green'
            )
            return

        vehicle_states = self.vehicle_manager.get_vehicle_states()
        infra_state = self.mock_infra.generate_signals(vehicle_states)
        self._signals = infra_state.signals

        # Record position before move
        self._trail.append(_vehicle_visual_pos(target.position))

        self.vehicle_manager.update_vehicles(infra_state)

        _draw_network(self.ax, self._signals)
        _draw_vehicles(self.ax, self.vehicle_manager,
                       traced_id=self._traced_id, trail=self._trail)

        # Signal annotation for the vehicle
        target = self.vehicle_manager.vehicles.get(self._traced_id)
        if target:
            pos = target.position
            visited = ', '.join(sorted(target.visited)) if target.visited else 'none'
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
            if pos.slot == max_slots:
                if pos.direction == Direction.EAST:
                    ni = (pos.x + 1, pos.y)
                elif pos.direction == Direction.WEST:
                    ni = (pos.x - 1, pos.y)
                elif pos.direction == Direction.SOUTH:
                    ni = (pos.x, pos.y + 1)
                else:
                    ni = (pos.x, pos.y - 1)
                sig = infra_state.signals.get((ni[0], ni[1], pos.direction), SignalState.RED)
                sig_str = f"signal: {sig.name} at {ni}"
            else:
                sig_str = "mid-segment"

            self.ax.set_title(
                f"Tracing V{self._traced_id}  |  step={frame}"
                f"  |  ({pos.x},{pos.y}) slot={pos.slot} {pos.direction.name}"
                f"  |  visited=[{visited}]  |  {sig_str}",
                fontsize=9
            )

    def run(self, steps: int = 350, interval: int = 80):
        vehicle = self.vehicle_manager.spawn_vehicle()
        if not vehicle:
            print("Failed to spawn vehicle")
            return
        self._traced_id = vehicle.id
        self._anim = FuncAnimation(self.fig, self._animate, frames=steps,
                                   interval=interval, repeat=False)
        plt.tight_layout()
        plt.show()


class VGroupInspectVisualizer:
    """Animate intersection activity with the target intersection highlighted."""

    def __init__(self, x: int, y: int, signal_strategy: str = "random",
                 max_vehicles: int = 8, spawn_rate: float = 0.3):
        self.xi = x
        self.yi = y
        self.vehicle_manager = VehicleManager(max_vehicles=max_vehicles)
        self.mock_infra = MockInfrastructure(signal_strategy)
        self.spawn_rate = spawn_rate
        self._signals: Dict = {}
        self._step = 0

        self.fig, self.ax = plt.subplots(figsize=(10, 10))

    def _animate(self, frame):
        self._step = frame

        if random.random() < self.spawn_rate:
            self.vehicle_manager.spawn_vehicle()

        vehicle_states = self.vehicle_manager.get_vehicle_states()
        infra_state = self.mock_infra.generate_signals(vehicle_states)
        self._signals = infra_state.signals

        self.vehicle_manager.update_vehicles(infra_state)

        _draw_network(self.ax, self._signals,
                      highlight_intersection=(self.xi, self.yi))
        _draw_vehicles(self.ax, self.vehicle_manager)

        # Label vehicles near the highlighted intersection
        for v in self.vehicle_manager.vehicles.values():
            pos = v.position
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)
            approaching = (
                pos.slot > max_slots - 3 and (
                    (pos.direction == Direction.EAST  and (pos.x + 1, pos.y) == (self.xi, self.yi)) or
                    (pos.direction == Direction.WEST  and (pos.x - 1, pos.y) == (self.xi, self.yi)) or
                    (pos.direction == Direction.SOUTH and (pos.x, pos.y + 1) == (self.xi, self.yi)) or
                    (pos.direction == Direction.NORTH and (pos.x, pos.y - 1) == (self.xi, self.yi))
                )
            )
            departing = (pos.get_intersection() == (self.xi, self.yi) and pos.slot <= 3)
            if approaching or departing:
                vx, vy = _vehicle_visual_pos(pos)
                label = "APR" if approaching else "DEP"
                self.ax.annotate(
                    label, (vx, vy),
                    xytext=(vx, vy - 0.18),
                    fontsize=6, color='#cc5500', ha='center',
                    arrowprops=dict(arrowstyle='-', color='#cc5500', lw=0.8),
                    zorder=8
                )

        # Signal state box near the highlighted intersection
        sig_lines = []
        for d in sorted(RoadNetwork.get_valid_arrival_directions(self.xi, self.yi),
                        key=lambda d: d.value):
            state = infra_state.signals.get((self.xi, self.yi, d), SignalState.RED)
            mark = "●" if state == SignalState.GREEN else "○"
            sig_lines.append(f"{mark} {d.name}: {state.name}")
        self.ax.text(
            self.xi, self.yi + 0.5,
            "\n".join(sig_lines),
            ha='center', va='bottom', fontsize=7.5,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#ffffcc',
                      edgecolor='#999900', alpha=0.92),
            zorder=9
        )

        self.ax.set_title(
            f"Inspecting ({self.xi},{self.yi})  |  strategy={self.mock_infra.signal_strategy}"
            f"  |  step={frame}  |  active={len(self.vehicle_manager.vehicles)}"
            f"  |  completed={self.vehicle_manager.completed_vehicles}",
            fontsize=9
        )

    def run(self, steps: int = 300, interval: int = 100):
        self._anim = FuncAnimation(self.fig, self._animate, frames=steps,
                                   interval=interval, repeat=False)
        plt.tight_layout()
        plt.show()


class VGroupDeadlockVisualizer:
    """Animate deadlock detection; vehicles heat up (orange→red) as stall grows."""

    def __init__(self, signal_strategy: str = "all_red", target_vehicles: int = 5):
        self.vehicle_manager = VehicleManager(max_vehicles=target_vehicles)
        self.mock_infra = MockInfrastructure(signal_strategy)
        self.target_vehicles = target_vehicles
        self._signals: Dict = {}
        self._stall: Dict[int, int] = {}
        self._step = 0
        self._deadlock_vid: Optional[int] = None

        self.fig, self.ax = plt.subplots(figsize=(10, 10))

    def _animate(self, frame):
        self._step = frame

        if len(self.vehicle_manager.vehicles) < self.target_vehicles:
            self.vehicle_manager.spawn_vehicle()

        vehicle_states = self.vehicle_manager.get_vehicle_states()
        infra_state = self.mock_infra.generate_signals(vehicle_states)
        self._signals = infra_state.signals

        prev = {v.id: v.position for v in self.vehicle_manager.vehicles.values()}
        self.vehicle_manager.update_vehicles(infra_state)

        # Update stall counts
        for vid, prev_pos in prev.items():
            if vid not in self.vehicle_manager.vehicles:
                self._stall.pop(vid, None)
                continue
            if self.vehicle_manager.vehicles[vid].position == prev_pos:
                self._stall[vid] = self._stall.get(vid, 0) + 1
            else:
                self._stall[vid] = 0
            if self._stall[vid] > 20 and self._deadlock_vid is None:
                self._deadlock_vid = vid

        _draw_network(self.ax, self._signals)
        _draw_vehicles(self.ax, self.vehicle_manager, stall_counts=self._stall)

        # Annotate max-stall vehicle
        if self._deadlock_vid and self._deadlock_vid in self.vehicle_manager.vehicles:
            vx, vy = _vehicle_visual_pos(
                self.vehicle_manager.vehicles[self._deadlock_vid].position
            )
            self.ax.annotate(
                f"STALL {self._stall[self._deadlock_vid]}",
                (vx, vy), xytext=(vx + 0.3, vy - 0.3),
                fontsize=8, color='red', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='red'), zorder=9
            )

        max_stall = max(self._stall.values(), default=0)
        status = f"⚠ DEADLOCK V{self._deadlock_vid}" if self._deadlock_vid else "monitoring..."
        self.ax.set_title(
            f"Deadlock Detection  |  strategy={self.mock_infra.signal_strategy}"
            f"  |  step={frame}  |  active={len(self.vehicle_manager.vehicles)}"
            f"  |  max stall={max_stall}  |  {status}",
            fontsize=9
        )

    def run(self, steps: int = 150, interval: int = 120):
        self._anim = FuncAnimation(self.fig, self._animate, frames=steps,
                                   interval=interval, repeat=False)
        plt.tight_layout()
        plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("\nV-Group Visualization")
    print("=" * 40)
    print("Test suite (spawn_rate=1.0, 1800 steps):")
    print("  1. Random signals")
    print("  2. Smart signals")
    print("  3. Adversarial signals")
    print("  4. All red signals")
    print("")
    print("Debug visualizers:")
    print("  5. Trace single vehicle")
    print("  6. Inspect intersection (1,1)")
    print("  7. Deadlock detection (all-red signals)")

    choice = input("\nEnter choice (1-7): ").strip()

    if choice == "1":
        VGroupTestVisualizer(signal_strategy="random", spawn_rate=1.0).run(num_steps=STEPS_PER_HOUR)
    elif choice == "2":
        VGroupTestVisualizer(signal_strategy="smart", spawn_rate=1.0).run(num_steps=STEPS_PER_HOUR)
    elif choice == "3":
        VGroupTestVisualizer(signal_strategy="adversarial", spawn_rate=1.0).run(num_steps=STEPS_PER_HOUR)
    elif choice == "4":
        VGroupTestVisualizer(signal_strategy="all_red", spawn_rate=1.0).run(num_steps=STEPS_PER_HOUR)
    elif choice == "5":
        VGroupTraceVisualizer(signal_strategy="random").run(steps=350)
    elif choice == "6":
        VGroupInspectVisualizer(1, 1, signal_strategy="random").run(steps=300)
    elif choice == "7":
        VGroupDeadlockVisualizer(signal_strategy="all_red").run(steps=150)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
