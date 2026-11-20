#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex7_config_save_load.py
#
# Persistent settings with checked queries and a staged update.
# exists_checked() / file_size_checked() keep "missing" distinct from an
# I2C/card error. A new config is staged in CONFIG.TMP, the live file is
# removed, then the staged bytes are rewritten as CONFIG.INI. The module has
# no atomic rename, so the config carries a checksum: a power loss in that
# small window is detected at boot and falls back to defaults, never to a
# half-written setting the sketch would act on.
#-------------------------------------------------------------------------------
import qwiic_sd_expansion_py

CFG_PATH = "CONFIG.INI"
TMP_PATH = "CONFIG.TMP"


def checksum(prefix):
    value = 0
    for byte in prefix:
        value ^= byte
    return value


def format_config(threshold, interval_ms):
    prefix = "T=%d,I=%d," % (threshold, interval_ms)
    return "%sX=%02X\n" % (prefix, checksum(prefix.encode("ascii")))


def parse_config(text):
    try:
        mark = text.index("X=")
        if int(text[mark + 2 :].strip(), 16) != checksum(text[:mark].encode("ascii")):
            return None
        threshold = int(text[text.index("T=") + 2 :].split(",")[0])
        interval = int(text[text.index("I=") + 2 :].split(",")[0])
        return (threshold, interval)
    except (ValueError, IndexError):
        return None


def write_all(dev, path, text):
    try:
        with dev.open(path, "w") as f:
            return f.write(text.encode("ascii"))
    except OSError:
        return False


def stage_and_install(dev, text):
    if not write_all(dev, TMP_PATH, text):
        return False
    if not dev.remove(CFG_PATH):
        return False
    if not write_all(dev, CFG_PATH, text):
        return False
    dev.remove(TMP_PATH)  # best-effort cleanup
    return True


def load_config(dev):
    ok, present = dev.exists_checked(CFG_PATH)
    if not ok:
        print("config_save_load: exists_checked FAILED (bus/card error)")
        return None
    if not present:
        return None
    ok, size = dev.file_size_checked(CFG_PATH)
    if not ok or size == 0 or size > 63:
        return None
    try:
        with dev.open(CFG_PATH, "r") as f:
            raw = f.read(size)
    except OSError:
        return None
    return parse_config(raw.decode("ascii", "ignore"))


def run_example():
    microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    cfg = load_config(microSDexp)
    if cfg is None:
        cfg = (512, 250)
        if not stage_and_install(microSDexp, format_config(*cfg)):
            print("config_save_load: failed to create defaults")
            return
        print("config_save_load: created default config")
    else:
        print("config_save_load: loaded existing config")

    print(format_config(*cfg).rstrip())

    # A settings change: bump the threshold and persist it safely.
    cfg = (768, cfg[1])
    if stage_and_install(microSDexp, format_config(*cfg)):
        print("config_save_load: settings updated")
    else:
        print("config_save_load: update FAILED - boot will fall back to defaults")


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit):
        pass
