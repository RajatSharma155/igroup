/*
 * 07_peterson.pml  --  Peterson's Algorithm
 *
 * Peterson (1981): a software-only mutual exclusion algorithm for 2 processes.
 * No hardware atomics required -- just reads and writes of shared variables.
 *
 * Variables:
 *   flag[i]  -- process i signals its intent to enter the CS
 *   turn     -- tie-breaker: the process that set turn LAST waits
 *
 * Protocol for process i (other = 1-i):
 *   1.  flag[i] = true        // "I want in"
 *   2.  turn    = other       // "but you go first if you want"
 *   3.  wait until !(flag[other] && turn == other)
 *   4.  [critical section]
 *   5.  flag[i] = false       // "I'm done"
 *
 * Correctness argument:
 *   Safety:  If both reach step 3 simultaneously, turn can only equal 0 or 1,
 *            so exactly one of them sees the wait condition false.
 *   Liveness: The waiting process waits only while the other is in CS.
 *            Once the other exits (flag[other]=false), the wait condition breaks.
 *
 * Run:
 *   spin -a 07_peterson.pml && gcc -o pan pan.c && ./pan -a
 *
 *   # Liveness checks (need -f for weak fairness):
 *   spin -a -N no_starvation_0 07_peterson.pml && gcc -o pan pan.c && ./pan -a -f
 *   spin -a -N no_starvation_1 07_peterson.pml && gcc -o pan pan.c && ./pan -a -f
 *
 * Expected: 0 errors for all properties.
 */

/* ── Shared variables ───────────────────────────────────────────────────── */
bool flag[2];   /* flag[i]: process i wants to enter         */
byte turn;      /* turn: the process that must wait (0 or 1) */
byte in_cs;     /* count of processes in critical section    */

/* ── LTL Properties ─────────────────────────────────────────────────────── */
ltl mutual_exclusion { [] (in_cs <= 1) }
ltl no_starvation_0  { [] (flag[0] -> <> (in_cs == 1)) }
ltl no_starvation_1  { [] (flag[1] -> <> (in_cs == 1)) }

/* ── Process template ───────────────────────────────────────────────────── */
proctype Peterson(byte me) {
    byte other = 1 - me;

    do
    :: true ->
        /* ── Entry protocol ── */
        flag[me] = true;         /* Step 1: announce intent                */
        turn     = other;        /* Step 2: give the other priority        */

        /* Step 3: wait -- suspend until the other is NOT competing
         *         OR it is our turn (the other set turn back to us).
         *
         * In Promela, a boolean used as a statement is a GUARD:
         * execution blocks here until the expression is true.             */
        !(flag[other] == true && turn == other);

        /* ── Critical section ── */
        in_cs = in_cs + 1;
        assert(in_cs == 1);      /* SPIN checks this on every reachable state */
        printf("P%d in CS\n", me);
        in_cs = in_cs - 1;

        /* ── Exit protocol ── */
        flag[me] = false          /* Step 5: release intent flag           */
    od
}

init {
    flag[0] = false;
    flag[1] = false;
    turn    = 0;
    in_cs   = 0;
    run Peterson(0);
    run Peterson(1)
}

/*
 * Experiment: comment out "turn = other" in one process and re-verify.
 * SPIN will find a counterexample showing both processes can enter the CS.
 *
 * Experiment 2: change the flag assignment and wait in the wrong order:
 *   turn     = other;     ← swap these two lines
 *   flag[me] = true;
 * SPIN will again find a safety violation.
 *
 * These experiments show why each line of Peterson's algorithm is necessary.
 */
