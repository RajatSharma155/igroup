/*
 * 02_processes.pml  --  Concurrent processes and interleaving
 *
 * Run:
 *   spin 02_processes.pml               # simulate once (random schedule)
 *   spin 02_processes.pml               # run again -- output may differ!
 *   spin -a 02_processes.pml && gcc -o pan pan.c && ./pan -a   # verify ALL interleavings
 *
 * Concepts: proctype, run, nondeterminism, race conditions, atomic
 *
 * KEY INSIGHT: SPIN does not pick one schedule -- it explores every possible
 * interleaving of all processes.  If any schedule leads to an assert failure,
 * SPIN finds it.
 */

byte x = 0;

/* ── proctype: a reusable process template (like a function/thread) ──────── */
proctype Incrementer(byte id) {
    printf("Process %d: x was %d\n", id, x);
    x = x + 1;
    printf("Process %d: x is now %d\n", id, x)
}

/* ── A second process that reads x ──────────────────────────────────────── */
proctype Reader() {
    /* This process "blocks" until x >= 2, then proceeds.
     * In Promela, a bare expression used as a statement is a GUARD:
     * the process waits until it becomes true.                          */
    x >= 2;
    printf("Reader: saw x = %d\n", x);
    assert(x >= 2)
}

init {
    /* run() spawns a process.  All three run concurrently. */
    run Incrementer(1);
    run Incrementer(2);
    run Reader();

    /* Wait for all spawned processes to finish before init exits.
     * (_nr_pr is a built-in variable = number of running processes) */
    (_nr_pr == 1)   /* blocks until only init itself is left */
}

/*
 * Try this experiment: change assert(x >= 2) to assert(x == 3).
 * SPIN will find a counterexample because Reader might run before
 * both Incrementers finish.
 */
