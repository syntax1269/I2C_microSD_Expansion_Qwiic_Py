# I²C microSD Expansion — SparkFun Qwiic Python Driver

**Add FAT file storage to any Python host with just two wires — as a Qwiic driver.**

The [I²C microSD Expansion](https://github.com/syntax1269/I2C-microSD-Expansion) module owns
the SD card and the FAT filesystem. Your host speaks plain I²C: open files, append,
list directories, stream data — with no FAT stack or SD driver in your code. The
module also exposes three expansion pins and a bit-bang engine that drives
WS2812B strips or plays timed pin scripts on its own.

`qwiic_sd_expansion_py` is the **SparkFun Qwiic Python (Qwiic_Py)** driver for that
module. It follows the Qwiic driver contract: a single importable module named
after the device, `device_name` and `available_addresses` class attributes, and
`is_connected()` / `connected` / `begin()` — so the `qwiic` package can discover
and construct it like any other Qwiic board.

The same API and the same `microSDexp` instance name are available in the
[Arduino](https://github.com/syntax1269/I2C-microSD-Expansion)
and [CircuitPython](https://github.com/syntax1269/I2C_microSD_Expansion_CircuitPython)
ports.

---

## Why use this module?

| Task | Without the module | With the module |
|---|---|---|
| Write a log | FAT library + SPI + shifter | `open("log.csv", "w")` → `write()` → `close()` |
| Read a file | Same, plus RAM buffers | `open("data.bin", "r")` → `read()` |
| List a directory | FAT directory parsing | `list_dir("/")` |
| Check card health | Mount volume, parse CSD | `card_info()` |
| Long filenames | LFN code size | Up to 259-char paths |
| WS2812B strip | LED library + PWM/SPI | `show_neopixels(pin, grb, count)` |

One file can be open at a time. `close()` returns only after the bytes are
committed to the card.

---

## Install

With the Qwiic package (Raspberry Pi, Jetson, Coral, MicroPython, CircuitPython
hosts):

```sh
pip install sparkfun_qwiic_i2c
pip install .                      # from this repository
```

For `qwiic.list_devices()` to discover the driver, the module must be importable
in the same environment as `qwiic` — either install it as above, or place
`qwiic_sd_expansion_py.py` alongside the `qwiic` package (in a checkout, its
`qwiic/drivers/` directory holds driver submodules).

The driver also works **standalone**, without the `qwiic` package:

```python
import qwiic_sd_expansion_py
microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
```

---

## Wiring

| Host | Module |
|---|---|
| SDA | SDA |
| SCL | SCL |
| GND | GND |
| 3.3 V **or** 5 V | Power (one only, never both) |

- No external level shifter — the module handles 3.3 V / 5 V bus logic.
- 3.3 kΩ pull-ups are fitted on the module; remove via the underside trace cut if
  your host supplies its own.
- The expansion pins are 3.3 V logic; a 5 V WS2812B strip needs a level shifter
  on DIN.

See [docs/wiring.md](docs/wiring.md) for board notes.

---

## Qwiic discovery

Because the driver follows the Qwiic contract, the `qwiic` package finds it at
runtime — no hard-coded address and no manual wiring of driver objects:

```python
import qwiic

for address, name, driver in qwiic.list_devices():
    print(address, name, driver)
# 110 I2C microSD Expansion QwiicSDExpansion

microSDexp = qwiic.create_device("I2C microSD Expansion")
microSDexp.begin()

with microSDexp.open("HELLO.TXT", "w") as f:
    f.write(b"HELLO-WORLD")
```

`qwiic.list_available_drivers()` reports it without a scan:

```python
>>> qwiic.list_available_drivers([0x6E])
[(110, 'I2C microSD Expansion', 'QwiicSDExpansion')]
```

The class is also reachable as `qwiic.QwiicSdExpansionPy` after the package
loader runs (Qwiic_Py derives that name from the module name).

### What makes it discoverable

| Qwiic requirement | This driver |
|---|---|
| Module `qwiic_<device>.py` | `qwiic_sd_expansion_py.py` |
| Class `Qwiic<Device>` | `QwiicSDExpansion` (alias `QwiicSdExpansionPy`) |
| `device_name` | `"I2C microSD Expansion"` |
| `available_addresses` | `[0x6E, 0x6A, 0x6B, 0x6C, 0x6D, 0x6F]` |
| `__init__(address=None, i2c_driver=None)` | yes |
| `is_connected()` / `connected` / `begin()` | yes |
| Built on `qwiic_i2c` | `qwiic_i2c.getI2CDriver()` |

Discovery is address-based: the module answers at `0x6E` by default and can be
re-addressed to `0x6A`–`0x6F`; all six addresses are advertised.

---

## Quick start (standalone)

```python
import qwiic_sd_expansion_py

microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
if not microSDexp.begin():
    raise SystemExit("microSD expansion not found")

print(microSDexp.version())                 # e.g. "18.8.22"

f = microSDexp.open("HELLO.TXT", "w")
f.write(b"HELLO-WORLD")
f.close()                                   # returns once it is on the card

r = microSDexp.open("HELLO.TXT", "r")
print(r.read(32))                           # b'HELLO-WORLD'
r.close()
```

Use `QwiicSDExpansion(address=0x6C)` for a re-addressed module, or
`QwiicSDExpansion(i2c_driver=bus)` to reuse a bus driver you already created.

**Module firmware:** the file API needs 18.5.x+; pin/bit-bang needs 18.5.2+;
banner-only frames need 18.8.0+. From 18.8.0 the version command also reports the
measured clock, exposed via `firmware_clock_hz()`.

---

## Using the driver

### Files

```python
with microSDexp.open("data.log", "w") as f:    # create/truncate
    f.write(b"sensor reading\n")

with microSDexp.open("log.csv", "a") as f:     # append
    f.write(b"1,2,3\n")

with microSDexp.open("data.log", "r") as f:
    data = f.read(128)                         # short at EOF

microSDexp.open_write("x.bin")
microSDexp.open_read("x.bin")
microSDexp.open_append("log.csv")
```

### Directories and queries

```python
microSDexp.mkdir("logs")
microSDexp.remove("temp.tmp")
microSDexp.rmdir("empty")

if microSDexp.exists("data.bin"):
    size = microSDexp.file_size("data.bin")
    microSDexp.is_directory("data.bin")

for e in microSDexp.list_dir("/", max_entries=32):
    print("D" if e.is_dir else "F", e.name, e.size)
```

Paths follow the module's FAT semantics: case-insensitive 8.3 comparison, `/`
separator, `DIR/FILE` and `/DIR/FILE` equivalent, trailing `/` ⇒ directory, LFN
up to 259 characters. `valid_path()` length-gates a path without bus traffic.

### Card, version, and diagnostics

```python
print(microSDexp.version())
print(microSDexp.firmware_banner())
print(microSDexp.firmware_clock_hz())
print(microSDexp.temperature_k())       # whole kelvin; 0xFFFF on error
print(microSDexp.adc_pa5())              # 0xFFFF on error/unavailable
info = microSDexp.card_info()
print(info.mounted, info.fat_type, info.sck_hz)
st = microSDexp.read_status()            # raw 12-byte StatusFrame
```

`card_info().fat_type` uses SdFat values: `0` unmounted, `12`/`16`/`32`/`64`.
`temperature_k()` returns whole kelvin (2-byte LE, rounded to integer K), not an ADC
count; subtract 273.15 for °C. Both `temperature_k()` and `adc_pa5()` return
`0xFFFF` on any failure (bus error, short read, or unavailable ADC channel).

### Expansion pins and NeoPixel

```python
from qwiic_sd_expansion_py import MICROSDEXP_PIN_PA5, MICROSDEXP_PIN_PB2

microSDexp.set_pin_mode(MICROSDEXP_PIN_PB2, 0)   # mode 0 = digital output
microSDexp.write_pin(MICROSDEXP_PIN_PB2, 1)      # level 1 = high
microSDexp.save_pin_mode()               # persist modes + address once, when final

frame = bytearray(8 * 3)                 # GRB, three bytes per pixel
frame[1] = 40
microSDexp.set_pin_mode(MICROSDEXP_PIN_PA5, 0)   # mode 0 = digital output
microSDexp.bitbang_clear()
microSDexp.show_neopixels(MICROSDEXP_PIN_PA5, frame, 8)
```

Mode/level literals are module protocol values (no named aliases): `0` in
`set_pin_mode` = digital output; `write_pin(..., 0)` = low, `write_pin(..., 1)` = high;
`format(0)` = automatic, `format(1)` = force FAT rebuild.

The workspace is 256 bytes ⇒ at most 85 pixels. For custom timing use
`bitbang_buffer()` + `bitbang_execute(MICROSDEXP_BITBANG_PROFILE_SCRIPT)`; see the
[Bit-Bang Engine wiki](wiki/Bit-Bang-Engine.md).

### Housekeeping and errors

```python
microSDexp.set_clock_time(2026, 11, 18, 12, 0, 0)
microSDexp.change_address(0x6C)          # re-address the module (persist with save_pin_mode)
microSDexp.reboot()
microSDexp.format(0)                     # DESTRUCTIVE; 0 = automatic, 1 = force FAT

if microSDexp.last_error != 0: ...
if microSDexp.file_open: microSDexp.close()
if microSDexp.sticky_error != 0: ...   # fault since clear_error()
microSDexp.clear_error()              # start a fresh error window
```

`last_error` is the result of the *most recent* call and may be overwritten by
internal calls (for example, a `list_dir()` drain). Use `sticky_error` for the
first failure since `clear_error()` when you need an error that internal traffic
cannot hide. `version()` returns `""` with `INVALID` when the banner cannot be
parsed in the available data.

| Value | Meaning |
|---|---|
| 0 `OK` | No error |
| 1 `NO_MODULE` | Module not responding |
| 2 `NO_FILE` | No file open |
| 3 `OPEN_FAIL` | Open rejected |
| 4 `CARD_ERR` | Card / filesystem error |
| 5 `QUEUE_FULL` | Module queue full |
| 6 `INVALID` | Bad argument |
| 7 `OVERFLOW` | Module buffers full |
| 8 `TIMEOUT` | Operation timed out |

---

## Transport notes and tuning

The module protocol is one command per transaction, mirrored here onto the
`qwiic_i2c` register-style API: `writeCommand()` / `writeBlock()` send the command
plus data with a STOP, and `writeReadBlock()` sends the command and reads back
with a repeated START.

- **Write chunk:** 32 bytes by default (Linux SMBus block writes carry at most
  32 payload bytes), 128 on CircuitPython. Override with
  `set_write_chunk_bytes(n)`.
- **Read chunk:** 256 bytes by default — the module stages that much across its
  two TX buffers. A port that caps a transfer lower falls back automatically.
- **ACK-paced writes:** push until the module NACKs, then read STATUS to tell
  "buffers busy" from a card error and wait `flow_poll_ms` before retrying.
  Tune with `set_poll_interval(ms)` and `set_flow_poll_ms(ms)`.
- **Fast path:** on CircuitPython, the driver detects `qwiic_i2c`'s underlying
  `_i2cbus` (`busio.I2C`) and streams through reusable buffers instead of
  rebuilding boxed Python lists per call, falling back to portable calls on
  every other backend.

Typical throughput at a 1 MHz bus with the fast path is about **44 KiB/s write /
38 KiB/s read** on files from 128 KiB to 3 MiB, byte-identical round trips. The
portable 32-byte fallback reaches about 20 KiB/s. Note that the first file after
a module reset is slower while the card re-trains; time later files. If
throughput collapses in both directions, `reboot()` restores full speed.

---

## Examples

| Example | Shows |
|---|---|
| `ex1_file_write_read.py` | Qwiic discovery, write, close, read back |
| `ex2_directory_and_card.py` | Directory listing, card info, version |
| `ex3_pins_and_neopixel.py` | Pins, EEPROM save, NeoPixel frame |
| `ex4_diagnostics.py` | One-page health report |
| `ex5_nonblocking_write.py` | Non-blocking submit/poll write |
| `ex6_sensor_ring_logger.py` | 500 Hz sampling with an SRAM ring buffer |
| `ex7_config_save_load.py` | Checked queries and staged settings updates |
| `ex8_dual_module_mirror.py` | Two modules, one bus, `sticky_error` failover |
| `ex9_threshold_bitbang_alert.py` | CSV logging + module-side strobe alert |

---

## Tests

The suite runs on a desktop — no hardware and no `qwiic_i2c` install needed
(a stand-in driver and an in-memory module are registered by the tests):

```sh
python -m unittest discover -s tests -v
```

It covers Qwiic metadata, discovery, address scanning, write/read round trips,
chunk limits, append, directories and queries, card info and version, pin-mode
de-duplication, EEPROM save, the 85-pixel frame limit, bit-bang workspace writes,
the raw-`busio.I2C` fast path, and the no-module path.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Driver not discovered | Not importable in the `qwiic` environment | Install with `pip install .` or place it in `qwiic/drivers/` |
| `begin()` returns False | Wrong address / no common GND | Scan `0x6E`–`0x6F`; common GND |
| Card not mounted | exFAT or unformatted card | Reformat FAT16/FAT32 |
| Short or stale reads | Didn't wait for completion | Use the file object; the driver polls STATUS for you |
| Short reads / NACKs on a Raspberry Pi (Pi 4 or earlier) | Broadcom BSC silicon bug with clock stretching | Add `dtoverlay=i2c-gpio` to `/boot/config.txt`, or use a Pi 5 |
| `OVERFLOW` | Writing faster than the module commits | Slow down / raise the flow poll interval |
| Strip stays dark | Pin not an output | `set_pin_mode(pin, 0)` first |
| Tail pixels lit | Stale workspace | `bitbang_clear()` before a shorter frame |

Deep protocol detail is in the [wiki](wiki/Home.md). For the Broadcom host bug
and its workaround, see
[Clock stretching and Raspberry Pi hosts](wiki/Protocol-Reference.md#clock-stretching-and-raspberry-pi-hosts).

---

## Blocking behavior (important)

Most high-level methods are **synchronous**: they poll the module's STATUS
frame in a `delay()` loop until the operation completes or a timeout expires.
They do not sleep the whole time (the I²C bus stays responsive at the protocol
level), but your sketch/application **is blocked** for the duration. Plan for
this with watchdogs, real-time loops, cooperative schedulers and ESP32 tasks.

Timeouts scale up on slow buses (`base × 100000 / I2C_Hz`, floor `base`, 2× below
50 kHz) and are **capped at 120 s** by the host. `format()` is the exception: it
uses an unscaled 300 s budget. The ESP32 gateway's `cardinfo` shows the
configured bus clock.

| Method | Typical wait | Worst case |
|---|---|---|
| `begin()` | ~1.5 s | 10 mount attempts × 150 ms + STATUS probes |
| `read_status()` | one I²C transaction | no loop |
| `wait_for_op_complete()` | 15 s | 120 s cap |
| `wait_for_committed()` | 30 s | 120 s cap |
| `open_write()` / `open_read()` | one op wait | up to 6 × (close-flush barrier + op wait + 200 ms) — potentially minutes |
| `open_append()` | none | local state only |
| `write()` | ~0.8 s per 64 B block (flow poll) | 400 attempts × 2 ms per block; append adds one op wait per chunk |
| `read()` | until bytes arrive | 30 s, up to 120 s cap |
| `sync()` | until bytes commit | 30 s, up to 120 s cap |
| `close()` | sync + one op wait | ~45 s typical, up to two capped waits |
| `format()` | destructive, long | 300 s (unscaled; not subject to the 120 s cap) |
| `mkdir/rmdir/remove/exists/is_directory/file_size/version/firmware_banner/card_info/list_dir` | one op wait | 15 s, up to 120 s cap |
| `bitbang_*()` / `show_neopixels()` / `save_pin_mode()` | one I²C transaction | module-side execution is not awaited |
| `diagnostics()` | a few STATUS reads | no wait loops |

Feed any hardware watchdog around `format()` and the open/write/sync/close
group. If you cannot afford to block, use the non-blocking API below (no feature flag needed).

## Checked queries (return semantics)

`exists()` / `file_size()` / `is_directory()` return a value even when the I²C
command fails, so `False` / `0` can mean either "no such file" or "communication
error". Use the checked variants when that distinction matters — they return
`(ok, value)`:

```python
ok, present = microSDexp.exists_checked("A.TXT")
ok, size = microSDexp.file_size_checked("A.TXT")
ok, isdir = microSDexp.is_directory_checked("DIR")
```

`ok` is `False` on I²C/card/path error; inspect `last_error` then. `last_ok` is
a shorthand for `last_error == MicroSDExpError.OK`. The original methods are
unchanged and remain convenient when a failed query can simply mean "no".

## Diagnostics

`diagnostics()` returns a one-page report for troubleshooting:

```python
microSDexp.begin()
print(microSDexp.diagnostics())
```

```text
I2C microSD Expansion
---------------------
Module detected:   yes
Firmware version:  18.8.23
Protocol version:  2
SD card detected:  yes
Filesystem:        FAT32
Capacity:          3810.0 MiB / 3.72 GiB
Free space:        3801.9 MiB / 3.71 GiB
I2C address:       0x6E
I2C speed:         n/a (host bus)
Communication:     OK
```

It is safe to call before `begin()`; unreadable fields show as `n/a`. The call
does not change `last_error`. Bus speed is owned by the Qwiic host driver, so
it is reported as `n/a (host bus)`.

## Non-blocking API

If your application cannot block, the submit/poll API performs no sleeps:

```python
import qwiic_sd_expansion_py
from qwiic_sd_expansion_py import AsyncOp, ASYNC_BUSY, ASYNC_OK

microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
microSDexp.begin()

op = AsyncOp()
microSDexp.begin_open_write("ASYNC.TXT", op)
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass                      # do other work here

sent = 0
while sent < len(data):
    sent += microSDexp.write_now(data[sent:])  # 0 = try again next pass

target = microSDexp.committed_bytes()
while microSDexp.committed_bytes() < target:
    pass

op = AsyncOp()
microSDexp.begin_close(op)
while microSDexp.poll_op(op) == ASYNC_BUSY:
    pass
```

`begin_open_write`, `begin_open_read`, `begin_close`, `begin_format` and
`begin_query` submit a command and return immediately. `poll_op()` performs one
STATUS read (`ASYNC_BUSY`, `ASYNC_OK`, or a module error code). `write_now()`
and `read_now()` move only what fits right now — zero/empty means "try again",
not failure. `committed_bytes()` reports the commit counter. Only one async
operation may be pending at a time.

No compile-time flag is needed (unlike the Arduino port); the blocking methods
remain available and unchanged. See `ex5_nonblocking_write.py`.

## Documentation

Full API documentation is published at https://i2c-microsd-expansion-qwiic-py.readthedocs.io/ and can be built locally with `Sphinx <https://www.sphinx-doc.org/>`_ from `docs/`.

---

## License

MIT. See [LICENSE](LICENSE). Not affiliated with the SD Association.
