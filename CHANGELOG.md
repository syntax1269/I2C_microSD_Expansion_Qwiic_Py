# Changelog

All notable changes to the Qwiic Python driver are documented here.

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
