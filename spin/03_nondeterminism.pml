/*
 * 03_nondeterminism.pml  --  Nondeterminism: the heart of model checking
 *
 * Run:
 *   spin 03_nondeterminism.pml          # one random simulation
 *   spin -a 03_nondeterminism.pml && gcc -o pan pan.c && ./pan -a
 *
 * Concepts: nondeterministic if, nondeterministic do, modeling environments
 *
 * KEY INSIGHT: When multiple guards (::) in an if/do are true at the same
 * time, SPIN explores ALL of them -- not just one.  This lets you model
 * "any possible input" or "any possible environment" without enumerating
 * every case manually.
 *
 * This is exactly how traffic_signal.pml models V-group:
 *   "demand can be 0 or 1 -- SPIN checks every combination"
 */

byte value = 0;

proctype NondeterministicChoice() {
    /* All three guards are true when value == 0.
     * SPIN will explore all three branches. */
    if
    :: value = 1; printf("chose path 1\n")
    :: value = 2; printf("chose path 2\n")
    :: value = 3; printf("chose path 3\n")
    fi;

    /* This assert holds regardless of which branch was taken */
    assert(value >= 1 && value <= 3)
}

proctype NondeterministicLoop() {
    byte n = 0;

    /* Loop that may exit at any iteration (models "at some unknown point") */
    do
    :: n < 10 -> n = n + 1          /* continue */
    :: break                         /* exit at any time */
    od;

    printf("loop exited at n = %d\n", n);
    assert(n <= 10)
}

/* ─────────────────────────────────────────────────────────────────────────
 * Modeling an environment nondeterministically (key pattern for your model)
 *
 * Instead of simulating real vehicles, traffic_signal.pml does exactly this:
 *
 *   if
 *   :: gdemand[iid][d] = 0    // no vehicle
 *   :: gdemand[iid][d] = 1    // vehicle waiting
 *   fi
 *
 * SPIN checks the signal algorithm holds for EVERY possible demand pattern.
 * ───────────────────────────────────────────────────────────────────────── */
byte sensor = 0;    /* models a traffic sensor */

proctype SignalCheck() {
    /* Nondeterministically set demand */
    if
    :: sensor = 0
    :: sensor = 1
    fi;

    /* Property: signal controller must handle both cases correctly.
     * Here we just assert sensor is valid (trivially true). */
    assert(sensor == 0 || sensor == 1);
    printf("sensor = %d\n", sensor)
}

init {
    run NondeterministicChoice();
    run NondeterministicLoop();
    run SignalCheck();
    (_nr_pr == 1)
}
