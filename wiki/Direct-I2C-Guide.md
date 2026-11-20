# Direct I²C Guide

This page walks through the mechanics of talking to the module without a host
library. It assumes you can already send and receive raw I²C transactions on
your platform (Linux `ioctl(I2C_RDWR)`, Arduino `Wire`, MicroPython
`machine.I2C`, etc.).

If you are not sure which command to send, start with the
[Protocol Reference](Protocol-Reference.md).

## 1. The minimal exchange

Every command is a single transaction:

1. Master issues START, writes the module address (with R/W bit = 0).
2. Master writes the **command byte**.
3. Depending on the command:
   - **Write commands:** master writes zero or more payload bytes, then STOP.
   - **Read commands:** master issues a **repeated START**, writes the address
     with R/W = 1, and clocks in the response; STOP when done.

```python
# Pseudocode — adapt to your platform's I2C API.
def cmd_write(payload):
    i2c.write_to(0x6E, payload)          # START, addr+W, payload..., STOP

def cmd_read(command, count):
    i2c.write_to(0x6E, [command])         # START, addr+W, cmd, NO STOP
    return i2c.read_from(0x6E, count)     # repeated START, addr+R, count, STOP
```

Most read commands can be issued repeatedly to drain successive chunks; the
`STATUS` frame tells you when there is more data.

### A first conversation

```
R 0x6E [0x0F] -> up to 112 bytes       # VERSION → firmware banner
R 0x6E [0x20] -> 12 bytes              # STATUS → rev, state, ...
R 0x6E [0x29] -> 24 bytes              # CARD_INFO → is a card mounted?
```

Decoding STATUS: byte 0 should be `0x02` (protocol revision 2). Byte 1 is the
state; `5` = COMPLETE, `6` = ERROR. See [Protocol Reference](Protocol-Reference.md#3-status-frame-the-heartbeat-of-every-operation).

## 2. Write transactions and STOP

For write commands, **STOP is significant**. The module latches the payload when
it sees the STOP condition, so a transaction must contain the command byte and
its whole payload followed by one STOP. Splitting a `WRITE` payload across two
STOPs sends two separate WRITE operations.

Clock stretching is normal: the module pulls SCL low only while it copies a byte
into RAM or stages a response — typically **well under ~10 µs per byte**. Any
spec-compliant I²C master must support it. `FORMAT` is a long *operation*, but it
does not hold SCL low the whole time; poll STATUS for completion.

> **Raspberry Pi hosts:** the Broadcom BSC controller (BCM2835–BCM2711,
> Pi 4 and earlier) has a **silicon bug** with clock stretching. Add
> `dtoverlay=i2c-gpio` to `/boot/config.txt` to use the bit-banged bus, or use a
> Pi 5 (RP1 / Synopsys DesignWare I²C), which is unaffected. See
> [Clock stretching and Raspberry Pi hosts](Protocol-Reference.md#clock-stretching-and-raspberry-pi-hosts).

## 3. Two ways to write a file

The module offers two file APIs. Pick the one that fits your host.

### a) Legacy one-shot API — easiest

```
W 0x6E [0x01, 'D','A','T','A','.','T','X','T']     # FILENAME
W 0x6E [0x02, ...payload...]                       # WRITE_FILE: create, write, close
```

`APPEND_FILE` (`0x04`) is identical but appends. When the op completes, read
STATUS and check `state == COMPLETE` and `error == 0`. This path is fine for
small files that fit in one transaction; it is limited by your host's maximum
I²C write length.

### b) Streaming API — for anything large

```
W [0x21, 'L','O','G','.','C','S','V']    # OPEN_WRITE (create/truncate)
# poll STATUS until opDone advances, error == 0
W [0x22, ...up to 128 payload bytes...] # WRITE; repeat, watching for NACK
# poll STATUS until result >= bytes_written (commit to card)
W [0x24]                                # CLOSE_FLUSH; poll until opDone advances
```

The module NACKs a `WRITE` when its RX buffers are full. A NACK is *flow control*,
not an error: read STATUS to confirm `state == BUSY_RX`/`BUSY_SD`, wait, and retry
the same block. See [File Operations](File-Operations.md) for the full sequence.

## 4. Reading a file

### Legacy

```
W [0x01, 'D','A','T','A','.','T','X','T']  # set FILENAME
W [0x03]                                   # READ_FILE
# repeatedly R [0x03] -> up to 256 bytes until state == COMPLETE
```

### Streaming

```
W [0x25, 'L','O','G','.','C','S','V']      # OPEN_READ
# poll until opDone advances
loop:
    R [0x23] -> up to 256 bytes            # drain one chunk
    R [0x20] -> 12 bytes                   # check state / txAvail
until state == COMPLETE (EOF)
W [0x24]                                   # CLOSE_FLUSH
```

## 5. Querying without opening a file

```
W [0x01, 'D','A','T','A','.','B','I','N']  # FILENAME
W [0x05]                                   # FILE_SIZE
# poll until opDone advances, then:
R [0x20] -> 12 bytes                       # result (offset 8) = size, LE
```

`FILE_EXISTS` (`0x06`) and `IS_DIRECTORY` (`0x07`) work the same way: set the
filename, issue the command, wait for completion, then read `STATUS.result` (a
single byte, `1` or `0`).

## 6. Waiting for completion — the essential loop

```python
def wait_done(previous_opdone, timeout_ms=15000):
    deadline = now() + timeout_ms
    while now() < deadline:
        st = cmd_read(0x20, 12)             # STATUS
        state, opdone, error = st[1], st[2], st[3]
        if state in (5, 6, 7):              # COMPLETE / ERROR / OVERFLOW
            if opdone != previous_opdone:   # counter advanced → op finished
                return st
        short_pause(2)                       # e.g. 2–10 ms
    raise TimeoutError("module did not finish")
```

Capture `opDone` **before** submitting the command; the counter is 8-bit and
wraps, so compare for *inequality*, not "greater than". For writes, additionally
wait on `STATUS.result` reaching the committed-byte target. Full detail is in
[Status and Polling](Status-and-Polling.md).

## 7. Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Read returns stale bytes | Didn't wait for opDone to advance | Always capture opDone before submit and poll |
| Write returns `OVERFLOW` | Pushed after module NACK | Treat NACK as flow control; poll STATUS and retry |
| `FILE_SIZE` returns 0 | Read `result` before op completed | Poll STATUS first; `result` latches on completion |
| Last pixels stay lit | Sent I²C during a bit-bang frame | Keep the bus quiet for the whole frame duration |
| `version()` returns a clock number | Parsed first line of new banner | Scan for the dotted version token |
| Card not mounted | exFAT or unformatted card | Reformat FAT16/FAT32; check `CARD_INFO.mounted` |

## 8. Recommended setup

- Use **1 MHz** if your host and wiring support it; fall back to 400 kHz or
  100 kHz. Timeout scaling is automatic in the libraries; in a raw driver use
  the formula in the [Protocol Reference](Protocol-Reference.md#9-timeout-scaling).
- Use a short, well-decoupled power lead and a common ground.
- Keep the bus quiet during bit-bang frames (no other transactions).
- Read `CARD_INFO.sck_hz` once at startup to know what throughput to expect.

## See also

- [Protocol Reference](Protocol-Reference.md) — complete command/frame tables
- [File Operations](File-Operations.md)
- [Expansion Pins](Expansion-Pins.md)
- [Bit-Bang Engine](Bit-Bang-Engine.md)
