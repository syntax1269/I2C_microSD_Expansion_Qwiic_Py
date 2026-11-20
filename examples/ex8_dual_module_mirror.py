#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex8_dual_module_mirror.py
#
# Two modules, one bus, automatic failover (port of DualModuleMirror.ino).
# moduleA is at 0x6E, moduleB at 0x6C. Every frame is appended to both cards;
# when a sticky_error appears on Card A the sketch keeps logging to Card B.
#
# Provisioning (one time): both modules ship at 0x6E. Set PROVISION_MODULE_B
# below to True, DISCONNECT MODULE A first, run once and confirm, then reconnect
# A and set the flag back to False. The address command changes every module
# still at 0x6E, so never run it with both modules attached.
#-------------------------------------------------------------------------------
import time

import qwiic_sd_expansion_py

# One-time provisioning. True ONLY for one run, after disconnecting module A.
PROVISION_MODULE_B = False


def provision_module_b():
    """Set the single remaining module's address to 0x6C and persist it."""
    print("PROVISION: disconnect module A from the I2C bus now.")
    answer = input("Type Y and Enter to set the remaining module to 0x6C: ")
    if answer.strip().upper() != "Y":
        print("PROVISION: cancelled - no address was changed")
        return False
    dev = qwiic_sd_expansion_py.QwiicSDExpansion(address=0x6E)
    if not dev.begin():
        print("PROVISION: no module answered at 0x6E")
        return False
    if not dev.change_address(0x6C):
        print("PROVISION: SET_ADDR failed")
        return False
    dev.save_pin_mode()  # persist the new address in module EEPROM
    print("PROVISION: module B is now 0x6C (saved to EEPROM).")
    print("PROVISION: reconnect module A, then restart this example.")
    return True


def run_example():
    if PROVISION_MODULE_B and not provision_module_b():
        print("dual_module_mirror: provisioning aborted")
        return

    card_a = qwiic_sd_expansion_py.QwiicSDExpansion(address=0x6E)
    card_b = qwiic_sd_expansion_py.QwiicSDExpansion(address=0x6C)

    a_up = card_a.begin()
    b_up = card_b.begin()
    if not a_up:
        print("dual_module_mirror: module A (0x6E) not found")
    if not b_up:
        print("dual_module_mirror: module B (0x6C) not found")

    # Start with a clean latch so the first real failure is easy to spot.
    card_a.clear_error()
    card_b.clear_error()
    print("A: %s addr=0x%02X sticky=%d"
          % ("UP" if a_up else "DOWN", card_a.address, card_a.sticky_error))
    print("B: %s addr=0x%02X sticky=%d"
          % ("UP" if b_up else "DOWN", card_b.address, card_b.sticky_error))

    frame_no = 0
    while a_up or b_up:
        frame_no += 1
        frame = ("%d,%f\n" % (frame_no, time.monotonic())).encode("ascii")

        if a_up:
            try:
                with card_a.open("MIRROR.CSV", "a") as f:
                    f.write(frame)
            except OSError:
                pass
            if not card_a.last_ok or card_a.sticky_error != 0:
                a_up = False
                print("dual_module_mirror: Card A FAILED -> failing over to B")
                print("A: DOWN sticky=%d" % card_a.sticky_error)

        if b_up:
            try:
                with card_b.open("MIRROR.CSV", "a") as f:
                    f.write(frame)
            except OSError:
                pass
            if not card_b.last_ok or card_b.sticky_error != 0:
                b_up = False
                print("dual_module_mirror: Card B FAILED")
                print("B: DOWN sticky=%d" % card_b.sticky_error)

        print("frame %d -> %s" % (frame_no, "A+B" if a_up else "B only"))
        time.sleep(0.5)

    if not (a_up or b_up):
        print("dual_module_mirror: no module available")


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit):
        pass
