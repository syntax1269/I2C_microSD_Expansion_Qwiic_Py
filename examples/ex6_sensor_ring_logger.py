#!/usr/bin/env python
#-------------------------------------------------------------------------------
# ex6_sensor_ring_logger.py
#
# High-frequency logging with a local ring buffer (port of SensorRingLogger.ino).
# A 500 Hz producer fills a 512-byte ring while write_now() drains it as fast
# as the module accepts bytes. When the module is busy (flash-page erase)
# write_now() returns 0 and the samples just wait in the ring, so an SD stall
# never delays the sampling loop.
#-------------------------------------------------------------------------------
import time

import qwiic_sd_expansion_py
from qwiic_sd_expansion_py import AsyncOp, ASYNC_BUSY, ASYNC_OK

SAMPLE_S = 0.002
RUN_S = 10.0
RING_BYTES = 512       # power of two -> cheap wrap
MASK = RING_BYTES - 1


def run_example():
    microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
    if not microSDexp.begin():
        print("Module did not answer. Check the wiring and the I2C address.")
        return

    op = AsyncOp()
    if not microSDexp.begin_open_write("SENSOR.CSV", op):
        print("Open submit failed")
        return
    while microSDexp.poll_op(op) == ASYNC_BUSY:
        pass
    if microSDexp.poll_op(op) != ASYNC_OK:
        print("Open failed")
        return

    baseline = microSDexp.committed_bytes()
    ring = bytearray(RING_BYTES)
    head = tail = used = 0
    produced = dropped = pushed = 0
    next_sample = start = time.monotonic()

    print("sensor_ring_logger: sampling at 500 Hz for 10 s")
    while True:
        now = time.monotonic()

        # ---- Producer: one 4-byte sample every 2 ms -----------------------
        if now >= next_sample:
            next_sample += SAMPLE_S
            if next_sample < now:  # resync instead of burst-catch-up
                next_sample = now + SAMPLE_S
            tick = int(now * 1000)
            value = 512 + ((tick // 4) & 0x3FF)  # simulated 10-bit sensor
            sample = bytes((tick & 0xFF, (tick >> 8) & 0xFF,
                            value & 0xFF, (value >> 8) & 0xFF))
            if used + len(sample) <= RING_BYTES:
                for byte in sample:
                    ring[head] = byte
                    head = (head + 1) & MASK
                used += len(sample)
                produced += 1
            else:
                dropped += 1

        # ---- Consumer: push only what RX can accept right now -------------
        if used:
            n = min(used, 64, RING_BYTES - tail)
            chunk = bytes(ring[tail : tail + n])
            accepted = microSDexp.write_now(chunk)
            if accepted:
                tail = (tail + accepted) & MASK
                used -= accepted
                pushed += accepted
            # 0 = module busy: leave the bytes in the ring and retry

        # ---- Finish: drain, wait for commit, close ------------------------
        if now - start >= RUN_S and used == 0:
            while microSDexp.committed_bytes() < baseline + pushed:
                pass
            op = AsyncOp()
            ok = False
            if microSDexp.begin_close(op):
                while microSDexp.poll_op(op) == ASYNC_BUSY:
                    pass
                ok = microSDexp.poll_op(op) == ASYNC_OK
            print("sensor_ring_logger: %s produced=%d dropped=%d pushed=%d"
                  % ("DONE" if ok else "CLOSE ERROR", produced, dropped, pushed))
            break


if __name__ == "__main__":
    try:
        run_example()
    except (KeyboardInterrupt, SystemExit):
        pass
