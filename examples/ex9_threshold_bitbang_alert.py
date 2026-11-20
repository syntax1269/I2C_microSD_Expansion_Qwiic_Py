#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex9_threshold_bitbang_alert.py
#
# The module alone produces the timed alert (port of ThresholdBitbangAlert.ino).
# Every 500 ms the host reads adc_pa5() and temperature_k() and appends a CSV
# row. When the ADC crosses THRESHOLD it loads a 300 ms strobe script into the
# module's bit-bang workspace and starts it on PB2. The module plays the pulse
# train itself; the host keeps the I2C bus quiet for the script duration.
#
# Wiring: LED + resistor (or a scope probe) on PB2; a sensor on PA5 makes the
# threshold meaningful.
#-------------------------------------------------------------------------------
import time

import qwiic_sd_expansion_py
from qwiic_sd_expansion_py import MICROSDEXP_PIN_PB2, MICROSDEXP_BITBANG_PROFILE_SCRIPT

THRESHOLD = 3000
RUN_S = 30.0
STROBE_S = 0.31  # 300 ms script + slack

# 3 x (50 ms high, 50 ms low). Offsets: 0 SET_HIGH, 1 DELAY_MS(50),
# 3 SET_LOW, 4 DELAY_MS(50), 6 LOOP_GOTO(target 0, 3 passes).
STROBE = bytes(
    [
        0x01, 0x04, 50,
        0x02, 0x04, 50,
        0x05, 0x00, 3,
    ]
)


def run_example():
    microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    if (not microSDexp.set_pin_mode(MICROSDEXP_PIN_PB2, 0)
            or not microSDexp.bitbang_set_mode(MICROSDEXP_PIN_PB2)):
        print("threshold_bitbang_alert: pin setup failed")
        return
    microSDexp.bitbang_clear()  # no stale tokens behind the strobe

    f = microSDexp.open("ALERT.CSV", "w")
    if f is None:
        print("threshold_bitbang_alert: open failed")
        return
    f.write(b"millis,adc,tempK,alert\n")
    start = time.monotonic()
    alerts = 0

    while time.monotonic() - start < RUN_S:
        adc = microSDexp.adc_pa5()
        temp_k = microSDexp.temperature_k()
        alert = adc != 0xFFFF and adc >= THRESHOLD
        now_ms = int((time.monotonic() - start) * 1000)
        f.write(("%d,%d,%d,%d\n" % (now_ms, adc, temp_k, 1 if alert else 0)).encode("ascii"))

        if alert:
            alerts += 1
            if not microSDexp.bitbang_buffer(0, STROBE):
                print("threshold_bitbang_alert: strobe buffer FAILED")
            elif not microSDexp.bitbang_execute(MICROSDEXP_BITBANG_PROFILE_SCRIPT):
                print("threshold_bitbang_alert: strobe execute FAILED")
            else:
                time.sleep(STROBE_S)  # module is playing: keep the bus quiet

        time.sleep(0.5)  # ~2 Hz sample cadence when no alert is firing

    f.close()
    print("threshold_bitbang_alert: DONE alerts=%d" % alerts)


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit):
        pass
