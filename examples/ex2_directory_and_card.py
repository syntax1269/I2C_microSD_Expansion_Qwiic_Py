#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex2_directory_and_card.py
#
# List the card's root directory, create and remove a directory, and print the
# card/volume snapshot reported by the module.
#-------------------------------------------------------------------------------
import sys

import qwiic_sd_expansion_py


def run_example():
    microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()  # default address 0x6E
    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    info = microSDexp.card_info()
    if info is None:
        print("Unable to read the card info (error %d)" % microSDexp.last_error)
        return
    print(
        "Card: mounted=%d fat=%d sectors=%d free_clusters=%d sck=%d Hz"
        % (
            info.mounted,
            info.fat_type,
            info.sector_count,
            info.free_clusters,
            info.sck_hz,
        )
    )

    if microSDexp.mkdir("LOGS"):
        print("Created LOGS")
    if microSDexp.exists("LOGS"):
        print("LOGS exists, is a directory:", microSDexp.is_directory("LOGS"))

    print("Root directory contents:")
    for entry in microSDexp.list_dir("/"):
        kind = "DIR " if entry.is_dir else "FILE"
        print("  %s %-20s %d" % (kind, entry.name, entry.size))

    print("LOGS removed:", microSDexp.rmdir("LOGS"))


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit) as exErr:
        print("\nEnding ex2_directory_and_card")
        sys.exit(0)
