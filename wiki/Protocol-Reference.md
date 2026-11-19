# Wire Protocol Reference

This page is the authoritative reference for communicating with the I²C microSD
Expansion module **directly**, without any of the host libraries. Everything on
this page applies equally to the Arduino, CircuitPython, and Qwiic Python ports —
the module speaks one protocol, and each library is just a convenient wrapper
around it.

If you are using a library, you can skip this page. If you want to write your own
driver, this is where to start.

## 1. Bus basics

| Property | Value |
|---|---|
| Default I²C address | `0x6E` (7-bit) |
| Re-addressable range | `0x6A`–`0x6F` (command `0x16`) |
| I²C speeds | 100 kHz (Sm), 400 kHz (Fm), 1 MHz (Fm+) |
| Logic levels | 3.3 V and 5 V tolerant on the bus (module has level shifting) |
| Addressing | 7-bit, standard I²C |
| Transaction style | One command per transaction |

The module is a **single-master peripheral**: it never clocks the bus on its own.
Every exchange begins with the master writing a command byte; reads use a
repeated START after that command byte.

### Transaction notation used in this wiki

```
W addr [ cmd, payload... ]        write transaction (STOP at end)
R addr [ cmd ] -> n bytes         write cmd, repeated START, read n bytes
```

A "clock stretch" (the module holding SCL low) is normal while it copies a
payload into RAM or stages a response. Allow stretches of at least a few
milliseconds; a full card format can stretch much longer.

### The two transaction shapes

1. **Command with payload (write).** Master writes the command byte followed by
   its payload, then STOPs. The module copies the payload into RAM and begins the
   operation asynchronously. `STOP` is what "publishes" a WRITE block; there is
   no separate "go" byte.
2. **Command with response (read).** Master writes only the command byte, issues
   a **repeated START**, then reads the response bytes. Reads that stream data
   (STATUS, CARD_INFO, READ_FILE, LIST_DIR, VERSION) are repeated until the
   module reports completion.

Some commands (pin control, `SAVEEEPROM`, `FORMAT`, `REBOOT`) take no payload and
are sent as a bare command byte + STOP.

## 2. Command map

All values are hexadecimal command bytes. "R" means the command is followed by a
read; "W" means it is followed by a payload write.

### Legacy file family (simple, one-shot)

| Cmd | Name | Dir | Payload / response |
|---|---|---|---|
| `0x01` | `FILENAME` | W | Filename bytes; STOP stores the path |
| `0x02` | `WRITE_FILE` | W | Payload; create/overwrite, write, close in one op |
| `0x03` | `READ_FILE` | R | Opens the stored path and streams bytes via TX buffers |
| `0x04` | `APPEND_FILE` | W | Payload; append, write, close in one op |
| `0x05` | `FILE_SIZE` | R | Size (4 B LE) latched in `STATUS.result` |
| `0x06` | `FILE_EXISTS` | R | `1` = exists, `0` = not found, in `STATUS.result` |
| `0x07` | `IS_DIRECTORY` | R | `1` = directory, `0` = file, in `STATUS.result` |
| `0x08` | `LIST_DIR` | R | Entry stream (see §6) |
| `0x09` | `MAKE_DIR` | W | Create directory at stored path |
| `0x0A` | `REMOVE_DIR` | W | Remove empty directory |
| `0x0B` | `REMOVE_FILE` | W | Delete file at stored path |
| `0x0E` | `CLOCK_SET` | W | 6 bytes `[Y, M, D, h, m, s]`; STOP applies |
| `0x0F` | `VERSION` | R | Version string (see §7) |

`0x0C` and `0x0D` are unused.

### Expansion pins and housekeeping

| Cmd | Name | Dir | Payload / response |
|---|---|---|---|
| `0x10` | `PA5_SET_MODE` | W | 1 B mode (`0` = digital output) |
| `0x11` | `PA5_CONTROL` | W | Mode-dependent control value |
| `0x12` | `PB2_SET_MODE` | W | 1 B mode |
| `0x13` | `PB2_CONTROL` | W | Mode-dependent control value |
| `0x14` | `PB3_SET_MODE` | W | 1 B mode |
| `0x15` | `PB3_CONTROL` | W | Mode-dependent control value |
| `0x16` | `I2C_SET_ADDR` | W | 1 B new address (`0x6A`–`0x6F`) |
| `0x17` | `TEMP_READ` | R | 2-byte integer Kelvin (LE), rounded to whole K |
| `0x18` | `ADC_READ_PA5` | R | 12-bit ADC word |
| `0x19` | `ADC_READ_PB3` | R | Always `0xFF` — PB3 has no ADC on this part |
| `0x1A` | `SAVEEEPROM` | W | No payload; persist pin modes + I²C address |
| `0x1C` | `PIN_STATE_READ` | R | Mask: PA5 = bit 0, PB2 = bit 1, PB3 = bit 2 |

### Asynchronous (streaming) protocol, revision 2

| Cmd | Name | Dir | Payload / response |
|---|---|---|---|
| `0x20` | `STATUS` | R | 12-byte status frame (see §3) |
| `0x21` | `OPEN_WRITE` | W | Filename bytes; create/truncate, open for write |
| `0x22` | `WRITE` | W | Payload block → module RX buffers |
| `0x23` | `READ` | W / R | Write: request block; read: drain one TX chunk |
| `0x24` | `CLOSE_FLUSH` | W | No payload; flush + close the open file |
| `0x25` | `OPEN_READ` | W | Filename bytes; open for reading |
| `0x28` | `FORMAT` | W | 1 B mode (`0` = auto, `1` = force FAT) — destructive |
| `0x29` | `CARD_INFO` | R | 24-byte card/volume snapshot (see §5) |
| `0x2F` | `REBOOT` | W | No payload; reboot the module |

`0x26` (`DIAG`), `0x27` (`DIAG2`), and `0x2A` (`SD_DIAG`) exist in debug firmware
builds only and are not part of the stable API.

### Bit-bang engine

| Cmd | Name | Dir | Payload |
|---|---|---|---|
| `0x2B` | `BITBANG_SET_MODE` | W | 1 B pin ID: PA5 = `5`, PB2 = `2`, PB3 = `3` |
| `0x2C` | `BITBANG_BUFFER` | W | `[offL, offH, len, ...data]` into the 256 B workspace |
| `0x2D` | `BITBANG_EXECUTE` | W | 1 B profile: `1` = NeoPixel, `2` = script |
| `0x2E` | `BITBANG_CLEAR` | W | No payload; zero workspace + length mark |

Pin IDs are the **MCU port numbers** (`PA5 = 5`, `PB2 = 2`, `PB3 = 3`), not the
connector pin positions. `BITBANG_SET_MODE` selects the data pin but does **not**
set its direction — use the `SET_MODE` commands (`0x10`/`0x12`/`0x14`) with mode
`0` for that.

## 3. STATUS frame (the heartbeat of every operation)

`R addr [0x20] -> 12 bytes`, little-endian multi-byte fields:

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0 | 1 | `rev` | Protocol revision (`2` for rev 2) |
| 1 | 1 | `state` | One of `MICROSDEXP_ST_*` (below) |
| 2 | 1 | `opDone` | Sequence number of the last completed operation |
| 3 | 1 | `error` | One of `MICROSDEXP_ERR_*` (below) |
| 4 | 2 | `rxFree` | Free bytes in the RX buffer (LE) |
| 6 | 2 | `txAvail` | Staged bytes waiting in the TX buffer (LE) |
| 8 | 4 | `result` | Latched result (LE); sticky until the next op |

### `state` values

| Value | Name | Meaning |
|---|---|---|
| 0 | `IDLE` | No active storage operation |
| 1 | `ACCEPTED` | Request/payload safely copied into RAM |
| 2 | `BUSY_RX` | RX buffers occupied, being consumed |
| 3 | `BUSY_SD` | Worker is servicing the SD card / SPI |
| 4 | `TX_READY` | Response bytes staged for the master |
| 5 | `COMPLETE` | Last operation finished successfully |
| 6 | `ERROR` | Last operation failed (see `error`) |
| 7 | `OVERFLOW` | RX buffering exceeded; accepted bytes preserved |

### `error` values

| Value | Name | Meaning |
|---|---|---|
| 0 | `NONE` | No error |
| 1 | `NO_FILE` | Read/write with no file open |
| 2 | `OPEN` | OPEN failed (invalid path) |
| 3 | `CARD` | Filesystem/card failure |
| 4 | `QUEUE` | Request queue full; request rejected |
| 5 | `INVALID` | Malformed request |
| 6 | `OVERFLOW` | RX buffers full; bytes were NACKed |

### `opDone` and `result` — the two rules that matter most

> **1. ACK ≠ committed.** An ACK on a WRITE means "copied into RAM", never "on
> the card". Before submitting an operation, read `STATUS.opDone` and remember
> it. Then poll STATUS until `opDone` advances (it is an 8-bit counter that
> wraps). Only then did the operation actually finish.
>
> **2. `result` is a sticky latch.** Queries (`FILE_SIZE`, `FILE_EXISTS`,
> `IS_DIRECTORY`) and the write-commit counter report through `STATUS.result`.
> Read it *after* the op completes; it holds until the next operation starts.
> For a write, `result` is the cumulative byte count committed to the card —
> wait until `result >= baseline + bytes_written` before declaring success.

See [Status and Polling](Status-and-Polling.md) for the complete algorithm.

## 4. Little-endian convention

Every multi-byte field on the wire is **little-endian**: low byte first. For
example, a file size of `0x00000400` (1024) appears as `00 04 00 00`.

## 5. CARD_INFO frame

`R addr [0x29] -> 24 bytes`, all little-endian:

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | `mounted` — `1` = card mounted |
| 1 | 1 | `fat_type` — `0` unmounted, `12`/`16`/`32` FAT12/16/32, `64` exFAT |
| 2 | 1 | `card_type` — card class (SDSC, SDHC, …) |
| 3 | 1 | reserved (`0`) |
| 4 | 4 | `sector_count` |
| 8 | 4 | `free_clusters` |
| 12 | 2 | `err_code` |
| 14 | 2 | `err_data` |
| 16 | 4 | `cluster_count` |
| 20 | 4 | `sck_hz` — negotiated card SPI clock in Hz |

`sck_hz` is the single best predictor of throughput: cards that negotiate
10 MHz reach roughly 30–33 KiB/s at a 1 MHz I²C bus, while cards limited to
1 MHz sit near 18 KiB/s. Check it before assuming the bus is the bottleneck.

## 6. Stream formats

### Directory listing (`LIST_DIR`, `0x08`)

After the op completes, drain the TX buffer. Each entry is:

```
'F' or 'D'   (1 byte: file or directory)
name         (NUL-terminated string)
size         (4 bytes LE; 0 for directories)
```

The stream ends with a single `0xFF` byte. An empty directory produces just
`0xFF`. A missing path or a file used as a directory produces `ERROR` with no
stream at all.

### File read stream (`READ_FILE` `0x03` / `READ` `0x23`)

Bytes are staged in two staggered 128-byte TX buffers. Request up to 256 bytes
per drain (the module can stage that much across both buffers), then poll STATUS
and keep draining while `state == TX_READY` / `txAvail > 0`. The stream ends when
`state == COMPLETE` (EOF) or `ERROR`.

## 7. VERSION and the firmware banner

`R addr [0x0F]` returns the firmware version.

- Firmware **≤ 18.7.x**: a bare, NUL-padded string such as `"18.7.6"`.
- Firmware **≥ 18.8.0**: a 112-byte multi-line banner. The **first line is the
  measured clock** (e.g. `Clock: 20000000 Hz (fuse OSCCFG=0x7E)`), and the version
  (`v18.8.22`) appears on a later line.

When parsing, scan for a token containing a `.` that starts with a digit — that
is the version. Do **not** simply return the first line: on new firmware it is
the clock, not the version. The number immediately after `Clock:` on line one is
the measured module clock; the host libraries expose this as
`firmware_clock_hz()` / `firmwareClockHz()`.

## 8. Firmware feature floors

| Feature | Minimum module firmware |
|---|---|
| Asynchronous file API (`OPEN_WRITE`, `WRITE`, …) | 18.5.x |
| Pin control + bit-bang engine | 18.5.2 |
| Banner-only frames (cleared workspace really goes dark) | 18.8.0 |

## 9. Timeout scaling

The module's operation timeout scales with the I²C clock:

```
timeout = base * 100000 / scl_hz
```

but is **never shorter than `base`** (worker time does not track the bus clock).
Below 50 kHz the timeouts are doubled; the ceiling is 120 s. `FORMAT` is the
exception and uses its own 300 s budget. Note that per NXP UM10204 the "Standard
mode" range starts at 0 Hz and I²C uses static logic — arbitrarily low clocks are
valid and do not lose data. (The spec calls ≤100 kHz "Sm", never "Low-Speed".)

## 10. Paths

Paths are passed to the module's SdFat layer: case-insensitive 8.3 comparison,
`/` separator, `DIR/FILE` and `/DIR` treated equivalently, a trailing `/` means
a directory, and long filenames up to 259 characters. Validate path length in
the host before sending; overlong paths are rejected before any I²C traffic.

## See also

- [Direct I²C Guide](Direct-I2C-Guide.md) — transaction recipes
- [File Operations](File-Operations.md) — raw read/write/close sequences
- [Status and Polling](Status-and-Polling.md) — the completion algorithm
- [Expansion Pins](Expansion-Pins.md)
- [Bit-Bang Engine](Bit-Bang-Engine.md)
- [Error Codes](Error-Codes.md)
