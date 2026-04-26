/*
 * 06_mutex.pml  --  Mutual Exclusion (naive attempt vs correct)
 *
 * SAFETY property:  at most one process is in the critical section at a time.
 * LIVENESS property: every process that wants in, eventually gets in.
 *
 * Run safety check (assert):
 *   spin -a 06_mutex.pml && gcc -o pan pan.c && ./pan -a
 *
 * Run liveness check (LTL, requires weak fairness):
 *   spin -a -N no_starvation_0 06_mutex.pml && gcc -o pan pan.c && ./pan -a -f
 *   spin -a -N no_starvation_1 06_mutex.pml && gcc -o pan pan.c && ./pan -a -f
 *
 * Expected results:
 *   assert         -> 0 errors  (mutual exclusion holds)
 *   no_starvation  -> 0 errors  (neither process starves under fairness)
 */

/* ── Shared state ──────────────────────────────────────────────────────── */
byte in_cs = 0;        /* number of processes currently in critical section */
byte turn  = 0;        /* whose turn: 0 or 1 -- used for tie-breaking       */

/* ── Observable flags for LTL ──────────────────────────────────────────── */
bool want[2];          /* want[i] = process i is trying to enter            */
bool inside[2];        /* inside[i] = process i is currently in CS          */

/* ── LTL Properties ────────────────────────────────────────────────────── */

/* Safety: never two processes in the critical section simultaneously */
ltl mutual_exclusion { [] (in_cs <= 1) }

/* Liveness: if process 0 wants in, it eventually gets in */
ltl no_starvation_0 { [] (want[0] -> <> inside[0]) }

/* Liveness: same for process 1 */
ltl no_starvation_1 { [] (want[1] -> <> inside[1]) }


/* ── Process template ──────────────────────────────────────────────────── */
/*
 * Uses a simple "turn + want" protocol (Dekker-style):
 *
 *   Step 1: announce intent      want[me] = true
 *   Step 2: yield if other wants AND it's their turn
 *   Step 3: enter critical section
 *   Step 4: release              want[me] = false, give turn to other
 *
 * KEY: the interleaving of steps 1 & 2 across two processes is where
 * SPIN's exhaustive search is essential -- you cannot reason about this
 * manually for all possible schedules.
 */
proctype Proc(byte me) {
    byte other = 1 - me;

    do
    :: /* ── non-critical work (can repeat any number of times) ── */
        printf("P%d: non-critical\n", me);

        /* Step 1: declare intent */
        want[me] = true;

        /* Step 2: busy-wait while the other process wants in AND it's their turn.
         *         This guard blocks (suspends the process) until it becomes false. */
        !(want[other] && turn == other);

        /* ── critical section ── */
        in_cs   = in_cs + 1;
        inside[me] = true;

        assert(in_cs == 1);        /* inline safety check every step */
        printf("P%d: IN critical section\n", me);

        inside[me] = false;
        in_cs   = in_cs - 1;

        /* Step 4: release and give turn to the other process */
        turn    = other;
        want[me] = false
    od
}

init {
    want[0]  = false; want[1]  = false;
    inside[0] = false; inside[1] = false;
    run Proc(0);
    run Proc(1)
}
