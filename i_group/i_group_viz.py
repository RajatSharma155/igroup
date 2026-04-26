# i_group/i_group_viz.py - Animated visualization for I-Group test suite
#
# Shows the real InfrastructureManager's signal decisions side-by-side with
# MockVehicleManager traffic.  Violation mode vehicles are highlighted red;
# the right panel tracks both the i-group's internal violation report and
# the independent constraint verifier's cumulative counts.
#
# Run:  python -m i_group.i_group_viz

import re
import random
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation
from matplotlib.gridspec import GridSpec
from typing import Dict, List, Optional, Set, Tuple

from common import *
from i_group.i_group import InfrastructureManager
from i_group.i_group_test import MockVehicleManager, IGroupConstraintVerifier


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

_SIGNAL_OFFSET = 0.18
_SIGNAL_RADIUS = 0.045
_DIR_OFFSETS = {
    Direction.NORTH: (0,   -_SIGNAL_OFFSET),
    Direction.SOUTH: (0,    _SIGNAL_OFFSET),
    Direction.EAST:  ( _SIGNAL_OFFSET, 0),
    Direction.WEST:  (-_SIGNAL_OFFSET, 0),
}
_CHECKPOINT_INTERSECTIONS = {(0, 2), (2, 2), (2, 0)}


def _vehicle_visual_pos(pos: Position) -> Tuple[float, float]:
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


def _draw_network(ax, signals: Dict):
    """Draw road network, intersections, and i-group signal dots."""
    ax.clear()
    ax.set_xlim(-2, 4)
    ax.set_ylim(-1, 4)
    ax.set_aspect('equal')
    ax.invert_yaxis()

    # Intersections
    for x in range(3):
        for y in range(3):
            color = '#2255cc' if (x, y) in _CHECKPOINT_INTERSECTIONS else 'black'
            ax.add_patch(plt.Circle((x, y), 0.1, color=color, fill=True, zorder=4))
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
                          edgecolor='none', alpha=0.85), zorder=5)

    # Roads
    for x in range(-1, 3):
        for y in range(3):
            if x == -1 and y != 0:
                continue
            for nx, ny, direction in RoadNetwork.get_neighbors(x, y):
                if x == -1 and direction != Direction.EAST:
                    continue
                kw = dict(head_width=0.05, head_length=0.05,
                          fc='gray', ec='gray', alpha=0.5)
                if direction == Direction.EAST:
                    ax.arrow(x + 0.1, y + 0.05, nx - x - 0.2, 0, **kw)
                elif direction == Direction.WEST:
                    ax.arrow(x - 0.1, y - 0.05, nx - x + 0.2, 0, **kw)
                elif direction == Direction.SOUTH:
                    ax.arrow(x - 0.05, y + 0.1, 0, ny - y - 0.2, **kw)
                elif direction == Direction.NORTH:
                    ax.arrow(x + 0.05, y - 0.1, 0, ny - y + 0.2, **kw)

    # Signal dots — all intersections managed by InfrastructureManager,
    # including (-1,0) = Point A for WEST-arriving (returning) vehicles.
    for x in range(-1, 3):
        for y in range(3):
            if x == -1 and y != 0:
                continue
            for direction in RoadNetwork.get_valid_arrival_directions(x, y):
                ox, oy = _DIR_OFFSETS[direction]
                state = signals.get((x, y, direction), SignalState.RED)
                color = '#00dd00' if state == SignalState.GREEN else '#dd0000'
                ax.add_patch(plt.Circle((x + ox, y + oy), _SIGNAL_RADIUS,
                                        color=color, fill=True, zorder=5))


def _draw_mock_vehicles(ax, vm: MockVehicleManager,
                        violation_ids: Optional[Set[int]] = None):
    """Draw MockVehicleManager vehicles; highlight violators in red."""
    violation_ids = violation_ids or set()
    for v in vm.vehicles.values():
        vx, vy = _vehicle_visual_pos(v.position)

        if v.id in violation_ids:
            color = '#ee2020'
        elif len(v.visited) == 3:
            color = '#22aa22'
        else:
            color = '#ff8c00'

        ax.add_patch(plt.Circle((vx, vy), 0.08, color=color, fill=True,
                                alpha=0.85, zorder=6))
        ax.text(vx, vy, str(v.id), ha='center', va='center',
                fontsize=6, color='white', fontweight='bold', zorder=7)

        # Checkpoint progress (e.g. "BC") below vehicle circle
        visited_str = ''.join(sorted(v.visited)) or '·'
        ax.text(vx, vy - 0.14, visited_str, ha='center', va='top',
                fontsize=5, color='#333333', zorder=7)


def _extract_vehicle_ids(messages: List[str]) -> Set[int]:
    """Pull vehicle IDs (V<n>) from violation message strings."""
    ids: Set[int] = set()
    for m in messages:
        for match in re.finditer(r'V(\d+)', m):
            ids.add(int(match.group(1)))
    return ids


# ---------------------------------------------------------------------------
# Main visualizer
# ---------------------------------------------------------------------------

class IGroupTestVisualizer:
    """Animated visualization of IGroupTestSuite.

    Left panel : road network with real i-group signal states + mock vehicles.
    Right panel: live stats panel —
                   • I-Group internal violation report (from InfrastructureManager)
                   • Independent constraint-verifier cumulative counts
                   • Recent violation messages

    Parameters
    ----------
    violation_mode : "none" | "red_light" | "uturn" | "wrong_lane" | "all"
    violation_rate : probability per eligible decision of injecting a violation
    """

    def __init__(self, max_vehicles: int = None, spawn_rate: float = 0.4,
                 violation_mode: str = "none", violation_rate: float = 0.1):
        self.vm = MockVehicleManager(max_vehicles,
                                     violation_mode=violation_mode,
                                     violation_rate=violation_rate)
        self.infra = InfrastructureManager()
        self.verifier = IGroupConstraintVerifier()
        self.spawn_rate = spawn_rate

        self._signals: Dict = {}
        self._step = 0

        # Cumulative verifier counts (independent of i-group internal report)
        self._cv_signal_inv = 0
        self._cv_collision  = 0
        self._cv_red_light  = 0
        self._cv_opposite   = 0
        self._cv_total      = 0

        # Rolling recent violation messages for the stats panel
        self._recent: List[str] = []

        self.fig = plt.figure(figsize=(16, 8))
        gs = GridSpec(1, 2, width_ratios=[3, 1], figure=self.fig,
                      left=0.04, right=0.97, wspace=0.05)
        self.ax_net  = self.fig.add_subplot(gs[0])
        self.ax_info = self.fig.add_subplot(gs[1])
        self.ax_info.axis('off')

    # ------------------------------------------------------------------
    # Stats panel
    # ------------------------------------------------------------------

    def _draw_info(self, violations: Dict):
        self.ax_info.clear()
        self.ax_info.axis('off')

        igr = self.infra.get_violation_report()
        mode = self.vm.violation_mode
        rate_str = f"  rate={self.vm.violation_rate:.0%}" if mode != "none" else ""

        lines = [
            "I-GROUP TEST",
            f"mode: {mode}{rate_str}",
            f"step:      {self._step}",
            f"active:    {len(self.vm.vehicles)}",
            f"completed: {self.vm.completed}",
            "",
            "── I-Group Report ──",
            f"collision:  {igr['collision']}",
            f"red light:  {igr['red_light']}",
            f"u-turn:     {igr['uturn']}",
            f"wrong lane: {igr['wrong_lane']}",
            f"total:      {igr['total']}",
            "",
            "── Verifier (cum.) ──",
            f"sig. inv:   {self._cv_signal_inv}",
            f"collision:  {self._cv_collision}",
            f"red light:  {self._cv_red_light}",
            f"opp. dir:   {self._cv_opposite}",
            f"events:     {self._cv_total}",
        ]

        if self._recent:
            lines += ["", "── Recent events ──"]
            lines += [f"• {m}" for m in self._recent[-6:]]
        else:
            lines += ["", "✓ No violations yet"]

        bg = '#ffeeee' if violations else '#eeffee'
        self.ax_info.text(
            0.05, 0.98, "\n".join(lines),
            transform=self.ax_info.transAxes,
            fontsize=8.5, va='top', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.5', facecolor=bg, alpha=0.92)
        )

    # ------------------------------------------------------------------
    # Animation loop
    # ------------------------------------------------------------------

    def _animate(self, frame):
        self._step = frame

        # Spawn
        if random.random() < self.spawn_rate:
            self.vm.spawn_vehicle()

        # Snapshot for violation detection
        prev_positions = {v.id: v.position for v in self.vm.vehicles.values()}
        prev_ids = set(self.vm.vehicles.keys())

        # I-Group computes signals
        vehicle_states = self.vm.get_vehicle_states()
        infra_state = self.infra.process_vehicle_states(vehicle_states)
        self._signals = infra_state.signals

        # Vehicles move
        self.vm.update(infra_state)
        completed_ids = prev_ids - set(self.vm.vehicles.keys())

        # Verify all constraints
        all_ok, violations = self.verifier.verify_all(
            self.vm, prev_positions, infra_state, completed_ids
        )

        violation_ids: Set[int] = set()
        if not all_ok:
            self._cv_total      += 1
            self._cv_signal_inv += len(violations.get('signal_invariant', []))
            self._cv_collision  += len(violations.get('collision', []))
            self._cv_red_light  += len(violations.get('red_light', []))
            self._cv_opposite   += len(violations.get('opposite_direction', []))

            all_msgs: List[str] = []
            for msgs in violations.values():
                all_msgs.extend(msgs)
            violation_ids = _extract_vehicle_ids(all_msgs)
            self._recent.extend(m[:42] for m in all_msgs)
            self._recent = self._recent[-12:]
        else:
            violations = {}

        # Draw
        _draw_network(self.ax_net, self._signals)
        _draw_mock_vehicles(self.ax_net, self.vm, violation_ids)
        self._draw_info(violations)

        mode_label = f"  |  mode={self.vm.violation_mode}" if self.vm.violation_mode != "none" else ""
        igr_total = self.infra.get_violation_report()['total']
        self.ax_net.set_title(
            f"I-Group Test{mode_label}"
            f"  |  step={frame}"
            f"  |  active={len(self.vm.vehicles)}"
            f"  |  completed={self.vm.completed}"
            f"  |  i-group detected={igr_total}",
            fontsize=10
        )

    def run(self, num_steps: int = 500, interval: int = 100):
        self._anim = FuncAnimation(self.fig, self._animate,
                                   frames=num_steps, interval=interval,
                                   repeat=False)
        plt.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print("\nI-Group Visualization")
    print("=" * 44)
    print("Law-abiding traffic:")
    print("  1. Low density    (spawn_rate=0.2)")
    print("  2. Medium density (spawn_rate=0.4)")
    print("  3. High density   (spawn_rate=0.8)")
    print("")
    print("Violation modes (spawn_rate=0.4, 20% rate):")
    print("  4. Red-light violations")
    print("  5. U-turn violations")
    print("  6. Wrong-lane (backward) violations")
    print("  7. All violations combined")

    choice = input("\nEnter choice (1-7): ").strip()

    if choice == "1":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.2,
                             violation_mode="none").run(num_steps=STEPS_PER_HOUR)
    elif choice == "2":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.4,
                             violation_mode="none").run(num_steps=STEPS_PER_HOUR)
    elif choice == "3":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.8,
                             violation_mode="none").run(num_steps=STEPS_PER_HOUR)
    elif choice == "4":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.4,
                             violation_mode="red_light",
                             violation_rate=0.2).run(num_steps=STEPS_PER_HOUR)
    elif choice == "5":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.4,
                             violation_mode="uturn",
                             violation_rate=0.2).run(num_steps=STEPS_PER_HOUR)
    elif choice == "6":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.4,
                             violation_mode="wrong_lane",
                             violation_rate=0.2).run(num_steps=STEPS_PER_HOUR)
    elif choice == "7":
        IGroupTestVisualizer(max_vehicles=None, spawn_rate=0.4,
                             violation_mode="all",
                             violation_rate=0.2).run(num_steps=STEPS_PER_HOUR)
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()
