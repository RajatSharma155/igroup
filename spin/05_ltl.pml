/*
 * 05_ltl.pml  --  Linear Temporal Logic (LTL) properties
 *
 * Run safety (assert) check:
 *   spin -a 05_ltl.pml && gcc -o pan pan.c && ./pan -a
 *
 * Run liveness (LTL) checks -- one property at a time:
 *   spin -a -N always_eventually_green 05_ltl.pml
 *   gcc -o pan pan.c && ./pan -a -f
 *
 *   spin -a -N green_before_red 05_ltl.pml
 *   gcc -o pan pan.c && ./pan -a -f
 *
 *   spin -a -N bad_property 05_ltl.pml
 *   gcc -o pan pan.c && ./pan -a        # should find a counterexample!
 *
 * Concepts: ltl, [] (always), <> (eventually), X (next), ->, U (until), -f flag
 *
 * LTL OPERATORS:
 *   [] p        "always p"         -- p holds at every future step
 *   <> p        "eventually p"     -- p holds at some future step
 *   X p         "next p"           -- p holds at the very next step
 *   p U q       "p until q"        -- p holds continuously until q becomes true
 *   p -> q      "p implies q"      -- if p then q  (same as !p || q)
 *
 * COMMON PATTERNS:
 *   [] p                     safety:   p is always true
 *   <> p                     liveness: p eventually becomes true
 *   [] <> p                  recurrence: p happens infinitely often
 *   [] (p -> <> q)           response: every p is eventually followed by q
 *   [] (p -> X q)            next-step: p is always immediately followed by q
 */

/* ── A simple traffic light model ─────────────────────────────────────────
 * signal: 0=RED, 1=GREEN
 * The light cycles RED->GREEN->RED->...
 */
byte signal = 0;   /* starts RED */

/* LTL properties evaluated over ALL infinite executions of the model */

/* P1: The light eventually turns green  (basic liveness) */
ltl always_eventually_green { [] <> (signal == 1) }

/* P2: Whenever green, the NEXT step is red  (response) */
ltl green_before_red { [] (signal == 1 -> X (signal == 0)) }

/* P3 (INTENTIONALLY BAD): signal is always green -- will find counterexample */
ltl bad_property { [] (signal == 1) }

/* P4: The light is never both red and green simultaneously -- trivially true */
ltl never_both { [] !(signal == 0 && signal == 1) }


proctype TrafficLight() {
    do
    :: /* RED phase: stay red for 1-3 steps (nondeterministic duration) */
        signal = 0;
        printf("RED\n");
        if
        :: skip          /* 1 step */
        :: skip; skip    /* 2 steps */
        :: skip; skip; skip  /* 3 steps */
        fi

    :: /* GREEN phase: stay green for 1-3 steps */
        signal = 1;
        printf("GREEN\n");
        if
        :: skip
        :: skip; skip
        :: skip; skip; skip
        fi
    od
}

init {
    run TrafficLight()
    /* Note: no (_nr_pr == 1) -- model runs forever (required for liveness LTL) */
}

/*
 * IMPORTANT: The -f flag (weak fairness) is needed for liveness.
 * Without -f, SPIN might find a "counterexample" where the TrafficLight
 * process never gets scheduled -- which is unrealistic.
 * -f guarantees: if a process is continuously enabled, it eventually runs.
 *
 * Your traffic_signal.pml uses -f for the same reason:
 *   ./pan -a -f
 */
