# API Reference

Everything below lives in the single module `qwiic_sd_expansion_py`.

## `QwiicSDExpansion(address=0x6E, i2c_driver=None, scl_hz=400000, poll_ms=10, flow_poll_ms=2)`

Create a module instance. An address outside the module's range falls back to
`0x6E`. `scl_hz` only feeds timeout scaling. `i2c_driver` is a `qwiic_i2c`
driver; when omitted, `qwiic_i2c.getI2CDriver()` is used. The alias
`QwiicSdExpansionPy` is provided for the Qwiic loader's derived class name.

### Qwiic contract

| Member | Description |
|---|---|
| `device_name` | `"I2C microSD Expansion"` |
| `available_addresses` | `[0x6E, 0x6A, 0x6B, 0x6C, 0x6D, 0x6F]` |
| `is_connected()` / `connected` | ACK probe at the bound address |
| `begin()` | Probe STATUS; scan `0x6A`–`0x6F` once if silent |
| `set_address(addr)` | Rebind this object to another address (no bus traffic) |
| `change_address(addr)` | Re-address the module itself (CMD `0x16`) |

### Configuration / diagnostics

| Member | Description |
|---|---|
| `set_poll_interval(ms)` | STATUS poll pause (default 10 ms) |
| `set_flow_poll_ms(ms)` / `flow_poll_ms()` | Pause after a write NACK (default 2 ms) |
| `set_read_chunk_bytes(n)` / `read_chunk_bytes()` | Bytes per READ drain (default 256) |
| `set_write_chunk_bytes(n)` / `write_chunk_bytes()` | Payload bytes per WRITE (default 32, 128 on CircuitPython) |
| `last_error` / `sticky_error` / `clear_error()` | Last result / first failure since clear / reset both |
| `file_open` | `True` while a file is open |
| `read_status()` | Raw 12-byte `StatusFrame` |
| `version()` | Firmware string, e.g. `"18.8.22"` |
| `firmware_banner()` | Full CMD `0x0F` answer |
| `firmware_clock_hz()` | Measured clock from the banner (`0` on older firmware) |
| `temperature_k()` / `adc_pa5()` | Whole-kelvin die temperature / raw 12-bit ADC word; both `0xFFFF` on error |
| `card_info()` | `CardInfo` (mounted, FAT type, sectors, SCK Hz) |

### Files

`open(path, mode)` → `MicroSDExpFile` (context manager) or `None`, with `"r"`
/ `"w"` / `"a"`; `open_read` / `open_write` / `open_append`; `write(data)`,
`read(n)`, `sync()`, `close()`.

### Directories and paths

`list_dir(path, max_entries=64)`, `mkdir`, `rmdir`, `remove`, `exists`,
`file_size`, `is_directory`, `valid_path`.

### Pins and bit-bang

`set_pin_mode(pin, mode)`, `write_pin(pin, value)`, `save_pin_mode()`,
`bitbang_set_mode(pin)`, `bitbang_buffer(offset, data, length=None)`,
`bitbang_execute(profile)`, `bitbang_clear()`, `show_neopixels(pin, grb,
pixel_count=None)`.

### Housekeeping

`set_clock_time(y, mo, d, h, mi, s)`, `reboot()`, `format(mode=0)` (destructive,
up to 300 s).

## Classes

- `MicroSDExpError` — `OK(0)`, `NO_MODULE(1)`, `NO_FILE(2)`, `OPEN_FAIL(3)`,
  `CARD_ERR(4)`, `QUEUE_FULL(5)`, `INVALID(6)`, `OVERFLOW(7)`, `TIMEOUT(8)`.
- `StatusFrame` — `rev`, `state`, `op_done`, `error`, `rx_free`, `tx_avail`,
  `result`.
- `CardInfo` — `mounted`, `fat_type`, `card_type`, `sector_count`,
  `free_clusters`, `cluster_count`, `sck_hz`, `free_bytes`.
- `DirEntry` — `is_dir`, `name`, `size`.
- `MicroSDExpFile` — `write`, `read`, `sync`, `close`, `microSDexp`, `is_open`,
  context-manager support.

## Constants

All `MICROSDEXP_*` wire constants are module-level: commands (`MICROSDEXP_CMD_*`),
pin IDs (`MICROSDEXP_PIN_PA5=5`, `_PB2=2`, `_PB3=3`), bit-bang profiles
(`MICROSDEXP_BITBANG_PROFILE_NEOPIXEL=1`, `_SCRIPT=2`), FAT types, STATUS
states/errors, and `__version__`. They mirror the Arduino library's
`protocol.h`; see the [Protocol Reference](../wiki/Protocol-Reference.md).
