/*
 * 01_basics.pml  --  Promela fundamentals
 *
 * Run:
 *   spin 01_basics.pml                  # simulate (random walk, prints output)
 *   spin -a 01_basics.pml && gcc -o pan pan.c && ./pan -a   # verify
 *
 * Concepts: variables, types, if/fi, do/od, printf, assert
 */

/* ── 1. Variable types ──────────────────────────────────────────────────────
 *
 *   bit      0..1          (1 byte stored, 1-bit range)
 *   bool     false/true    (alias for bit)
 *   byte     0..255
 *   short   -32768..32767
 *   int     full 32-bit signed
 *
 * Global variables are shared across all processes.
 */
byte  counter = 0;
bool  flag    = false;

/* ── 2. init process ────────────────────────────────────────────────────────
 *
 * Every model must have an init block.
 * init runs first and can start other processes with run().
 */
init {
    /* ── if / fi : selection (like switch/case) ── */
    if
    :: counter == 0 -> printf("counter starts at zero\n")
    :: counter  > 0 -> printf("counter is positive\n")
    fi;

    /* ── do / od : loop ── */
    do
    :: counter < 5 ->
        counter = counter + 1;
        printf("counter = %d\n", counter)
    :: counter >= 5 -> break
    od;

    assert(counter == 5);   /* safety: SPIN verifies this for every path */
    printf("done. counter = %d\n", counter)
}
