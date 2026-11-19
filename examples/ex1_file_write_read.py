#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex1_file_write_read.py
#
# Write a file to the micro-SD card, close it (which waits until the data is
# committed), then read it back.
#
# Works two ways:
#   * with the Qwiic package installed -- the driver is discovered on the bus
#     and constructed from the scan result;
#   * standalone -- import the driver directly.
#-------------------------------------------------------------------------------
import sys

try:
    import qwiic
    _HAVE_QWIIC = True
except ImportError:
    _HAVE_QWIIC = False

import qwiic_sd_expansion_py


def run_example():
    microSDexp = None

    if _HAVE_QWIIC:
        print("Scanning the I2C bus for Qwiic devices...")
        devices = qwiic.list_devices()
        print("Found:", devices)
        for device in devices:
            if device[1] == qwiic_sd_expansion_py.QwiicSDExpansion.device_name:
                microSDexp = qwiic.create_device(device)
                break
        if microSDexp is None:
            print("No I2C microSD Expansion found on the bus.")
            return

    if microSDexp is None:
        microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()

    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    print("Module firmware:", microSDexp.version())

    f = microSDexp.open("HELLO.TXT", "w")
    if f is None:
        print("Unable to open HELLO.TXT for writing (error %d)" % microSDexp.last_error)
        return
    f.write(b"HELLO-WORLD")
    print("HELLO.TXT closed on card:", f.close())

    r = microSDexp.open("HELLO.TXT", "r")
    if r is None:
        print("Unable to open HELLO.TXT for reading (error %d)" % microSDexp.last_error)
        return
    print("Read back:", r.read(32))
    r.close()


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit) as exErr:
        print("\nEnding ex1_file_write_read")
        sys.exit(0)
