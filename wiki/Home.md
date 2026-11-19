# Qwiic Python Driver Wiki

Technical documentation for the **I²C microSD Expansion Qwiic Python driver**.
The [README](../README.md) teaches you how to install and use the driver; this
wiki goes deeper, including how to talk to the module with raw I²C commands if
you would rather write your own driver.

## Where to go

| I want to… | Go to |
|---|---|
| Install / discover via Qwiic | [README](../README.md#install) · [Qwiic discovery](../README.md#qwiic-discovery) |
| Use the driver | [README](../README.md#using-the-driver) · [API reference](../docs/api.md) |
| Full command set | [Protocol Reference](Protocol-Reference.md) |
| Write my own I²C driver | [Direct I²C Guide](Direct-I2C-Guide.md) |
| Raw file read/write | [File Operations](File-Operations.md) |
| Completion / polling | [Status and Polling](Status-and-Polling.md) |
| PA5 / PB2 / PB3 | [Expansion Pins](Expansion-Pins.md) |
| WS2812B / scripts | [Bit-Bang Engine](Bit-Bang-Engine.md) |
| Decode an error | [Error Codes](Error-Codes.md) |

## 60-second summary

```python
import qwiic_sd_expansion_py
microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
if not microSDexp.begin():
    raise SystemExit("module not found")

f = microSDexp.open("HELLO.TXT", "w")
f.write(b"HELLO-WORLD")
f.close()                      # returns once bytes are committed
```

The module is an I²C peripheral at `0x6E` (re-addressable to `0x6A`–`0x6F`) that
owns the FAT filesystem. This driver maps it onto the `qwiic_i2c`
register-style API: `writeCommand()` / `writeBlock()` for writes with STOP, and
`writeReadBlock()` for reads with a repeated START. The critical rule: an ACK is
not a commit — poll the STATUS `opDone` counter and `result` latch before
trusting a write. See [Status and Polling](Status-and-Polling.md).

## Page index

- **[Protocol Reference](Protocol-Reference.md)** — commands, frames, streams,
  banner, paths, timeouts.
- **[Direct I²C Guide](Direct-I2C-Guide.md)** — transaction shapes and recipes.
- **[File Operations](File-Operations.md)** — raw file sequences with flow control.
- **[Status and Polling](Status-and-Polling.md)** — opDone, result, NACKs, recovery.
- **[Expansion Pins](Expansion-Pins.md)** — modes, ADC, EEPROM, address change.
- **[Bit-Bang Engine](Bit-Bang-Engine.md)** — NeoPixel frames and script tokens.
- **[Error Codes](Error-Codes.md)** — enums and troubleshooting.

## Firmware floors

| Feature | Minimum firmware |
|---|---|
| File API | 18.5.x |
| Pins + bit-bang | 18.5.2 |
| Banner frames + measured clock | 18.8.0 |

Check with `microSDexp.version()`.
