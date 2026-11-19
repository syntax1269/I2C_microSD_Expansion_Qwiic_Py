# Wiring Guide

The module needs four connections and translates bus logic levels for you.

## Basic connection

| Host pin | Module pin |
|---|---|
| SDA | SDA |
| SCL | SCL |
| GND | GND |
| 3.3 V **or** 5 V | Power (choose one) |

- Power the module from **5 V or 3.3 V, never both**. SD writes cause brief
  current spikes, so use a short, well-decoupled supply lead.
- 3.3 kΩ pull-ups are fitted on the module; cut the underside trace if your host
  already provides pull-ups.
- The expansion pins PA5, PB2, PB3 are 3.3 V logic. A 5 V WS2812B strip needs a
  level shifter on DIN.

## Default address and discovery

The module answers at `0x6E` by default and can be re-addressed to `0x6A`–`0x6F`
with `change_address()` (persist with `save_pin_mode()`). All six addresses are
advertised in the driver's `available_addresses` attribute, so Qwiic discovery
finds a module at any of them.

Common hosts:

- **Raspberry Pi / Jetson / Coral:** use the board's standard I²C pins; install
  `sparkfun_qwiic_i2c` so `qwiic_i2c.getI2CDriver()` finds the Linux backend.
- **MicroPython / CircuitPython:** the driver uses the `qwiic_i2c` bus driver for
  that platform; on CircuitPython, `busio.I2C` is detected for the fast path.
- **Any host:** pass your own driver with `QwiicSDExpansion(i2c_driver=bus)`.

## Before you start

Format the card as FAT16/FAT32 (not exFAT), verify the module with an I²C scanner
at `0x6E`–`0x6F`, and check `version()` / `card_info()` before writing data. See
[Expansion Pins](../wiki/Expansion-Pins.md) for the raw pin commands.
