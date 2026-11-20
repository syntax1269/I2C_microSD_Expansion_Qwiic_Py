# Changelog

All notable changes to the Qwiic Python driver are documented here.

## [1.0.8] - 2026-11-20

### Added

- Four new examples: `ex6_sensor_ring_logger.py` (500 Hz sampling into a
  512-byte ring, drained with `write_now()` / `committed_bytes()`),
  `ex7_config_save_load.py` (checked queries plus a staged settings update),
  `ex8_dual_module_mirror.py` (two modules on one bus with `sticky_error`
  failover) and `ex9_threshold_bitbang_alert.py` (CSV logging plus a
  module-side strobe script).

## [1.0.7] - 2026-11-19

### Added

- **Checked query variants**: `exists_checked`, `file_size_checked` and
  `is_directory_checked` return `(ok, value)` so "not found" is distinct from
  a failed I²C transaction. Added `last_ok` shorthand. Original methods
  unchanged.

## [1.0.6] - 2026-11-19

### Added

- **Non-blocking submit/poll API**: `begin_open_write`, `begin_open_read`,
  `begin_close`, `begin_format`, `begin_query`, `poll_op`, `write_now`,
  `read_now`, `committed_bytes`, plus the `AsyncOp` token and `ASYNC_*` result
  constants. No sleeps; one STATUS read per poll; only one pending operation.
  No feature flag needed; the blocking API is unchanged.
- Example `ex5_nonblocking_write.py` and updated README/RTD documentation.

## [1.0.5] - 2026-11-19

### Changed

- Documented blocking behavior and worst-case timeouts for every high-level
  method in README and RTD docs. The Python ports remain synchronous; use a
  worker thread/task if your application cannot block.

## [1.0.4] - 2026-11-19

### Added

- **`diagnostics()`** returns a one-page health report (module, firmware and
  protocol version, card/filesystem, capacity and free space, I²C address,
  communication verdict) for customer troubleshooting. Safe before `begin()`
  (`n/a` for unreadable fields) and leaves `last_error` unchanged. Uses the
  module's real `free_clusters` value.
- `examples/ex4_diagnostics.py` and an API entry for the new method.

## [1.0.3] - 2026-11-19

### Added

- **Sticky error API.** `sticky_error` reports the first failure since
  `clear_error()`; `last_error` keeps its per-call semantics. Internal calls can
  no longer hide a real fault from a caller that checks the sticky value.
- **Version parse signal.** `version()` now sets `INVALID` when no dotted token
  can be parsed from the answered banner.

## [1.0.2] - 2026-11-18

### Fixed

- **Consistent sensor error sentinel.** `temperature_k()` and `adc_pa5()` now
  both return `0xFFFF` on any failure (bus error or short read), matching the
  Arduino and CircuitPython ports. `temperature_k()` previously returned `0`.

## [1.0.1] - 2026-11-18

### Fixed

- **`version()` against firmware ≥ 18.8.** The driver now parses the 112-byte
  version banner for the dotted version token (`18.8.22` verified), falling back
  to the legacy bare string. Added `firmware_banner()` and `firmware_clock_hz()`.
- **`format()` timing.** Now waits on a dedicated 300 s budget instead of the
  15 s operation timeout.
- **Allocation-free CircuitPython fast path.** Streams through the underlying
  `busio.I2C` via reusable buffers when qwiic_i2c exposes `_i2cbus`, with a
  portable fallback on other backends.

### Changed

- Standardized identifiers across the three host ports (`MICROSDEXP_*`,
  `MicroSDExpError`, `MicroSDExpFile`, `microSDexp`).

## [1.0.0] - 2026-11-16

### Added

- Full file/directory API, Qwiic discovery, expansion-pin and bit-bang API.
- 256-byte read chunk and ACK-paced writes.
