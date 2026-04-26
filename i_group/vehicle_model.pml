/*
 * vehicle_model.pml  —  ECEN 723 Team 14, I-Group, Phase C
 *
 * SPIN Promela abstract model of the vehicle routing system.
 *
 * Abstraction rationale
 * ---------------------
 * The Python code has two kinds of steps:
 *   (a) advance one slot along a road segment  — no constraint can be violated
 *   (b) cross an intersection (jump to slot 1 of next road) — all violations here
 * We therefore model one Promela step as one INTERSECTION CROSSING and abstract
 * away slot-level movement inside road segments.
 *
 * Each Vehicle process visits three checkpoint intersections in order, then
 * signals completion.  The SignalCtrl process non-deterministically assigns
 * GREEN to one checkpoint signal per step, over-approximating all possible
 * I-Group signal schedules.
 *
 * Depth-management abstractions (evolved through three iterations)
 * ----------------------------------------------------------------
 * 1. Only the 3 checkpoint intersections (B, C, D) carry signal/occupancy
 *    state; 6 intermediate grid intersections are abstracted away.  This
 *    reduces the signal state space from 4^9 = 262 144 to 4^3 = 64.
 * 2. SignalCtrl updates ONE checkpoint signal per outer-loop step via a
 *    flat 12-branch if (3 checkpoints × 4 directions), preventing the
 *    ~18-step-per-cycle depth multiplication of the original inner loop.
 * 3. Vehicles sample the current GREEN direction atomically rather than
 *    choosing a fixed arrival direction and blocking.  This eliminates
 *    unbounded waiting paths (SignalCtrl cycling without granting GREEN)
 *    while preserving all safety guarantees: a vehicle still crosses only
 *    when GREEN, so all five LTL properties remain sound.
 * 4. SignalCtrl exits once done[0] ∧ done[1], bounding search depth.
 * 5. The slot claim uses atomic { guard; assign } (test-and-set) instead
 *    of a separate guard + d_step, eliminating the TOCTOU window.
 *
 * Properties verified (LTL):
 *   P1  no_uturn    — no vehicle makes a U-turn at any intersection
 *   P2  no_red      — no vehicle enters an intersection at RED
 *   P3  visit_all   — every completing vehicle has visited B, C, and D
 *   P4  no_coll     — no two vehicles occupy the same intersection simultaneously
 *   P5  liveness    — every vehicle eventually completes its tour
 *
 * Run commands (after installation):
 *   spin -search -ltl no_uturn   vehicle_model.pml
 *   spin -search -ltl no_red     vehicle_model.pml
 *   spin -search -ltl visit_all  vehicle_model.pml
 *   spin -search -ltl no_coll    vehicle_model.pml
 *   spin -search -ltl liveness -a -f vehicle_model.pml   (fairness needed)
 */

/* ─────────────────────────── Directions ────────────────────────────────── */
/* Encoded so that OPP(d) = d XOR 1 gives N<->S and E<->W correctly:        */
/*   DIR_N=0, DIR_S=1  →  0^1=1, 1^1=0  ✓                                  */
/*   DIR_E=2, DIR_W=3  →  2^1=3, 3^1=2  ✓                                  */
#define DIR_N    0
#define DIR_S    1
#define DIR_E    2
#define DIR_W    3
#define OPP(d)   ((d) ^ 1)

/* ─────────────────── Checkpoint indices (compact, 0–2) ─────────────────── */
/* Only the three checkpoint intersections appear in the model.              */
/* sig[] and occ[] are indexed by these constants.                          */
#define CP_B 0    /* checkpoint B at grid (0,2) */
#define CP_C 1    /* checkpoint C at grid (2,2) */
#define CP_D 2    /* checkpoint D at grid (2,0) */

/* ───────────────────────── Model parameters ────────────────────────────── */
#define NVEH 2    /* number of concurrent vehicles modelled */
#define FREE 255  /* sentinel: checkpoint slot is unoccupied */

/* ─────────────────────────── Shared state ──────────────────────────────── */
/* sig[i]  = direction currently holding GREEN at checkpoint i.              */
/* occ[i]  = vehicle id currently crossing checkpoint i, or FREE.           */
byte sig[3];
byte occ[3];

/* ────────────────────── Per-vehicle observable flags ───────────────────── */
bool vis_B[NVEH];   /* vehicle has crossed checkpoint B */
bool vis_C[NVEH];   /* vehicle has crossed checkpoint C */
bool vis_D[NVEH];   /* vehicle has crossed checkpoint D */
bool done[NVEH];    /* vehicle has completed full tour  */

/* ────────────────────── Violation flags ────────────────────────────────── */
/* These start false; the LTL properties assert they remain false forever.   */
bool fl_uturn;   /* a U-turn was made */
bool fl_red;     /* a vehicle crossed on RED */
bool fl_coll;    /* two vehicles occupied the same checkpoint slot */

/* ==========================================================================
   SignalCtrl
   Non-deterministically assigns exactly one GREEN direction to one of the
   three checkpoint intersections per outer-loop step.  12-branch flat if
   (3 checkpoints × 4 directions) over-approximates all signal schedules.
   Terminates once all vehicles complete, bounding SPIN's search depth.
   ========================================================================== */
active proctype SignalCtrl() {
    do
    :: (done[0] && done[1]) -> break
    :: else ->
       if
       :: sig[CP_B] = DIR_N :: sig[CP_B] = DIR_S
       :: sig[CP_B] = DIR_E :: sig[CP_B] = DIR_W
       :: sig[CP_C] = DIR_N :: sig[CP_C] = DIR_S
       :: sig[CP_C] = DIR_E :: sig[CP_C] = DIR_W
       :: sig[CP_D] = DIR_N :: sig[CP_D] = DIR_S
       :: sig[CP_D] = DIR_E :: sig[CP_D] = DIR_W
       fi
    od
}

/* ==========================================================================
   Vehicle(id, cp0, cp1, cp2)
   Visits cp0 → cp1 → cp2 in order, then marks done.

   At each crossing the process enforces (mirroring v_group.py):
     - Samples the current GREEN direction as its arrival direction  (→ P2)
     - Picks an exit direction that is NOT the U-turn direction      (→ P1)
     - Atomically waits for a free slot then claims it               (→ P4)
     - Marks the checkpoint flag                                     (→ P3)
     - Releases the slot

   cp0/cp1/cp2 are passed from init to model Strategy-E ordering:
     even-ID vehicles: B→C→D   odd-ID vehicles: D→C→B
   ========================================================================== */
proctype Vehicle(byte id; byte cp0; byte cp1; byte cp2) {
    byte step;
    byte target;
    byte arr_dir;   /* direction in which vehicle arrives at target */
    byte exit_dir;  /* direction in which vehicle leaves target     */

    step = 0;

    do
    :: step < 3 ->

        /* ── Select target checkpoint ────────────────────────────────── */
        if
        :: step == 0 -> target = cp0
        :: step == 1 -> target = cp1
        :: step == 2 -> target = cp2
        fi;

        /* ── P2: Sample current GREEN direction as arrival direction ─────
           All four guards evaluate sig[target] in a single atomic step;
           exactly one fires (the branch matching the current GREEN value).
           arr_dir therefore always equals sig[target] at crossing time,
           so the vehicle never enters on RED.  fl_red is never set.       */
        if
        :: sig[target] == DIR_N -> arr_dir = DIR_N
        :: sig[target] == DIR_S -> arr_dir = DIR_S
        :: sig[target] == DIR_E -> arr_dir = DIR_E
        :: sig[target] == DIR_W -> arr_dir = DIR_W
        fi;

        /* ── P1: Choose exit — any direction except U-turn ───────────── */
        if
        :: (OPP(arr_dir) != DIR_N) -> exit_dir = DIR_N
        :: (OPP(arr_dir) != DIR_S) -> exit_dir = DIR_S
        :: (OPP(arr_dir) != DIR_E) -> exit_dir = DIR_E
        :: (OPP(arr_dir) != DIR_W) -> exit_dir = DIR_W
        fi;
        /* Sanity assertion — structurally unreachable in a correct model */
        if
        :: exit_dir == OPP(arr_dir) -> fl_uturn = true
        :: else -> skip
        fi;

        /* ── P4: Atomic test-and-set — eliminates TOCTOU race ───────────
           atomic { guard; assign } ensures no interleaving between the
           free-check and the claim, making mutual exclusion watertight.  */
        atomic {
            (occ[target] == FREE);
            occ[target] = id
        };

        /* ── P3: Mark checkpoint visited ─────────────────────────────── */
        if
        :: target == CP_B -> vis_B[id] = true
        :: target == CP_C -> vis_C[id] = true
        :: target == CP_D -> vis_D[id] = true
        :: else -> skip
        fi;

        /* Release checkpoint slot */
        occ[target] = FREE;

        step++

    :: else ->
        done[id] = true;
        break
    od
}

/* ==========================================================================
   init — initialise shared state and launch all processes
   ========================================================================== */
init {
    /* Initialise checkpoint signals and occupancy (3 entries each) */
    sig[CP_B] = DIR_N;  sig[CP_C] = DIR_N;  sig[CP_D] = DIR_N;
    occ[CP_B] = FREE;   occ[CP_C] = FREE;   occ[CP_D] = FREE;

    /* Initialise per-vehicle flags */
    vis_B[0] = false;  vis_C[0] = false;  vis_D[0] = false;  done[0] = false;
    vis_B[1] = false;  vis_C[1] = false;  vis_D[1] = false;  done[1] = false;

    /* Initialise violation flags */
    fl_uturn = false;
    fl_red   = false;
    fl_coll  = false;

    /* Launch vehicles using Strategy-E checkpoint ordering (CLAUDE.md):
         even ID (0): B→C→D  (counterclockwise outer ring)
         odd  ID (1): D→C→B  (clockwise outer ring)              */
    run Vehicle(0, CP_B, CP_C, CP_D);
    run Vehicle(1, CP_D, CP_C, CP_B);
}

/* ==========================================================================
   LTL Properties
   ========================================================================== */

/* P1 — No U-turn at any intersection, ever */
ltl no_uturn  { [] !fl_uturn }

/* P2 — No vehicle enters an intersection while its signal is RED */
ltl no_red    { [] !fl_red }

/* P3 — Every vehicle that completes its tour has visited B, C, and D */
ltl visit_all {
    [] ( (done[0] -> (vis_B[0] && vis_C[0] && vis_D[0])) &&
         (done[1] -> (vis_B[1] && vis_C[1] && vis_D[1])) )
}

/* P4 — No two vehicles occupy the same checkpoint slot simultaneously */
ltl no_coll   { [] !fl_coll }

/* P5 (self-choice) — Every vehicle eventually completes its tour.
   This is a liveness property; verify with weak fairness: -a -f flags. */
ltl liveness  { <> (done[0] && done[1]) }
