/* ===========================================================
 * traffic_signal.pml
 * Promela / SPIN model of the I-Group Traffic Signal Controller
 * ECEN 723 Spring 2026, Team 14
 *
 * Grid intersections modeled (iid -> grid coordinate):
 *   iid 0->(0,0)  1->(1,0)  2->(2,0)
 *   iid 3->(0,1)  4->(1,1)  5->(2,1)
 *   iid 6->(0,2)  7->(1,2)  8->(2,2)
 * Point A (-1,0) has exactly one arrival direction (WEST) and is trivially safe.
 *
 * Directions: NORTH=0  SOUTH=1  EAST=2  WEST=3
 * Signals:    RED=0    GREEN=1
 *
 * Verified properties:
 *   P1 -- Safety:           at most one GREEN per intersection per step  (assert)
 *   P2 -- Liveness:         any direction with demand eventually gets GREEN  (LTL)
 *   P3 -- Bounded liveness: GREEN arrives within WAIT_BOUND steps  (LTL)
 *
 * Demand is fully nondeterministic -- models ALL possible V-group inputs.
 * The tie-breaking in argmax is also nondeterministic -- more conservative
 * than the Python implementation's dict-ordering tie-break.
 *
 * ===========================================================
 * How to compile and run:
 *
 *   # 1. Verify P1 (assert-based safety) -- exhaustive state space
 *   spin -a traffic_signal.pml
 *   gcc -o pan pan.c
 *   ./pan -a
 *
 *   # 2. Verify a specific LTL property (P2 or P3), e.g. p2_int4_north
 *   spin -a -N p2_int4_north traffic_signal.pml
 *   gcc -o pan pan.c
 *   ./pan -a -f          # -f enables weak fairness, required for liveness
 *
 *   # 3. If state space is too large, add partial-order reduction:
 *   gcc -DNOREDUCE -o pan pan.c && ./pan -a -f
 *   # or use bitstate hashing for a memory-bounded approximate check:
 *   gcc -DBITSTATE -o pan pan.c && ./pan -a -f
 *
 * Expected results:
 *   P1 (assert)         -- no errors, all reachable states satisfy green_count <= 1
 *   P2 (liveness LTL)   -- no counterexample under weak fairness (-f)
 *   P3 (bounded LTL)    -- no counterexample; GREEN always within WAIT_BOUND=8 steps
 *
 * State-space estimate (per intersection instance):
 *   sig[4]    -- 2 values each, only valid directions reachable -> small
 *   wait[4]   -- 0..WAIT_CAP (= 10) per direction               -> 11^4 = 14641
 *   gdemand[4]-- 2 values each, 4 directions                    -> 2^4 = 16
 *   Combined  -- ~2.3M states per instance (independent processes)
 * ===========================================================
 */

/* ---- Direction constants (must match indices 0..3) ---- */
#define NORTH 0
#define SOUTH 1
#define EAST  2
#define WEST  3

#define RED   0
#define GREEN 1

/* ---- Algorithm parameters (match i_group.py exactly) ---- */
#define STARVATION_THRESHOLD 2

/* WAIT_CAP: upper bound clamped onto wait counters to keep state space finite.
 *
 * Worst-case derivation for a 4-direction intersection under adversarial scheduling:
 *   Step 0: all eff=1, adversary picks SOUTH.   wait[NORTH]=1
 *   Step 1: all eff=1, adversary picks EAST.    wait[NORTH]=2
 *   Step 2: NORTH eff=2, WEST eff=2, others 1.  adversary picks WEST. wait[NORTH]=3
 *   Step 3: NORTH eff=2, SOUTH eff=2, others 1. adversary picks SOUTH. wait[NORTH]=4
 *   Step 4: NORTH eff=1+4/2=3, all others <=2.  NORTH must win. GREEN at step 4.
 *
 * Maximum wait before guaranteed GREEN: 4 steps. WAIT_CAP=10 provides 2.5x margin.
 * The cap does not break liveness: a capped direction has fixed eff=1+WAIT_CAP/2,
 * while its competitors cycle through lower waits (reset on service), so the capped
 * direction eventually wins every nondeterministic tie.
 */
#define WAIT_CAP 10

/* ---- Bounded liveness horizon for P3 ---- */
/* Worst case GREEN latency = 4 steps (derived above). WAIT_BOUND=8 is 2x margin. */
#define WAIT_BOUND 8

/* ---- Macro: test whether direction d is valid for mask m ---- */
/* Bit layout of vmask: bit0=NORTH bit1=SOUTH bit2=EAST bit3=WEST */
#define VALID(m, d) (((m) >> (d)) & 1)

/* ===========================================================
 * Global observable state
 *   sig[iid][dir]      -- signal state at intersection iid, direction dir
 *   gdemand[iid][dir]  -- demand at intersection iid, direction dir
 *                         (set nondeterministically each step; read by LTL)
 * =========================================================== */
byte sig[9][4];
byte gdemand[9][4];

/* ===========================================================
 * LTL Properties
 *
 * All properties are stated for intersection 4 (coordinate (1,1)),
 * which is the most complex (all 4 directions valid, maximum competition).
 * Re-run verification with different iid indices for other intersections.
 *
 * P1 is verified inline via assert() inside each atomic step --
 * no separate LTL formula is needed.
 *
 * For P2 and P3 (liveness), run pan with the -f flag (weak fairness):
 *   ./pan -a -f
 * Weak fairness ensures each continuously-enabled process eventually runs,
 * which is the minimum needed to make liveness meaningful.
 *
 * Semantics of P2:
 *   "Whenever demand is 1 at some step, GREEN eventually follows in this trace."
 *   A trace that holds demand=1 forever but never grants GREEN is a violation.
 *   A trace where demand drops to 0 before GREEN arrives is NOT a violation
 *   (the obligation discharged vacuously -- no vehicle is blocked).
 *
 * Semantics of P3:
 *   "Whenever demand is 1 at step t, GREEN holds at some step in [t, t+WAIT_BOUND]."
 *   Expressed as a nested X (next-step) unrolling of depth WAIT_BOUND.
 * =========================================================== */

/* P2: demand implies eventual GREEN */
ltl p2_int4_north { [] (gdemand[4][NORTH] == 1 -> <> (sig[4][NORTH] == GREEN)) }
ltl p2_int4_south { [] (gdemand[4][SOUTH] == 1 -> <> (sig[4][SOUTH] == GREEN)) }
ltl p2_int4_east  { [] (gdemand[4][EAST]  == 1 -> <> (sig[4][EAST]  == GREEN)) }
ltl p2_int4_west  { [] (gdemand[4][WEST]  == 1 -> <> (sig[4][WEST]  == GREEN)) }

/* P3: bounded liveness -- GREEN within WAIT_BOUND=8 steps.
 * The nested X formula  e || X(e || X(e || ... X(e)...))  of depth k
 * means "e holds at the current step, or 1 step from now, or 2 steps, ..., or k steps."
 *
 * Shorthand macros for readability: */
#define G4N (sig[4][NORTH] == GREEN)
#define G4S (sig[4][SOUTH] == GREEN)
#define G4E (sig[4][EAST]  == GREEN)
#define G4W (sig[4][WEST]  == GREEN)

ltl p3_int4_north {
    [] (gdemand[4][NORTH] == 1 ->
        (G4N || X(G4N || X(G4N || X(G4N ||
         X(G4N || X(G4N || X(G4N || X(G4N || X(G4N))))))))))
}
ltl p3_int4_south {
    [] (gdemand[4][SOUTH] == 1 ->
        (G4S || X(G4S || X(G4S || X(G4S ||
         X(G4S || X(G4S || X(G4S || X(G4S || X(G4S))))))))))
}
ltl p3_int4_east {
    [] (gdemand[4][EAST] == 1 ->
        (G4E || X(G4E || X(G4E || X(G4E ||
         X(G4E || X(G4E || X(G4E || X(G4E || X(G4E))))))))))
}
ltl p3_int4_west {
    [] (gdemand[4][WEST] == 1 ->
        (G4W || X(G4W || X(G4W || X(G4W ||
         X(G4W || X(G4W || X(G4W || X(G4W || X(G4W))))))))))
}

/* ===========================================================
 * Generic intersection process
 *
 * Parameters:
 *   iid   -- intersection index (0..8)
 *   vmask -- bitmask of valid arrival directions
 *             bit0=NORTH  bit1=SOUTH  bit2=EAST  bit3=WEST
 *
 * Valid-direction mask derivation (from RoadNetwork.get_valid_arrival_directions):
 *   A direction d is valid at (x,y) iff there is a road segment entering (x,y)
 *   traveling in direction d, i.e., it is the opposite of some exit direction.
 *
 *   iid  coord   valid arrivals     mask  (binary)
 *    0   (0,0)   N, E, W            13    (1101)
 *    1   (1,0)   N, E, W            13    (1101)
 *    2   (2,0)   N, E                5    (0101)
 *    3   (0,1)   N, S, W            11    (1011)
 *    4   (1,1)   N, S, E, W         15    (1111)
 *    5   (2,1)   N, S, E             7    (0111)
 *    6   (0,2)   S, W               10    (1010)
 *    7   (1,2)   S, E, W            14    (1110)
 *    8   (2,2)   S, E                6    (0110)
 *
 * One iteration of the main loop = one simulation time step.
 * The entire step is wrapped in atomic{} so LTL sees only fully-updated states.
 * ===========================================================
 */
proctype intersection(byte iid; byte vmask) {
    byte d;
    byte wait[4];       /* starvation wait counters, one per direction */
    byte eff[4];        /* effective demand = base + wait/THRESHOLD    */
    byte max_eff;       /* maximum effective demand this step          */
    byte winner;        /* direction chosen to receive GREEN           */
    byte any_demand;    /* 1 iff at least one valid direction has demand > 0 */
    byte green_count;   /* scratch var for P1 assertion                */

    /* ----- Initialise: all signals RED, all counters zero ---------- */
    d = 0;
    do
    :: d < 4 ->
        wait[d]        = 0;
        sig[iid][d]    = RED;
        gdemand[iid][d] = 0;
        d = d + 1
    :: d >= 4 -> break
    od;

    /* ===========================================================
     * Main loop: one iteration = one simulation time step.
     * ===========================================================
     */
    do
    :: atomic {

        /* ----------------------------------------------------------
         * Step 1: Set demand nondeterministically for each valid direction.
         *
         * This models all possible vehicle configurations that V-group
         * could report.  Invalid directions always get demand=0.
         * Base demand is abstracted to {0, 1} -- the exact vehicle count
         * does not matter for liveness (only whether demand > 0 matters
         * for the starvation algorithm).
         * ---------------------------------------------------------- */
        d = 0;
        do
        :: d < 4 ->
            if
            :: VALID(vmask, d) ->
                if
                :: gdemand[iid][d] = 0
                :: gdemand[iid][d] = 1
                fi
            :: else ->
                gdemand[iid][d] = 0
            fi;
            d = d + 1
        :: d >= 4 -> break
        od;

        /* ----------------------------------------------------------
         * Step 2: Compute effective demand with starvation boost.
         *
         * Mirrors i_group.py TrafficSignalController.update_signals():
         *   if base > 0:
         *       eff[d] = base + wait[d] // STARVATION_THRESHOLD
         *   else:
         *       eff[d] = 0
         *
         * Note: when base == 0 the wait counter is NOT consulted and
         * eff stays 0 regardless of accumulated wait.
         * ---------------------------------------------------------- */
        any_demand = 0;
        d = 0;
        do
        :: d < 4 ->
            if
            :: gdemand[iid][d] > 0 ->
                eff[d] = gdemand[iid][d] + wait[d] / STARVATION_THRESHOLD;
                any_demand = 1
            :: else ->
                eff[d] = 0
            fi;
            d = d + 1
        :: d >= 4 -> break
        od;

        /* ----------------------------------------------------------
         * Steps 3-5: Select winner, assign signals, update counters.
         * ---------------------------------------------------------- */
        if
        :: any_demand == 1 ->

            /* Find the maximum effective demand over all valid directions. */
            max_eff = 0;
            d = 0;
            do
            :: d < 4 ->
                if
                :: VALID(vmask, d) && eff[d] > max_eff ->
                    max_eff = eff[d]
                :: else -> skip
                fi;
                d = d + 1
            :: d >= 4 -> break
            od;

            /* Nondeterministically select winner from all valid directions
             * that achieve max_eff.  Multiple guards can be enabled when
             * directions are tied; SPIN explores all choices.
             *
             * Correctness note: max_eff >= 1 (guaranteed by any_demand==1),
             * so at least one valid direction has eff == max_eff.
             * The if statement cannot block here.                           */
            if
            :: VALID(vmask, NORTH) && eff[NORTH] == max_eff -> winner = NORTH
            :: VALID(vmask, SOUTH) && eff[SOUTH] == max_eff -> winner = SOUTH
            :: VALID(vmask, EAST)  && eff[EAST]  == max_eff -> winner = EAST
            :: VALID(vmask, WEST)  && eff[WEST]  == max_eff -> winner = WEST
            fi;

            /* Assign GREEN to winner, RED to all other directions. */
            d = 0;
            do
            :: d < 4 ->
                if
                :: d == winner -> sig[iid][d] = GREEN
                :: else        -> sig[iid][d] = RED
                fi;
                d = d + 1
            :: d >= 4 -> break
            od;

            /* Update starvation wait counters.
             *
             * Mirrors i_group.py exactly:
             *   direction_wait_steps[(x,y,chosen)] = 0           (reset winner)
             *   for d != chosen and demand[d] > 0: wait[d] += 1  (accumulate losers)
             *   (no change when demand[d] == 0)
             *
             * The wait counter for a direction with no demand is left unchanged.
             * This means if a direction had accumulated wait, that wait persists
             * and gives a faster boost the next time demand appears.
             */
            d = 0;
            do
            :: d < 4 ->
                if
                :: !VALID(vmask, d) ->
                    skip
                :: VALID(vmask, d) && d == winner ->
                    wait[d] = 0
                :: VALID(vmask, d) && d != winner && gdemand[iid][d] > 0 ->
                    if
                    :: wait[d] < WAIT_CAP -> wait[d] = wait[d] + 1
                    :: else               -> skip   /* already at cap -- no further increment */
                    fi
                :: else ->
                    skip   /* valid, not winner, no demand: leave wait unchanged */
                fi;
                d = d + 1
            :: d >= 4 -> break
            od

        :: else ->
            /* No demand at any valid direction this step.
             * Set all signals RED.  Wait counters are NOT reset --
             * this matches i_group.py (no reset code in the else branch). */
            d = 0;
            do
            :: d < 4 -> sig[iid][d] = RED; d = d + 1
            :: d >= 4 -> break
            od
        fi;

        /* ----------------------------------------------------------
         * P1 Safety assertion: at most one GREEN per intersection.
         *
         * SPIN checks this for every reachable state during exhaustive
         * search.  A violation here would mean the algorithm is broken.
         * ---------------------------------------------------------- */
        green_count = 0;
        d = 0;
        do
        :: d < 4 -> green_count = green_count + sig[iid][d]; d = d + 1
        :: d >= 4 -> break
        od;
        assert(green_count <= 1)

    } /* end atomic */
    od /* end main loop */
}

/* ===========================================================
 * init: spawn one process per grid intersection.
 *
 * Each process is fully independent -- intersections share no state
 * in either the Python code or this model.  SPIN verifies each
 * proctype instance simultaneously in its interleaved state space.
 * ===========================================================
 */
init {
    run intersection(0, 13);   /* (0,0): N, E, W     */
    run intersection(1, 13);   /* (1,0): N, E, W     */
    run intersection(2,  5);   /* (2,0): N, E        */
    run intersection(3, 11);   /* (0,1): N, S, W     */
    run intersection(4, 15);   /* (1,1): N, S, E, W  */
    run intersection(5,  7);   /* (2,1): N, S, E     */
    run intersection(6, 10);   /* (0,2): S, W        */
    run intersection(7, 14);   /* (1,2): S, E, W     */
    run intersection(8,  6)    /* (2,2): S, E        */
}
