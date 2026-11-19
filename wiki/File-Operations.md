# File Operations Over Raw I²C

This page shows the exact command sequences to create, write, read, and manage
files **without a host library**. All byte values are command bytes from the
[Protocol Reference](Protocol-Reference.md); multi-byte fields are little-endian.

## The two file APIs

| API | Commands | Use when |
|---|---|---|
| Legacy one-shot | `FILENAME` `0x01`, `WRITE_FILE` `0x02`, `READ_FILE` `0x03`, `APPEND_FILE` `0x04` | Small files that fit one transaction; simplest code |
| Streaming (rev 2) | `OPEN_WRITE` `0x21`, `WRITE` `0x22`, `READ` `0x23`, `CLOSE_FLUSH` `0x24`, `OPEN_READ` `0x25` | Large files, logging, bounded RAM |

Only **one file can be open at a time**. The legacy commands open and close
implicitly; the streaming commands require you to close explicitly.

---

## 1. Write a small file (legacy)

```
W [0x01, ...path bytes...]        # FILENAME: store path, e.g. "HELLO.TXT"
W [0x02, ...data...]              # WRITE_FILE: create/truncate, write, close
st = wait_done(prev_opdone)        # poll STATUS until opDone advances
assert st.state == 5 and st.error == 0   # COMPLETE
```

For an append instead of a truncate, use `0x04` (`APPEND_FILE`).

The data is committed to the card by the time the operation reports COMPLETE, so
no explicit close is needed. Keep each transaction within your platform's
maximum I²C write length (typically 32 bytes on Linux SMBus, 128 on `Wire`).

---

## 2. Write a large file (streaming)

This is the path the host libraries use. The module has two 128-byte RX buffers
(256 bytes of staging), and it NACKs a WRITE when they are full.

### Step 1 — open

```
prev = read(STATUS).opDone                        # capture BEFORE submitting
W [0x21, ...path bytes...]                        # OPEN_WRITE (create/truncate)
st = wait_done(prev)                              # poll STATUS
if st.error == 2:  path was invalid (OPEN error)
```

### Step 2 — push data, with commit tracking

Before the first block, note the current committed-byte baseline:

```
baseline = read(STATUS).result                    # bytes committed so far this boot
```

Then push blocks. Each block is one transaction ending in STOP:

```
for each block of up to 128 bytes:
    prev = read(STATUS).opDone
    while True:
        if write_transaction(0x22, block) succeeds (ACK):
            break
        # NACK = RX buffers full → flow control, not an error
        st = read(STATUS)
        if st.state == 6 or st.error in (1,3,5):  # real error → abort
            fail(st)
        short_pause(2)                            # e.g. 2 ms, then retry SAME block
    wait_done(prev)                               # optional: per-block completion
```

**Important:** an ACK only means "copied into RAM". After the last block, wait
until the card has actually committed everything:

```
target = baseline + total_bytes_written
while read(STATUS).result < target:
    short_pause(5)
st = read(STATUS)
if st.state == 6 or st.error == 3:  fail(st)      # card error
```

`STATUS.result` is a sticky, cumulative byte counter — read it after the writes,
not before. This is what makes `close()` safe on sudden power loss.

### Step 3 — close

```
prev = read(STATUS).opDone
W [0x24]                                          # CLOSE_FLUSH
wait_done(prev)
```

`CLOSE_FLUSH` flushes pending bytes and closes the file. Do not send any other
command until it completes.

---

## 3. Read a file (streaming)

The module stages read data in two staggered 128-byte TX buffers, so one drain
can return up to 256 bytes.

```
prev = read(STATUS).opDone
W [0x25, ...path bytes...]                        # OPEN_READ
wait_done(prev)                                   # check error == 0

out = bytearray()
while True:
    chunk = R [0x23] -> up to 256 bytes           # drain one chunk
    out += chunk
    st = read(STATUS)                             # STATUS
    if st.state == 5:  break                      # COMPLETE → EOF
    if st.state == 6:  fail(st)                   # ERROR
    # otherwise more bytes are staged → drain again

W [0x24]                                          # CLOSE_FLUSH
```

`READ` (`0x23`) is dual-purpose: a *write* to it requests a block, and a *read*
from it drains the staged bytes. Always issue the request before reading.

To size a read in advance, use `FILE_SIZE` (`0x05`) — see §5. Then you know
exactly how many bytes to drain and can stop at that count.

---

## 4. Read a small file (legacy)

```
W [0x01, ...path bytes...]        # FILENAME
W [0x03]                           # READ_FILE: open + stream
loop:
    data = R [0x03] -> up to 256 bytes
    st = read(STATUS)
until st.state == 5 (EOF) or st.state == 6 (error)
```

---

## 5. Queries and directory operations

All queries set the path first with `FILENAME` (`0x01`), issue the command, wait
for completion, then read the latched value from `STATUS.result` (offset 8, LE).

| Query | Cmd | `STATUS.result` after completion |
|---|---|---|
| `FILE_SIZE` | `0x05` | 4-byte file size |
| `FILE_EXISTS` | `0x06` | 1 = exists, 0 = missing |
| `IS_DIRECTORY` | `0x07` | 1 = directory, 0 = file |

```
W [0x01, ...path...]
prev = opDone; W [0x05]; wait_done(prev)
size = le32(read(STATUS)[8:12])
```

Directory mutation commands (no result, just completion):

```
W [0x01, ...path...]; W [0x09]     # MAKE_DIR
W [0x01, ...path...]; W [0x0A]     # REMOVE_DIR (empty only)
W [0x01, ...path...]; W [0x0B]     # REMOVE_FILE
```

### Listing a directory

```
W [0x01, '/']                       # FILENAME = "/" (or any directory)
W [0x08]                            # LIST_DIR
wait_done(...)
loop:
    b = R [0x08] -> 1 byte
    if b == 0xFF: break             # end of stream
    kind = 'D' if b == 'D' else 'F'
    name = read_until(0x00)         # NUL-terminated basename
    size = read(4) as LE32          # 0 for directories
```

An empty directory yields a single `0xFF`. A missing path, or a file used as a
directory, produces `state == ERROR` with no stream.

---

## 6. Path rules

- `/` is the separator; `DIR/FILE` and `/DIR/FILE` are equivalent.
- Comparison is case-insensitive (8.3 semantics).
- A trailing `/` denotes a directory.
- Long filenames up to **259 characters** work on full builds; the tiny build
  is strict 8.3 with one slash. Enforce the limit in your host before sending.

---

## 7. Formatting (destructive)

```
W [0x28, 0x00]                      # FORMAT, mode 0 = auto (1 = force FAT)
# Formatting can take tens of seconds. Use a long timeout (≈300 s),
# not the normal 15 s operation timeout.
wait_done(prev, timeout_ms=300000)
```

`FORMAT` destroys all data on the card. Check `CARD_INFO` afterwards.

---

## 8. Robustness notes

- **ACK ≠ committed** — always gate on `STATUS.result` for writes.
- The module auto-flushes and closes after **5 seconds** of total bus silence,
  advancing `opDone` while the master is gone. This makes recovery after a host
  crash possible: read STATUS, resume with the counters it reports.
- The libraries gate their close barrier on a **>4 s** activity gap so the first
  wait after a crash is never mis-tracked. In a raw driver, treat a long idle gap
  as "the module may have already closed the file".
- A redundant `CLOSE_FLUSH` when no file is open returns `NO_FILE` — harmless.

## See also

- [Direct I²C Guide](Direct-I2C-Guide.md)
- [Status and Polling](Status-and-Polling.md) — the completion algorithm in full
- [Protocol Reference](Protocol-Reference.md)
- [Error Codes](Error-Codes.md)
