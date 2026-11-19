#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex3_pins_and_neopixel.py
#
# Drive the module's expansion pins and latch a WS2812B frame through the
# module's bit-bang engine. The frame is clocked out by the module, so the host
# touches no GPIO at all.
#
# Rules the example follows:
#   * the pin must be a digital output before the engine can drive it;
#   * a frame holds at most 85 pixels (255 of the 256 B workspace);
#   * leave a frame time (~30 us/pixel plus the latch reset) before the next
#     I2C command.
#-------------------------------------------------------------------------------
import sys
import time

import qwiic_sd_expansion_py
from qwiic_sd_expansion_py import MICROSDEXP_PIN_PB2


def run_example():
    microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    # Digital output, applied in RAM only.
    if not microSDexp.set_pin_mode(MICROSDEXP_PIN_PB2, 0):
        print("Unable to set PB2 as an output (error %d)" % microSDexp.last_error)
        return

    # Blink a plain output pin.
    for _ in range(4):
        microSDexp.write_pin(MICROSDEXP_PIN_PB2, 1)
        time.sleep(0.25)
        microSDexp.write_pin(MICROSDEXP_PIN_PB2, 0)
        time.sleep(0.25)

    # Persist the pin modes (and I2C address) so they survive a power cycle.
    microSDexp.save_pin_mode()

    # Red, green, blue, then off -- raw GRB triplets, 4 pixels.
    frames = {
        "red": bytes([0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        "green": bytes([255, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        "blue": bytes([0, 0, 255, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
        "off": bytes(12),
    }
    for name, frame in frames.items():
        if not microSDexp.show_neopixels(MICROSDEXP_PIN_PB2, frame, 4):
            print("NeoPixel frame %s failed (error %d)" % (name, microSDexp.last_error))
            return
        print("Latched", name)
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit) as exErr:
        print("\nEnding ex3_pins_and_neopixel")
        sys.exit(0)
