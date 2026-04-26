# visualization.py - Optional visualization of the road network

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.animation import FuncAnimation
from common import *
from simulation import Simulation

class Visualizer:
    """Visualize the road network and vehicles"""
    
    def __init__(self, simulation: Simulation):
        self.sim = simulation
        self.fig, self.ax = plt.subplots(figsize=(12, 12))
        self._signals = {}
        
    def draw_network(self):
        """Draw the road network"""
        self.ax.clear()
        self.ax.set_xlim(-2, 4)
        self.ax.set_ylim(-1, 4)
        self.ax.set_aspect('equal')
        self.ax.invert_yaxis()
        
        # Draw intersections
        checkpoint_intersections = {(0, 2), (2, 2), (2, 0)}
        for x in range(3):
            for y in range(3):
                color = '#2255cc' if (x, y) in checkpoint_intersections else 'black'
                circle = plt.Circle((x, y), 0.1, color=color, fill=True, zorder=4)
                self.ax.add_patch(circle)
                self.ax.text(x, y - 0.25, f"({x},{y})", ha='center', va='top',
                             fontsize=7, color='#444444')

        # Draw point A as a square (spawn/destination)
        sq_half = 0.18
        rect = patches.Rectangle(
            (-1 - sq_half, 0 - sq_half), sq_half * 2, sq_half * 2,
            linewidth=1.5, edgecolor='#aa0000', facecolor='#ffcccc', zorder=4
        )
        self.ax.add_patch(rect)
        self.ax.text(-1, 0, "A", ha='center', va='center',
                     fontsize=13, fontweight='bold', color='#aa0000', zorder=5)

        # Draw checkpoint labels with a filled background box for visibility
        checkpoint_labels = {'B': (0, 2), 'C': (2, 2), 'D': (2, 0)}
        for name, (x, y) in checkpoint_labels.items():
            self.ax.text(x + 0.28, y - 0.28, name, ha='center', va='center',
                         fontsize=13, fontweight='bold', color='white',
                         bbox=dict(boxstyle='round,pad=0.2', facecolor='#2255cc',
                                   edgecolor='none', alpha=0.85),
                         zorder=5)
        
        # Draw roads
        for x in range(-1, 3):
            for y in range(3):
                if x == -1 and y != 0:
                    continue
                for nx, ny, direction in RoadNetwork.get_neighbors(x, y):
                    # Point A (-1,0) only has an eastward road; skip any other direction
                    if x == -1 and direction != Direction.EAST:
                        continue
                    kw = dict(head_width=0.05, head_length=0.05, fc='gray', ec='gray', alpha=0.5)
                    if direction == Direction.EAST:
                        self.ax.arrow(x+0.1, y+0.05, nx-x-0.2, 0, **kw)
                    elif direction == Direction.WEST:
                        self.ax.arrow(x-0.1, y-0.05, nx-x+0.2, 0, **kw)
                    elif direction == Direction.SOUTH:
                        self.ax.arrow(x-0.05, y+0.1, 0, ny-y-0.2, **kw)
                    elif direction == Direction.NORTH:
                        self.ax.arrow(x+0.05, y-0.1, 0, ny-y+0.2, **kw)
        
        # Draw traffic signals — only for valid arrival directions at each intersection.
        # Corner intersections (B, C, D) have 2 signals; T-intersections have 3; (1,1) has 4.
        signal_offset = 0.18
        signal_radius = 0.045
        dir_offsets = {
            Direction.NORTH: (0,  -signal_offset),
            Direction.SOUTH: (0,   signal_offset),
            Direction.EAST:  ( signal_offset, 0),
            Direction.WEST:  (-signal_offset, 0),
        }
        for x in range(3):
            for y in range(3):
                for direction in RoadNetwork.get_valid_arrival_directions(x, y):
                    dx, dy = dir_offsets[direction]
                    state = self._signals.get((x, y, direction), SignalState.RED)
                    color = '#00dd00' if state == SignalState.GREEN else '#dd0000'
                    sig = plt.Circle((x + dx, y + dy), signal_radius, color=color,
                                     fill=True, zorder=5)
                    self.ax.add_patch(sig)

        # Draw vehicles
        for vehicle in self.sim.vehicle_manager.vehicles.values():
            pos = vehicle.position
            max_slots = RoadNetwork.get_max_slots(pos.x, pos.y, pos.direction)

            # Calculate visual position using actual segment length (not hardcoded 30)
            if pos.direction == Direction.EAST:
                vx = pos.x + (pos.slot / max_slots) * 1.0
                vy = pos.y + 0.05
            elif pos.direction == Direction.WEST:
                vx = pos.x - (pos.slot / max_slots) * 1.0
                vy = pos.y - 0.05
            elif pos.direction == Direction.SOUTH:
                vx = pos.x - 0.05
                vy = pos.y + (pos.slot / max_slots) * 1.0
            else:  # NORTH
                vx = pos.x + 0.05
                vy = pos.y - (pos.slot / max_slots) * 1.0
            
            color = 'green' if len(vehicle.visited) == 3 else 'orange'
            circle = plt.Circle((vx, vy), 0.08, color=color, fill=True, alpha=0.7)
            self.ax.add_patch(circle)
            self.ax.text(vx, vy, str(vehicle.id), ha='center', va='center', 
                        fontsize=6, color='white', fontweight='bold')
        
        self.ax.set_title(f"Step: {self.sim.time_step} | Active: {len(self.sim.vehicle_manager.vehicles)} | "
                         f"Completed: {self.sim.vehicle_manager.completed_vehicles}")
    
    def animate(self, frame):
        """Animation update function"""
        # Run one simulation step
        import random
        if random.random() < self.sim.spawn_rate:
            self.sim.vehicle_manager.spawn_vehicle()

        vehicle_states = self.sim.vehicle_manager.get_vehicle_states()
        infra_state = self.sim.infra_manager.process_vehicle_states(vehicle_states)
        self._signals = infra_state.signals
        self.sim.vehicle_manager.update_vehicles(infra_state)
        self.sim.time_step += 1

        # Redraw
        self.draw_network()

        # Stop if done
        if self.sim.time_step >= self.sim.max_time_steps:
            self._anim.event_source.stop()

    def run(self):
        """Run visualization"""
        self._anim = FuncAnimation(self.fig, self.animate, frames=self.sim.max_time_steps,
                           interval=100, repeat=False)
        plt.show()

def visualize():
    """Run simulation with visualization"""
    sim = Simulation(max_vehicles=2,max_time_steps=1000)
    viz = Visualizer(sim)
    viz.run()

if __name__ == "__main__":
    visualize()
