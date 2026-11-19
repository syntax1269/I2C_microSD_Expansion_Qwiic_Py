# Error Codes and Troubleshooting

This page covers the error values you will see from the module and from the host
buses, and how the three host libraries normalize them.

## Host-library error enum

All three libraries expose a single normalized error enum. The numeric values are
identical across Arduino (`MicroSDExpError`), CircuitPython
(`MicroSDExpError`), and Qwiic Python (`MicroSDExpError`):

| Value | Name | Meaning |
|---|---|---|
| 0 | `OK` | No error |
| 1 | `NO_MODULE` | Module not responding |
| 2 | `NO_FILE` | No file open |
| 3 | `OPEN_FAIL` | Open rejected (bad path) |
| 4 | `CARD_ERR` | Card / filesystem error |
| 5 | `QUEUE_FULL` | Module request queue full |
| 6 | `INVALID` | Bad argument or malformed request |
| 7 | `OVERFLOW` | Module buffers full |
| 8 | `TIMEOUT` | Operation timed out |

`lastError()` (Arduino), `last_error` (Python) and `fileOpen()` / `file_open`
expose the most recent result and whether a file is currently open.

## Module `STATUS.error` values

The module reports its own error byte in `STATUS` (offset 3). These map onto the
same host enum:

| Value | Module name | Maps to | Meaning |
|---|---|---|---|
| 0 | `NONE` | `OK` | No error |
| 1 | `NO_FILE` | `NO_FILE` | Read/write with no file open |
| 2 | `OPEN` | `OPEN_FAIL` | OPEN failed (invalid path) |
| 3 | `CARD` | `CARD_ERR` | Filesystem / card failure |
| 4 | `QUEUE` | `QUEUE_FULL` | Request queue full |
| 5 | `INVALID` | `INVALID` | Malformed request |
| 6 | `OVERFLOW` | `OVERFLOW` | RX buffers full; bytes NACKed |

`STATUS.state == ERROR` or `OVERFLOW` means the operation finished with a failure;
decode the `error` byte for the cause.

## I²C bus (`Wire`) error normalization

Different cores number their I²C errors differently; the libraries normalize them:

| Bus code | Meaning | Normalized to |
|---|---|---|
| 0 | OK | `OK` |
| 1 | Data too long | `OVERFLOW` |
| 2 | NACK on address | `NO_MODULE` |
| 3 | NACK on data | `INVALID` |
| 4 | Other bus error | `CARD_ERR` |
| 5 | Bus timeout | `TIMEOUT` |

ESP32 adds a code `4`; AVR / Pico / SAMD share the `0`–`4` range. The library
maps them consistently so your code sees the same enum on every platform.

## Sticky errors

`last_error` / `lastError()` is the result of the most recent call and can be
overwritten by internal traffic (for example, a `list_dir()` drain). Use
`sticky_error` / `stickyError()` for the first failure since
`clear_error()` / `clearError()` when you need a fault that internal calls
cannot hide.

## Troubleshooting table

| Symptom | Likely cause | Fix |
|---|---|---|
| `begin()` returns false | Wrong address, no common ground, or a stuck bus | Scan for `0x6E`; ensure common GND; power from 3.3 V **or** 5 V, never both |
| Small file OK, large file truncates | Brown-out under SD write load | Power the module from one supply only; use short, decoupled wiring |
| `TIMEOUT` | Bus too slow for the operation | Lower speed to 100/400 kHz, or raise the timeout (remember timeout scaling) |
| `OVERFLOW` | Writing faster than the module can commit | Slow down; the library flow-paces automatically — treat NACK as flow control |
| Card not mounted | exFAT card, or unformatted card | Reformat to FAT16/FAT32; check `CARD_INFO.mounted` and `fat_type` |
| `OPEN_FAIL` on a path | Path too long, or illegal characters | Enforce ≤259 chars; use `/` separators; check trailing-`/` directory semantics |
| Read returns stale / short data | Didn't wait for `opDone` to advance | Capture `opDone` before submit and poll STATUS |
| `FILE_SIZE` returns 0 | Read `result` before completion | Poll STATUS until `opDone` advances, then read the latch |
| Strip stays dark | Pin not a digital output, or wrong data pin | Set mode `0` first; check the strip's DIN wiring and level |
| Last pixels show old color | Command reached module mid-frame | Keep the bus quiet for a frame time after `EXECUTE` |
| First file after reset is slow | Card re-training | Time files after the first; a `reboot()` restores full speed |
| Throughput collapses in both directions | Module in a degraded runtime state | `reboot()` the module (`format()` does not clear it) |
| Everything stalled after a long gap | Module may have auto-closed the file | Read STATUS and resynchronize `opDone` (see [Status and Polling](Status-and-Polling.md)) |

## Bus-busy recovery

If a NACK or timeout leaves SDA stuck low, `begin()` performs probing
transactions and an address scan (`0x6E`, then `0x6A`–`0x6F`). A true 9-clock +
STOP recovery requires wiggling the SDA/SCL pins, which the `Wire` abstraction
cannot express; on platforms that expose the raw pins you can implement it
yourself.

## See also

- [Status and Polling](Status-and-Polling.md) — how errors are detected
- [Protocol Reference](Protocol-Reference.md#3-status-frame-the-heartbeat-of-every-operation) — frame fields
- [Direct I²C Guide](Direct-I2C-Guide.md#7-common-pitfalls)
