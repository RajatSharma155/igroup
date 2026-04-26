# simulation.py - Main simulation coordinator

import random
import time
from typing import List, Optional
from common import *
from v_group import VehicleManager
from i_group import InfrastructureManager

class Simulation:
    """Main simulation coordinator"""

    def __init__(self, max_vehicles: int = None, max_time_steps: int = STEPS_PER_HOUR,
                 seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
        self.vehicle_manager = VehicleManager(max_vehicles)
        self.infra_manager = InfrastructureManager()
        self.max_time_steps = max_time_steps
        self.time_step = 0
        self.spawn_rate = 1.0  # Probability of spawning new vehicle each step
        self._warmup_baseline = 0  # completed_vehicles snapshot after warm-up
        
    def run(self):
        """Run the simulation"""
        
        print("=" * 60)
        print("ROAD SYSTEM SIMULATION")
        print("=" * 60)
        
        # Initial infrastructure state
        infra_state = InfrastructureState(signals={}, time_step=0)
        
        for step in range(self.max_time_steps):
            self.time_step = step
            
            # Spawn new vehicles probabilistically
            if random.random() < self.spawn_rate:
                vehicle = self.vehicle_manager.spawn_vehicle()
                if vehicle:
                    print(f"[Step {step}] Spawned vehicle {vehicle.id}")
            
            # V-Group: Get current vehicle states
            vehicle_states = self.vehicle_manager.get_vehicle_states()
            
            # I-Group: Process vehicle states and update signals
            infra_state = self.infra_manager.process_vehicle_states(vehicle_states)
            
            # V-Group: Update vehicle positions based on infrastructure state
            self.vehicle_manager.update_vehicles(infra_state)
            
            # Snapshot completions at end of warm-up period
            if step == WARMUP_STEPS - 1:
                self._warmup_baseline = self.vehicle_manager.completed_vehicles

            # Verify constraints
            valid, message = self.vehicle_manager.verify_constraints()
            if not valid:
                print(f"[Step {step}] ERROR: {message}")
                break

            # Print status every 10 steps
            if step % 10 == 0:
                self.print_status(step)
            
            # Check if simulation should end
            if (len(self.vehicle_manager.vehicles) == 0 and 
                self.vehicle_manager.completed_vehicles > 0):
                print(f"\n[Step {step}] All vehicles completed!")
                break
        
        self.print_final_stats()
    
    def print_status(self, step: int):
        """Print current simulation status"""
        active = len(self.vehicle_manager.vehicles)
        completed = self.vehicle_manager.completed_vehicles
        
        print(f"\n[Step {step}] Active: {active}, Completed: {completed}")
        
        # Print vehicle details
        for vehicle in list(self.vehicle_manager.vehicles.values())[:5]:  # Show first 5
            pos = vehicle.position
            visited = ','.join(vehicle.visited) if vehicle.visited else 'None'
            print(f"  Vehicle {vehicle.id}: ({pos.x},{pos.y}) slot={pos.slot} "
                  f"dir={pos.direction.name} visited=[{visited}]")
    
    def print_final_stats(self):
        """Print final simulation statistics"""
        completed = self.vehicle_manager.completed_vehicles
        hours = self.time_step * TIME_STEP_SECONDS / 3600
        throughput = completed / hours if hours > 0 else 0

        ss_steps = max(self.time_step - WARMUP_STEPS, 0)
        ss_hours = ss_steps * TIME_STEP_SECONDS / 3600
        ss_completed = completed - self._warmup_baseline
        ss_throughput = ss_completed / ss_hours if ss_hours > 0 else 0

        print("\n" + "=" * 60)
        print("SIMULATION COMPLETE")
        print("=" * 60)
        print(f"Total time steps:   {self.time_step}  ({hours:.2f} hours)")
        print(f"Completed vehicles: {completed}")
        print(f"Active vehicles:    {len(self.vehicle_manager.vehicles)}")
        print(f"Throughput (overall):     {throughput:.1f} vehicles/hour")
        print(f"Throughput (steady-state): {ss_throughput:.1f} vehicles/hour"
              f"  (after {WARMUP_STEPS}-step warm-up)")
        print("=" * 60)

def main():
    """Main entry point"""
    sim = Simulation(max_time_steps=STEPS_PER_HOUR)
    sim.run()

if __name__ == "__main__":
    main()
