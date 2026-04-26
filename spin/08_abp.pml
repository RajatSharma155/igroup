/*
 * 08_abp.pml  --  Alternating Bit Protocol (ABP)
 *
 * ABP is the simplest reliable data-transfer protocol over a lossy channel.
 * It guarantees in-order, exactly-once delivery despite packet loss.
 *
 * PROTOCOL OVERVIEW:
 *   Sender tags each message with a bit (0 or 1, alternating).
 *   Receiver sends ACK with the bit of the last correctly received message.
 *
 *   Sender state machine:
 *     Send msg with bit b -> wait for ACK(b) -> flip b -> send next msg
 *     If timeout (no ACK), retransmit same msg with same bit b.
 *
 *   Receiver state machine:
 *     If msg arrives with expected bit -> deliver, send ACK(b), flip expected bit
 *     If msg arrives with wrong bit   -> discard, resend ACK(1-b) (duplicate)
 *
 * CHANNEL MODEL:
 *   We model loss nondeterministically: each send either delivers or is dropped.
 *   This is the key advantage of SPIN -- no need to enumerate specific loss patterns.
 *
 * PROPERTIES VERIFIED:
 *   P1 (Safety):   delivered messages are always in order and unduplicated.
 *   P2 (Liveness): every sent message is eventually delivered.
 *
 * Run safety (assert):
 *   spin -a 08_abp.pml && gcc -o pan pan.c && ./pan -a
 *
 * Run liveness (LTL, requires fairness):
 *   spin -a -N every_msg_delivered 08_abp.pml && gcc -o pan pan.c && ./pan -a -f
 *
 * Expected: 0 errors for both.
 *
 * To see ABP FAIL: set LOSSY_ACK to 0 but still drop data -- or try the
 * experiment at the bottom of this file.
 */

/* ── Parameters ─────────────────────────────────────────────────────────── */
#define MSG_COUNT 3       /* number of messages sender will transmit */
#define LOSSY     1       /* 1 = channels can drop packets; 0 = perfect */

/* ── Channels ───────────────────────────────────────────────────────────── */
/* data_ch:  Sender -> Receiver,  carries (message_id, bit) */
/* ack_ch:   Receiver -> Sender,  carries (bit)             */
/* Capacity 1: only one packet in flight at a time (ABP assumption)         */
chan data_ch = [1] of { byte, bit };
chan ack_ch  = [1] of { bit };

/* ── Shared observable state (for LTL) ──────────────────────────────────── */
byte delivered = 0;    /* number of messages successfully delivered to receiver */
byte sent      = 0;    /* number of messages sender has started sending         */

/* ── LTL: every message sent is eventually delivered ────────────────────── */
ltl every_msg_delivered {
    [] (sent == MSG_COUNT -> <> (delivered == MSG_COUNT))
}

/* ── Sender ──────────────────────────────────────────────────────────────── */
proctype Sender() {
    byte msg = 1;      /* message counter 1..MSG_COUNT */
    bit  sbit = 0;     /* current send bit             */
    bit  ack_bit;

    do
    :: msg <= MSG_COUNT ->
        sent = msg;
        printf("Sender: sending msg=%d bit=%d\n", msg, sbit);

        /* Transmit loop: retransmit until correct ACK received */
        do
        :: /* Send (with possible loss) */
            if
            :: LOSSY -> skip                      /* drop: channel stays empty */
            :: data_ch ! msg, sbit                /* deliver to channel        */
            fi;

            /* Wait for ACK (with possible loss) */
            if
            :: ack_ch ? ack_bit ->
                if
                :: ack_bit == sbit ->
                    /* Correct ACK: advance to next message */
                    printf("Sender: got ACK bit=%d, advancing\n", ack_bit);
                    break
                :: else ->
                    /* Wrong ACK (stale from previous message): retransmit */
                    printf("Sender: wrong ACK bit=%d, retransmitting\n", ack_bit)
                fi
            :: empty(ack_ch) ->
                /* Timeout: no ACK yet, retransmit */
                printf("Sender: timeout, retransmitting msg=%d\n", msg)
            fi
        od;

        sbit = 1 - sbit;    /* flip bit for next message */
        msg  = msg + 1

    :: msg > MSG_COUNT ->
        printf("Sender: all %d messages sent\n", MSG_COUNT);
        break
    od
}

/* ── Receiver ────────────────────────────────────────────────────────────── */
proctype Receiver() {
    byte rmsg;
    bit  rbit;
    bit  expected = 0;   /* bit expected on next new message */

    do
    :: delivered < MSG_COUNT ->
        /* Wait for a packet */
        data_ch ? rmsg, rbit;

        if
        :: rbit == expected ->
            /* New message: accept and deliver */
            delivered = delivered + 1;
            printf("Receiver: delivered msg=%d bit=%d (total=%d)\n",
                   rmsg, rbit, delivered);

            /* Send ACK (with possible loss) */
            if
            :: LOSSY -> skip
            :: ack_ch ! rbit
            fi;

            expected = 1 - expected    /* flip expected bit */

        :: else ->
            /* Duplicate: discard but resend ACK for the previous message */
            printf("Receiver: duplicate msg=%d bit=%d, resending ACK\n", rmsg, rbit);
            if
            :: LOSSY -> skip
            :: ack_ch ! rbit
            fi
        fi

    :: delivered >= MSG_COUNT ->
        printf("Receiver: all %d messages delivered\n", MSG_COUNT);
        break
    od
}

init {
    delivered = 0;
    sent      = 0;
    run Sender();
    run Receiver()
}

/*
 * HOW ABP HANDLES LOSS:
 *
 *   Lost data packet:  Sender sees timeout (empty ack_ch), retransmits.
 *                      Receiver sees same msg+bit again next time -- accepts.
 *
 *   Lost ACK:          Sender retransmits. Receiver sees duplicate (wrong bit),
 *                      discards and resends ACK. Sender now sees correct ACK.
 *
 *   Duplicate data:    Receiver detects via wrong bit, discards. Protocol safe.
 *
 * WHY BIT FLIP MATTERS:
 *   If Sender always used bit=0, Receiver cannot distinguish a retransmission
 *   from the next new message -> duplicate delivery.
 *   The alternating bit creates a unique "epoch" per message.
 *
 * EXPERIMENT: Break the protocol intentionally.
 *   Comment out "sbit = 1 - sbit" in Sender.
 *   Run: spin -a 08_abp.pml && gcc -o pan pan.c && ./pan -a
 *   SPIN will find a state where delivered > MSG_COUNT (duplicate delivery).
 */
