# Expansion Pins Over Raw I²C

Besides storage, the module exposes three spare MCU pins: **PA5**, **PB2**, and
**PB3**. You can drive them as digital outputs, read their state, sample PA5 with
the ADC, and persist their configuration to EEPROM. This page gives the raw
commands; the host libraries wrap them as `set_pin_mode()` / `write_pin()` etc.

## Pin IDs vs. connector pins

| Signal | Pin ID (used in commands) | Notes |
|---|---|---|
| PA5 | `5` | Also the ADC input |
| PB2 | `2` | Digital output |
| PB3 | `3` | Digital output; **no ADC** on this MCU |

Pin IDs are the MCU port numbers, **not** the expansion-connector pin positions.

## 1. Set a pin's mode

| Cmd | Name | Payload |
|---|---|---|
| `0x10` | `PA5_SET_MODE` | 1 byte mode |
| `0x12` | `PB2_SET_MODE` | 1 byte mode |
| `0x14` | `PB3_SET_MODE` | 1 byte mode |

Mode `0` = digital output. Other values are forwarded to the module unchanged.

```
W [0x12, 0x00]        # set PB2 to digital output
```

Key behaviors:

- The mode takes effect **immediately in RAM**.
- The module **never writes EEPROM on a mode change**. You can change modes as
  often as you like without wearing the EEPROM.
- A redundant "apply" of the mode already in RAM is a no-op on the module.
- A control write to a pin that is not in output mode is NACKed.

## 2. Drive a pin

| Cmd | Name | Payload |
|---|---|---|
| `0x11` | `PA5_CONTROL` | mode-dependent value |
| `0x13` | `PB2_CONTROL` | mode-dependent value |
| `0x15` | `PB3_CONTROL` | mode-dependent value |

In digital-output mode the control value is simply the level: `0` = low, `1` =
high (any non-zero is typically treated as high).

```
W [0x10, 0x00]        # PA5 = digital output
W [0x11, 0x01]        # PA5 = high
W [0x11, 0x00]        # PA5 = low
```

## 3. Read pin state

`R [0x1C] -> 1 byte`, a bitmask of the current pin levels:

| Bit | Pin |
|---|---|
| 0 | PA5 |
| 1 | PB2 |
| 2 | PB3 |

```
R [0x1C] -> mask         # e.g. 0b001 = PA5 high
```

## 4. Analog input (PA5 only)

`R [0x18] -> 2 bytes` returns the 12-bit ADC word from PA5. The ADC uses an
internal `1.024 V` reference, roughly `1 mV` per LSB. An unavailable channel is
reported as `0xFFFF`.

```
R [0x18] -> adc_word (LE)         # 0..4095, or 0xFFFF if unavailable
```

`R [0x19]` (PB3 ADC) always returns `0xFF` — that pin has no ADC on this MCU.

## 5. Temperature

`R [0x17] -> 2-byte integer Kelvin (LE)`. This is the module die temperature
rounded to whole kelvin — **not** an ADC count and not a fixed-point value. The
host libraries expose it as `temperature_k()` / `temperatureK()`; subtract 273.15
for degrees Celsius (e.g. `294` ≈ 21 °C).
In the host libraries both the temperature and PA5 ADC calls use `0xFFFF`
as their error/unavailable sentinel.

## 6. Persist configuration to EEPROM

`W [0x1A]` with **no payload** (STOP only) writes the current pin modes **and the
I²C address** to the module's EEPROM so they survive reset/power loss.

```
W [0x10, 0x00]        # PA5 output
W [0x12, 0x00]        # PB2 output
...                    # final configuration
W [0x1A]              # persist once, at teardown
```

Because applies are RAM-only, call `0x1A` once when the configuration is final.
A redundant save (nothing changed since the last) is a harmless no-op. Expect a
brief NVM stall (~3 ms) while the EEPROM writes.

## 7. Change the module's I²C address

`W [0x16, addr]` changes the module's address live, applied from STOP. Valid
addresses are `0x6A`–`0x6F`. Persist the new address with `0x1A` so it survives a
reset.

```
W [0x16, 0x6C]        # module answers at 0x6C from now on
W [0x1A]              # persist it
```

Remember to update the address your master uses afterwards, and keep track of the
module — all six addresses are discoverable by the Qwiic driver.

## 8. Blinking a pin from raw commands

```
W [0x14, 0x00]        # PB3 = output
loop:
    W [0x15, 0x01]    # PB3 high
    delay(200)
    W [0x15, 0x00]    # PB3 low
    delay(200)
```

For precisely-timed pulses, generating edges over I²C is limited by bus latency.
Use the module-side [bit-bang script engine](Bit-Bang-Engine.md) instead — it runs
on the module with interrupts masked and needs no host involvement.

## See also

- [Bit-Bang Engine](Bit-Bang-Engine.md) — timed pin edges and WS2812B
- [Protocol Reference](Protocol-Reference.md#3-expansion-pins-and-housekeeping) — command table
- [Error Codes](Error-Codes.md)
