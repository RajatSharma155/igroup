/*
 * 04_channels.pml  --  Message passing with channels
 *
 * Run:
 *   spin 04_channels.pml
 *   spin -a 04_channels.pml && gcc -o pan pan.c && ./pan -a
 *
 * Concepts: chan, !, ?, synchronous vs buffered channels
 *
 * Channels are Promela's primary inter-process communication mechanism.
 * They're useful for modeling request/response protocols -- exactly what
 * the V-group ↔ I-group interface is.
 */

/* ── Buffered channel: chan name = [capacity] of { type, type, ... } ─────── */
chan request  = [4] of { byte };   /* holds up to 4 messages of type byte  */
chan response = [4] of { byte };

/* ── Sender process ──────────────────────────────────────────────────────── */
proctype Sender() {
    byte i = 1;
    do
    :: i <= 3 ->
        request ! i;            /* send value i on channel 'request'  */
        printf("Sent: %d\n", i);
        i = i + 1
    :: i > 3 -> break
    od
}

/* ── Receiver process ────────────────────────────────────────────────────── */
proctype Receiver() {
    byte msg;
    byte count = 0;
    do
    :: request ? msg ->         /* receive one message into 'msg'      */
        printf("Received: %d\n", msg);
        response ! (msg * 2);   /* send back doubled value             */
        count = count + 1
    :: count >= 3 -> break
    od
}

/* ── Collector reads the responses ───────────────────────────────────────── */
proctype Collector() {
    byte val;
    byte i = 0;
    do
    :: i < 3 ->
        response ? val;
        printf("Response: %d\n", val);
        assert(val == 2 || val == 4 || val == 6);   /* doubled 1,2,3 */
        i = i + 1
    :: i >= 3 -> break
    od
}

init {
    run Sender();
    run Receiver();
    run Collector();
    (_nr_pr == 1)
}

/*
 * Synchronous (rendez-vous) channels: use capacity 0.
 *   chan sync = [0] of { byte }
 * Both sender and receiver must be ready simultaneously -- good for
 * modeling tight handshakes.
 *
 * Channel operations:
 *   ch ! val          send
 *   ch ? var          receive (blocks if empty)
 *   ch ? [var]        poll (non-blocking test, doesn't consume)
 *   len(ch)           number of messages currently in buffer
 *   empty(ch)         true if channel has 0 messages
 *   full(ch)          true if channel is at capacity
 */
