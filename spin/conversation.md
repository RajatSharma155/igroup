# SPIN / Promela Learning Session
_ECEN723 Spring 2026 — Team 14_

---

## User: I want to install and learn spin model checking tool. Help me

**Status:** SPIN 6.5.2 available via Homebrew. Project already has `model_checking/traffic_signal.pml`.

**Install:**
```bash
brew install spin
spin -V
xcode-select --install   # for gcc
```

**Core workflow (3 commands every time):**
```bash
spin -a model.pml        # compile Promela → pan.c
gcc -o pan pan.c         # compile C → verifier
./pan -a                 # exhaustive state-space search
```

**Property types:**
- **Safety** — `assert(condition)` inside model: "bad thing never happens"
- **Liveness** — `ltl name { [] <> ... }`: "good thing eventually happens"

**Run the existing model:**
```bash
cd model_checking

# P1: Safety — at most one GREEN per intersection
spin -a traffic_signal.pml && gcc -o pan pan.c && ./pan -a

# P2: Liveness — demand eventually gets GREEN (needs weak fairness)
spin -a -N p2_int4_north traffic_signal.pml && gcc -o pan pan.c && ./pan -a -f

# P3: Bounded liveness — GREEN within 8 steps
spin -a -N p3_int4_north traffic_signal.pml && gcc -o pan pan.c && ./pan -a -f

# Replay a counterexample if found
spin -t traffic_signal.pml
```

**Output fields:**
| Field | Meaning |
|---|---|
| `errors: 0` | Property holds |
| `errors: N` | N counterexamples found |
| `states, stored` | Total reachable states explored |
| `depth reached` | Longest execution path |

**Key Promela concepts in `traffic_signal.pml`:**
| Concept | Example |
|---|---|
| Constants | `#define GREEN 1` |
| Global arrays | `byte sig[9][4]` |
| Process template | `proctype intersection(byte iid; byte vmask)` |
| Atomic block | `atomic{ ... }` — LTL sees consistent snapshots |
| Loop | `do :: ... od` |
| Nondeterministic choice | `if :: ... fi` — SPIN explores ALL branches |
| Safety | `assert(green_count <= 1)` |
| Liveness | `ltl p2_int4_north { [] (gdemand[4][NORTH]==1 -> <> (sig[4][NORTH]==GREEN)) }` |

---

## User: thanks, I installed spin. help me learn with SPIN and Promela

Created tutorial files in `spin/`:

### `01_basics.pml`
Variables (`bit`, `bool`, `byte`, `short`, `int`), `if/fi`, `do/od`, `printf`, `assert`.
```bash
spin 01_basics.pml                                              # simulate
spin -a 01_basics.pml && gcc -o pan pan.c && ./pan -a          # verify
```

### `02_processes.pml`
`proctype`, `run`, concurrent interleaving, guard statements (blocking on a condition).
```bash
spin 02_processes.pml         # run twice — output may differ (random schedule)
spin -a 02_processes.pml && gcc -o pan pan.c && ./pan -a
```

### `03_nondeterminism.pml`
Nondeterministic `if` and `do` — how SPIN models "any possible input".
This is exactly how `traffic_signal.pml` models V-group demand:
```promela
if
:: gdemand[iid][d] = 0
:: gdemand[iid][d] = 1
fi
```

### `04_channels.pml`
`chan`, `!` (send), `?` (receive), buffered vs synchronous channels.
```bash
spin 04_channels.pml
spin -a 04_channels.pml && gcc -o pan pan.c && ./pan -a
```

### `05_ltl.pml`
LTL operators: `[]` (always), `<>` (eventually), `X` (next), `U` (until), `->` (implies).

| Pattern | Meaning |
|---|---|
| `[] p` | safety: p is always true |
| `<> p` | liveness: p eventually true |
| `[] <> p` | recurrence: p happens infinitely often |
| `[] (p -> <> q)` | response: every p eventually followed by q |

```bash
# Liveness check (needs -f):
spin -a -N always_eventually_green 05_ltl.pml && gcc -o pan pan.c && ./pan -a -f
# Bad property (finds counterexample):
spin -a -N bad_property 05_ltl.pml && gcc -o pan pan.c && ./pan -a
```

---

## User: Show me examples for mutex, alternating bit protocol and peterson's algorithm

### `06_mutex.pml` — Mutual Exclusion
Dekker-style: `want[i]` flag + `turn` tie-breaker.

```bash
spin -a 06_mutex.pml && gcc -o pan pan.c && ./pan -a
spin -a -N no_starvation_0 06_mutex.pml && gcc -o pan pan.c && ./pan -a -f
spin -a -N no_starvation_1 06_mutex.pml && gcc -o pan pan.c && ./pan -a -f
```

Properties verified: `mutual_exclusion` (safety), `no_starvation_0/1` (liveness).

---

### `07_peterson.pml` — Peterson's Algorithm
Software-only mutex for 2 processes. No hardware atomics.

```
flag[me] = true          // "I want in"
turn     = other         // "but you go first"
!(flag[other] && turn == other)   // wait
[critical section]
flag[me] = false
```

```bash
spin -a 07_peterson.pml && gcc -o pan pan.c && ./pan -a
spin -a -N no_starvation_0 07_peterson.pml && gcc -o pan pan.c && ./pan -a -f
```

**Experiment:** swap `flag[me]=true` and `turn=other` — SPIN finds a safety violation proving the order is critical.

---

### `08_abp.pml` — Alternating Bit Protocol
Reliable delivery over a lossy channel. Loss modeled nondeterministically:

```promela
if
:: skip           /* drop */
:: ch ! msg, bit  /* deliver */
fi
```

Sender tags messages with alternating bit `b`; receiver accepts only if bit matches expected. Detects duplicates via wrong bit.

```bash
spin -a 08_abp.pml && gcc -o pan pan.c && ./pan -a
spin -a -N every_msg_delivered 08_abp.pml && gcc -o pan pan.c && ./pan -a -f
```

**Experiment:** comment out `sbit = 1 - sbit` in Sender — SPIN catches duplicate delivery.

---

## Mapping to `traffic_signal.pml`

| Concept | Classic example | In `traffic_signal.pml` |
|---|---|---|
| Mutual exclusion | `in_cs <= 1` | `green_count <= 1` (P1) |
| Starvation freedom | `[] (want[i] -> <> inside[i])` | `[] (demand==1 -> <> GREEN)` (P2) |
| Bounded wait | N/A | `[] (demand==1 -> GREEN within 8 steps)` (P3) |
| Nondeterministic env | packet loss `if :: skip :: ch!msg fi` | demand `if :: gdemand=0 :: gdemand=1 fi` |
| Atomic step | `atomic{}` | `atomic{}` wraps each simulation time step |
