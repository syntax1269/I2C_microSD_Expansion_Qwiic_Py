# Status and Polling

The module is asynchronous: a command that returns an ACK has only been *accepted
into RAM*, not completed. This page explains how to know when an operation is
really finished, how to track commit progress, and how to recover from a host
reset. Everything here is derived from the 12-byte `STATUS` frame (`0x20`).

## The STATUS frame, field by field

`R [0x20] -> 12 bytes`:

| Offset | Field | Width | Use |
|---|---|---|---|
| 0 | `rev` | 1 | Protocol revision; `2` for rev 2 |
| 1 | `state` | 1 | Current state machine state |
| 2 | `opDone` | 1 | Sequence number of the last completed op |
| 3 | `error` | 1 | Error code of the last op |
| 4 | `rxFree` | 2 | Free RX bytes (LE) — write capacity |
| 6 | `txAvail` | 2 | Staged TX bytes (LE) — readable data waiting |
| 8 | `result` | 4 | Latched result / commit counter (LE), sticky |

### `state` machine

```
IDLE(0) -> ACCEPTED(1) -> BUSY_RX(2) -> BUSY_SD(3) -> TX_READY(4) -> COMPLETE(5)
                                                                  \-> ERROR(6)
                                                                  \-> OVERFLOW(7)
```

- `ACCEPTED` — payload copied into RAM; work queued.
- `BUSY_RX` — consuming RX bytes.
- `BUSY_SD` — worker talking to the SD card over SPI.
- `TX_READY` — response bytes staged; master should drain them.
- `COMPLETE` — operation finished successfully.
- `ERROR` / `OVERFLOW` — finished with a failure; check `error`.

Note that a fast host may never observe all intermediate states. Always poll
until you see a **terminal** state (`COMPLETE`, `ERROR`, `OVERFLOW`).

## Rule 1: `opDone` tells you *when* an op finished

`opDone` is an 8-bit counter incremented each time an operation completes. The
correct pattern is:

```
1. prev = STATUS.opDone                 # capture BEFORE submitting the command
2. submit command (write/STOP)
3. poll STATUS until opDone != prev     # counter advanced → op finished
4. inspect state and error
```

Compare with **inequality**, never `>`: the counter wraps from 255 to 0.

```python
def wait_done(prev, timeout_ms=15000, poll_ms=2):
    deadline = millis() + timeout_ms
    while millis() < deadline:
        st = cmd_read(0x20, 12)
        if st[2] != prev:               # opDone advanced
            return st
        sleep_ms(poll_ms)
    raise TimeoutError
```

If you capture `opDone` *after* submitting, you can miss the transition entirely
if the operation completes between the submit and the read.

## Rule 2: `result` tells you *what* the op produced

`STATUS.result` is a sticky latch, updated when an operation completes and held
until the next operation begins. Two uses:

### Query results

`FILE_SIZE`, `FILE_EXISTS`, and `IS_DIRECTORY` write their answer into `result`.
Read it only *after* `opDone` advances:

```
W [0x01, ...path...]          # FILENAME
prev = opDone; W [0x05]       # FILE_SIZE
wait_done(prev)
size = le32(STATUS.result)    # valid NOW; garbage before completion
```

### Write commit progress

For streaming writes, `result` is a running total of bytes committed to the card
this boot. It advances in the background as the module flushes its RAM buffers.
Therefore:

```
baseline = STATUS.result          # before writing anything
... push all WRITE blocks ...
while STATUS.result < baseline + total_bytes:
    wait a few ms                  # still flushing to card
# only now is the data durable
```

This is why the library's `close()` and `sync()` can promise "returns only once
it is on the card". An ACK on the last `WRITE` is **not** enough.

## Flow control: handling NACKs on WRITE

Each WRITE transaction owns one 128-byte RX buffer and STOP publishes it. When
both buffers are busy draining to the card, the module NACKs the next WRITE.

```
st = STATUS
if st.state in (BUSY_RX, BUSY_SD):   # buffers busy → expected NACK
    sleep_ms(flow_poll_ms)           # retry the SAME block later
elif st.state == ERROR or st.error in (3, 6):
    abort                            # real card/buffer error
```

Do not poll STATUS before *every* block — that costs a bus turnaround (~1.3 ms at
1 MHz, about the wire time of a 128-byte block) and roughly a third of the
throughput. Push until the module NACKs, *then* consult STATUS.

## Timeout scaling

The base operation timeout is 15 s. It scales with the bus clock:

```
effective = max(base, base * 100000 / scl_hz)
```

and below 50 kHz it is doubled; the ceiling is 120 s. The point: worker time does
not track the bus clock, so the timeout must never shrink below the fixed floor.
`FORMAT` uses its own 300 s budget because rebuilding a FAT table on a large card
takes tens of seconds.

## Abrupt recovery: what happens after the host disappears

The module watches for bus silence. After **5 seconds** with no activity it:

1. flushes pending bytes,
2. closes the open file cleanly (FAT left consistent, card not busy),
3. advances `opDone`.

That means after a host crash or reset you can read STATUS, see that the op
completed, and resume without a corrupt filesystem. The host libraries exploit
this with a **CLOSE_FLUSH barrier gated on a >4 s activity gap**: if more than
4 s of silence happened, the first wait after a crash assumes the module may
have closed the file itself, so the counter is not mis-tracked.

For a raw driver, the equivalent rule is: treat a long idle gap as a possible
implicit close; read STATUS first and re-synchronize `opDone` from it before
issuing new commands.

## Debugging checklist

| Observation | Interpretation |
|---|---|
| `state == 1` forever | Worker stuck; check for a card error, try `REBOOT` |
| `state == 7` | RX overflow; you pushed after a NACK — slow down |
| `result` not advancing | Worker busy with SD, or a card error (`error == 3`) |
| `opDone` advanced but `error != 0` | Op completed with failure; decode `error` |
| First file after reset is slow | Card re-training; time subsequent files |
| Everything stalled after a long gap | Re-read STATUS, resync opDone (auto-close may have occurred) |

## See also

- [Protocol Reference](Protocol-Reference.md#3-status-frame-the-heartbeat-of-every-operation) — frame layout
- [File Operations](File-Operations.md) — write sequences using these rules
- [Error Codes](Error-Codes.md)
