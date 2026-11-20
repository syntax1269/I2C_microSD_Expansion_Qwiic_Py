# Bit-Bang Engine and WS2812B

The module has an on-board bit-bang engine that generates timed pin waveforms
**without host involvement**. It is used for two things:

1. driving WS2812B ("NeoPixel") LED strips, and
2. playing a small token script for custom timed pin edges.

The waveform is generated on the module by a cycle-exact assembly emitter, so its
timing is far more precise than toggling a GPIO over I²C. Since firmware 18.8.33
the TWI (I²C) interrupt stays enabled during a blit - see **Interrupt behaviour**
below. This page documents the raw commands; the libraries expose them as
`show_neopixels()`, `bitbang_*()` etc.

Requires module firmware **18.5.2** or newer. The "send only buffered bytes"
behavior (so clearing the workspace really darkens the strip) needs **18.8.0**.
Continuous chases (`0x03`) need **18.8.41** (ATtiny3224) / **19.2.5** (AVR64DD20).

## The 256-byte workspace

The engine works from a **256-byte RAM workspace**. A value written past 256
bytes is silently dropped. A NeoPixel frame is 3 bytes per pixel (GRB), so:

```
max frame = 255 bytes = 85 pixels
```

The module tracks a **high-water mark** (`bitbangDataLength`) of how many bytes
have been buffered. It clocks out exactly that many bytes, so a short frame
cannot push stale pixels — but the mark only grows. **Clear the workspace before
sending a shorter frame**, or the old tail bytes will still be transmitted.

The workspace aliases the formatter/probe sector buffer, so `BITBANG_BUFFER`
(`0x2C`) is NACKed while a format or probe owns that block. Retry later.

## Commands

| Cmd | Name | Payload | Effect |
|---|---|---|---|
| `0x2B` | `BITBANG_SET_MODE` | 1 B pin ID | Select data pin: PA5=`5`, PB2=`2`, PB3=`3` |
| `0x2C` | `BITBANG_BUFFER` | `[offL, offH, len, ...data]` | Copy `len` bytes to workspace at `offset` |
| `0x2D` | `BITBANG_EXECUTE` | 1 B profile | Run profile `1` (NeoPixel), `2` (script), or `3` (continuous NeoPixel loop) |
| `0x2E` | `BITBANG_CLEAR` | none | Zero workspace and reset the length mark |

The header (`offset` low, `offset` high, `len`) and payload of `0x2C` travel in
**one transaction**. Split a longer frame into consecutive workspace writes,
each small enough for your host's I²C write buffer.

`BITBANG_SET_MODE` does **not** set the pin direction. Set the pin to digital
output first with `PA5_SET_MODE` / `PB2_SET_MODE` / `PB3_SET_MODE` (`0x10` /
`0x12` / `0x14`) with mode `0`.

## 1. Drive a WS2812B strip

The strip expects **GRB** bytes, green first, three per pixel.

```
W [0x10, 0x00]                 # PA5 = digital output (if using PA5)
W [0x2B, 0x05]                 # bit-bang data pin = PA5
W [0x2E]                       # CLEAR workspace / length mark
# frame: 8 pixels, first one dim red (G=0, R=40, B=0)
W [0x2C, 0x00, 0x00, 0x18,
    0x00, 40, 0,  0,0,0, 0,0,0, ...]   # 24 bytes at offset 0
W [0x2D, 0x01]                 # EXECUTE NeoPixel profile
delay(2 + pixels*32/1000)      # keep bus quiet until frame is on the wire
```

Three host responsibilities the engine cannot handle for you:

1. **Pin must be a digital output** — set the mode first.
2. **Clear before a shorter frame** — otherwise stale tail bytes light extra
   LEDs.
3. **Keep the bus quiet** during and just after `EXECUTE` — about 30 µs per pixel
   plus the latch reset. A following command can split the frame and make the
   tail pixels keep their old color.

The timing is derived from the module's clock measured at power-up, so it holds
at both 10 MHz and 20 MHz module variants.

## 2. Play a script (timed pin edges)

Profile `2` interprets the workspace as a token program.

| Byte | Token | Payload | Meaning |
|---|---|---|---|
| `0x01` | `SET_HIGH` | — | Drive data pin high |
| `0x02` | `SET_LOW` | — | Drive data pin low |
| `0x03` | `DELAY_US` | `usL, usH` | Delay 1–65535 µs |
| `0x04` | `DELAY_MS` | `ms` | Delay 1–255 ms |
| `0x05` | `LOOP_GOTO` | `target, count` | Jump to byte offset `target`, `count` passes total |
| `0x00` | end | — | Stop execution |

Execution stops at `0x00`, at any unrecognized byte, or at the workspace end.
`DELAY_US` is counted in CPU cycles from the measured clock, so it is accurate at
both supported module speeds.

### Example: blink PA5 five times (200 ms each half)

```
W [0x10, 0x00]                 # PA5 = output
W [0x2B, 0x05]                 # engine data pin = PA5
W [0x2E]                       # clear workspace
W [0x2C, 0x00, 0x00, 0x09,
    0x01, 0x04, 200,           # SET_HIGH, DELAY_MS 200
    0x02, 0x04, 200,           # SET_LOW,  DELAY_MS 200
    0x05, 0x00, 5]             # LOOP_GOTO offset 0, 5 passes
W [0x2D, 0x02]                 # EXECUTE script profile
delay(2100)                    # 5 * 400 ms; keep bus quiet
```

## 3. Continuous chase (profile 3)

Profile `3` re-clocks the buffered frame forever, so the module generates a
running chase with **no host involvement** after one frame has been uploaded:

```
W [0x10, 0x00]                 # PA5 = digital output (or 0x12/PA6, 0x14/PA7)
W [0x2B, 0x05]                 # engine data pin = PA5
W [0x2E]                       # CLEAR workspace / length mark
W [0x2C, 0x00, 0x00, ...]      # one GRB frame (3 bytes per pixel)
W [0x2D, 0x03]                 # EXECUTE NEO_LOOP
# ... the strip now chases continuously ...
W [0x2E]                       # CLEAR stops the loop and darkens the strip
```

**Interrupt behaviour.** The TWI ISR stays enabled throughout the chase. An
incoming transaction preempts the emitter, is serviced from the ISR's RAM
state, and the emitter resumes at the next bit; SCL is held only for the
ISR's few-microsecond latency. Closing the TWI interrupt (per pixel or per
frame) was tried and rejected: it lost CLEAR/STOP and left the chase
unstoppable over I2C.

**Scheduling and file I/O.** The chase is limited to about 30 frames/s and
rotates one GRB pixel per frame, so an uploaded rainbow frame becomes a
moving chase. File operations queued while a chase is running are not
processed until `BITBANG_CLEAR` stops it; use host-driven profile 1 frames
when storage I/O must overlap with LED output.

The watchdog is fed once per frame, so the chase survives indefinitely even
with no I2C traffic. `BITBANG_CLEAR (0x2E)` is the stop control. Do not rewrite
the workspace (`0x2C`) while a loop is running - CLEAR first, then upload the
new frame.

## Constraints and safety

- **TWI interrupt stays enabled** since firmware 18.8.33. Commands are ACKed
  during a blit; only the millis tick is masked. Profile 1 (single frame) can
  have its colours split by mid-frame I2C traffic - keep the bus quiet for
  ~30 us/pixel plus the latch reset, or use profile 3 for a continuous chase.
- Profile 3 keeps the TWI ISR enabled and runs at ~30 fps. Transactions are
  never dropped; queued file operations complete after CLEAR stops the chase.
- Scripts and profile 3 feed the watchdog themselves (18.8.37+), so long or
  looping runs no longer reset at 8 s. Still provide a stop (`0x2E`) for
  unbounded scripts.
- A rejected `BITBANG_BUFFER` during format/probe is expected; retry later.
- `BITBANG_BUFFER` may NACK while a format/probe owns the shared block; retry.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Strip stays dark | Pin not set to output; wrong data pin; no level shifter for a 5 V strip's DIN |
| Extra LEDs lit | Forgot `BITBANG_CLEAR` before a shorter frame |
| Tail pixels keep old color | I²C traffic arrived during the frame; keep bus quiet |
| Script never stops | Missing `0x00` terminator, or an invalid token ended it early |
| `BITBANG_BUFFER` NACKs | Format/probe running; retry later |

## See also

- [Expansion Pins](Expansion-Pins.md) — pin modes and data pin selection
- [Protocol Reference](Protocol-Reference.md#4-bit-bang-engine) — command table
- [Error Codes](Error-Codes.md)
