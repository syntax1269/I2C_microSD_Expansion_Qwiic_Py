# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""Desktop tests for the qwiic_sd_expansion_py driver (no hardware required).

Run from the library directory:

    python -m unittest discover -s tests -v

The suite drives the real driver against an in-memory module
(``tests/mock_qwiic.py``), so it covers the wire protocol, the flow pacing, the
Qwiic discovery metadata and the file/pin APIs.
"""

import unittest

import mock_qwiic
import qwiic_sd_expansion_py
from qwiic_sd_expansion_py import QwiicSDExpansion


def make_device(**kwargs):
    bus = mock_qwiic.MockI2CDriver()
    return QwiicSDExpansion(i2c_driver=bus, **kwargs), bus


class TestQwiicContract(unittest.TestCase):
    def test_discovery_metadata(self):
        dev = QwiicSDExpansion
        self.assertEqual(dev.device_name, "I2C microSD Expansion")
        self.assertEqual(dev.available_addresses[0], 0x6E)
        self.assertEqual(
            sorted(dev.available_addresses), [0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F]
        )
        # Qwiic_Py derives the class name from the module name by title-casing
        # the underscored parts; the alias must satisfy that lookup.
        derived = "Qwiic" + "".join(
            part.title() for part in "qwiic_sd_expansion_py".split("_")[1:]
        )
        self.assertEqual(derived, "QwiicSdExpansionPy")
        self.assertTrue(hasattr(qwiic_sd_expansion_py, derived))
        self.assertIs(getattr(qwiic_sd_expansion_py, derived), QwiicSDExpansion)

    def test_constructor_signature_defaults(self):
        microSDexp = QwiicSDExpansion(i2c_driver=mock_qwiic.MockI2CDriver())
        self.assertEqual(microSDexp.address, 0x6E)
        # A bogus address falls back to the default, like other Qwiic drivers
        microSDexp = QwiicSDExpansion(address=0x6C, i2c_driver=mock_qwiic.MockI2CDriver())
        self.assertEqual(microSDexp.address, 0x6C)

    def test_connected_and_begin(self):
        microSDexp, _bus = make_device()
        self.assertTrue(microSDexp.is_connected())
        self.assertTrue(microSDexp.connected)
        self.assertTrue(microSDexp.begin())

    def test_begin_scans_runtime_address_range(self):
        bus = mock_qwiic.MockI2CDriver()
        bus.microSDexp.device_address = 0x6B
        microSDexp = QwiicSDExpansion(i2c_driver=bus)
        self.assertFalse(microSDexp.is_connected())
        self.assertTrue(microSDexp.begin())
        self.assertEqual(microSDexp.address, 0x6B)

    def test_sticky_error(self):
        dev, bus = make_device()
        self.assertTrue(dev.begin())
        self.assertEqual(dev.sticky_error, qwiic_sd_expansion_py.MicroSDExpError.OK)
        self.assertFalse(dev.bitbang_set_mode(7))
        self.assertEqual(dev.last_error, qwiic_sd_expansion_py.MicroSDExpError.INVALID)
        self.assertTrue(dev.version())       # later successful call
        self.assertEqual(dev.last_error, qwiic_sd_expansion_py.MicroSDExpError.OK)
        self.assertEqual(dev.sticky_error, qwiic_sd_expansion_py.MicroSDExpError.INVALID)
        dev.clear_error()
        self.assertEqual(dev.sticky_error, qwiic_sd_expansion_py.MicroSDExpError.OK)
        self.assertEqual(dev.last_error, qwiic_sd_expansion_py.MicroSDExpError.OK)

    def test_no_module(self):
        bus = mock_qwiic.MockI2CDriver(microSDexp=mock_qwiic.MockMicroSDExp(address=0x50))
        microSDexp = QwiicSDExpansion(i2c_driver=bus)
        self.assertFalse(microSDexp.is_connected())
        self.assertFalse(microSDexp.begin())
        self.assertEqual(microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.NO_MODULE)
        self.assertEqual(microSDexp.version(), "")


class TestFileApi(unittest.TestCase):
    def test_write_read_roundtrip(self):
        microSDexp, bus = make_device()
        self.assertTrue(microSDexp.begin())

        f = microSDexp.open("HELLO.TXT", "w")
        self.assertIsNotNone(f)
        self.assertEqual(f.write(b"HELLO-WORLD"), 11)
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("HELLO.TXT"), b"HELLO-WORLD")

        r = microSDexp.open("HELLO.TXT", "r")
        self.assertEqual(r.read(32), b"HELLO-WORLD")
        self.assertEqual(r.read(8), b"")
        r.close()

    def test_large_write_is_chunked_within_block_limit(self):
        microSDexp, bus = make_device()
        payload = bytes(bytearray(range(200))) * 2  # 400 bytes
        f = microSDexp.open("BIG.BIN", "w")
        self.assertEqual(f.write(payload), len(payload))
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("BIG.BIN"), payload)
        self.assertLessEqual(bus.microSDexp.largest_write_payload, 32)

    def test_write_chunk_is_configurable(self):
        microSDexp, bus = make_device()
        microSDexp.set_write_chunk_bytes(16)
        self.assertEqual(microSDexp.write_chunk_bytes(), 16)
        f = microSDexp.open("TUNE.BIN", "w")
        f.write(bytes(50))
        f.close()
        self.assertEqual(len(bus.microSDexp.file_bytes("TUNE.BIN")), 50)
        self.assertLessEqual(bus.microSDexp.largest_write_payload, 16)

        microSDexp.set_write_chunk_bytes(999)
        self.assertEqual(microSDexp.write_chunk_bytes(), 128)

    def test_circuitpython_defaults_to_full_rx_block(self):
        # busio.I2C has no SMBus 32 B ceiling, so on CircuitPython the driver
        # starts at the firmware's 128 B RX block. Other backends stay at 32.
        microSDexp, _bus = make_device()
        self.assertEqual(microSDexp.write_chunk_bytes(), 32)

        real_sys = qwiic_sd_expansion_py.sys

        class _FakeCircuitPython(object):
            class implementation(object):
                name = "circuitpython"

        qwiic_sd_expansion_py.sys = _FakeCircuitPython
        try:
            microSDexp, _bus = make_device()
            self.assertEqual(microSDexp.write_chunk_bytes(), 128)
        finally:
            qwiic_sd_expansion_py.sys = real_sys

    def test_write_polls_status_only_on_nack(self):
        # The ACK path must not spend a STATUS turnaround per chunk: the
        # firmware publishes one RX block per transaction, so a fresh push is
        # always placeable.
        microSDexp, bus = make_device()
        f = microSDexp.open("PACE.BIN", "w")
        bus.microSDexp.status_reads = 0
        self.assertEqual(f.write(bytes(1024)), 1024)
        self.assertEqual(bus.microSDexp.status_reads, 0)
        self.assertTrue(f.close())
        self.assertEqual(len(bus.microSDexp.file_bytes("PACE.BIN")), 1024)

    def test_write_retries_after_nack(self):
        microSDexp, bus = make_device()
        microSDexp.set_flow_poll_ms(0)
        payload = b"0123456789" * 10
        f = microSDexp.open("RETRY.BIN", "w")
        bus.microSDexp.nack_writes = 3
        self.assertEqual(f.write(payload), len(payload))
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("RETRY.BIN"), payload)
        self.assertGreaterEqual(bus.microSDexp.status_reads, 1)

    def test_ack_paced_push_uses_full_chunk(self):
        # ACK pacing should fill each transaction to the configured chunk
        # instead of hesitating over a partly drained RX block.
        microSDexp, bus = make_device()
        microSDexp.set_write_chunk_bytes(16)
        payload = bytes(bytearray(range(50)))
        f = microSDexp.open("CHUNK.BIN", "w")
        self.assertEqual(f.write(payload), len(payload))
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("CHUNK.BIN"), payload)
        self.assertEqual(bus.microSDexp.write_payload_sizes[:3], [16, 16, 16])

    def test_flow_poll_is_configurable(self):
        microSDexp, _bus = make_device()
        self.assertEqual(microSDexp.flow_poll_ms(), 2)
        microSDexp.set_flow_poll_ms(0)
        self.assertEqual(microSDexp.flow_poll_ms(), 0)
        microSDexp.set_flow_poll_ms(-5)
        self.assertEqual(microSDexp.flow_poll_ms(), 0)
        microSDexp.set_flow_poll_ms(4)
        self.assertEqual(microSDexp.flow_poll_ms(), 4)

    def test_portable_path_when_no_raw_bus(self):
        microSDexp, _bus = make_device()
        self.assertIsNone(microSDexp._raw_i2c)
        self.assertIsNone(microSDexp._raw_read)

    def test_raw_bus_write_and_read_roundtrip(self):
        # CircuitPython exposes busio.I2C as `_i2cbus`; the driver should
        # detect it and stream 128 B blocks through reusable buffers instead
        # of rebuilding a boxed list per transaction.
        bus = mock_qwiic.MockI2CDriver(raw=True)
        microSDexp = QwiicSDExpansion(i2c_driver=bus)
        self.assertTrue(microSDexp.begin())
        self.assertIsNotNone(microSDexp._raw_i2c)
        self.assertIsNotNone(microSDexp._raw_read)
        microSDexp.set_write_chunk_bytes(128)

        payload = bytes(bytearray((i * 7 + 3) & 0xFF for i in range(4096)))
        f = microSDexp.open("RAW.BIN", "w")
        self.assertEqual(f.write(payload), len(payload))
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("RAW.BIN"), payload)
        self.assertEqual(bus.microSDexp.largest_write_payload, 128)
        self.assertGreater(bus.raw.writes, 0)

        r = microSDexp.open("RAW.BIN", "r")
        self.assertEqual(r.read(len(payload)), payload)
        self.assertTrue(r.close())
        self.assertGreater(bus.raw.reads, 0)

    def test_raw_write_retries_after_nack(self):
        bus = mock_qwiic.MockI2CDriver(raw=True)
        microSDexp = QwiicSDExpansion(i2c_driver=bus)
        self.assertTrue(microSDexp.begin())
        microSDexp.set_write_chunk_bytes(128)
        payload = b"0123456789" * 10
        f = microSDexp.open("RAW_NACK.BIN", "w")
        bus.microSDexp.nack_writes = 2
        self.assertEqual(f.write(payload), len(payload))
        self.assertTrue(f.close())
        self.assertEqual(bus.microSDexp.file_bytes("RAW_NACK.BIN"), payload)
        self.assertGreaterEqual(bus.microSDexp.status_reads, 1)

    def test_raw_read_error_sets_no_module(self):
        bus = mock_qwiic.MockI2CDriver(raw=True)
        microSDexp = QwiicSDExpansion(i2c_driver=bus)
        self.assertIsNotNone(microSDexp._raw_read)

        def boom(*args, **kwargs):
            raise OSError(5, "bus error")

        bus.raw.writeto_then_readfrom = boom
        self.assertIsNone(
            microSDexp._read(qwiic_sd_expansion_py.MICROSDEXP_CMD_STATUS, 12)
        )
        self.assertEqual(
            microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.NO_MODULE
        )
        # The failed attempt must not leave the bus locked.
        self.assertTrue(bus.raw.try_lock())
        bus.raw.unlock()

    def test_append(self):
        microSDexp, bus = make_device()
        f = microSDexp.open("LOG.TXT", "a")
        f.write(b"one\n")
        f.write(b"two\n")
        f.close()
        self.assertEqual(bus.microSDexp.file_bytes("LOG.TXT"), b"one\ntwo\n")

    def test_queries_and_listing(self):
        microSDexp, bus = make_device()
        bus.microSDexp.seed_file("DATA.BIN", b"12345")
        bus.microSDexp.seed_file("SUB/IN.TXT", b"x")
        bus.microSDexp._dirs.add("/SUB")

        self.assertTrue(microSDexp.exists("DATA.BIN"))
        self.assertFalse(microSDexp.exists("NOPE.BIN"))
        self.assertEqual(microSDexp.file_size("DATA.BIN"), 5)
        self.assertEqual(microSDexp.file_size("NOPE.BIN"), 0)
        self.assertTrue(microSDexp.is_directory("SUB"))
        self.assertFalse(microSDexp.is_directory("DATA.BIN"))

        self.assertTrue(microSDexp.mkdir("NEWDIR"))
        self.assertTrue(microSDexp.exists("NEWDIR"))
        self.assertTrue(microSDexp.rmdir("NEWDIR"))
        self.assertFalse(microSDexp.exists("NEWDIR"))

        self.assertTrue(microSDexp.remove("DATA.BIN"))
        self.assertFalse(microSDexp.exists("DATA.BIN"))

        entries = microSDexp.list_dir("/")
        self.assertEqual(
            [(e.is_dir, e.name, e.size) for e in entries], [(False, "SUB/IN.TXT", 1)]
        )

    def test_invalid_paths_send_nothing(self):
        microSDexp, bus = make_device()
        before = bus.microSDexp.transactions
        self.assertFalse(microSDexp.exists(""))
        self.assertFalse(microSDexp.mkdir("X" * 300))
        self.assertIsNone(microSDexp.open("", "r"))
        self.assertEqual(microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.INVALID)
        self.assertEqual(bus.microSDexp.transactions, before)

    def test_card_info_and_version(self):
        microSDexp, _bus = make_device()
        # Firmware >= 18.8.0 answers 0x0F with a multi-line banner; the API
        # still returns just the version token.
        self.assertEqual(microSDexp.version(), "18.8.22")
        self.assertEqual(microSDexp.firmware_clock_hz(), 20000000)
        banner = microSDexp.firmware_banner()
        self.assertIn("I2C microSD Expansion v18.8.22", banner)
        info = microSDexp.card_info()
        self.assertEqual(info.mounted, 1)
        self.assertEqual(info.fat_type, qwiic_sd_expansion_py.MICROSDEXP_FAT32)
        self.assertEqual(info.sector_count, 8388608)
        self.assertEqual(info.sck_hz, 5000000)

    def test_version_legacy_short_form(self):
        microSDexp, bus = make_device()
        bus.microSDexp._version = b"18.7.6"
        self.assertEqual(microSDexp.version(), "18.7.6")
        self.assertEqual(microSDexp.firmware_clock_hz(), 0)

    def test_op_completion_ignores_reboot(self):
        microSDexp, bus = make_device()
        self.assertTrue(microSDexp.begin())
        bus.microSDexp._op_done = 41
        # A module reset wraps opDone to 0 without completing anything.
        bus.microSDexp._op_done = 0
        bus.microSDexp._state = qwiic_sd_expansion_py.MICROSDEXP_ST_IDLE
        self.assertEqual(microSDexp.wait_for_op_complete(41, timeout_ms=20), -1)
        self.assertEqual(
            microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.TIMEOUT
        )
        # A real completion is still reported.
        self.assertTrue(microSDexp.mkdir("REALDIR"))
        done = bus.microSDexp._op_done
        self.assertEqual(microSDexp.wait_for_op_complete(done - 1), 0)

    def test_format(self):
        microSDexp, bus = make_device()
        bus.microSDexp.seed_file("OLD.TXT", b"x")
        self.assertTrue(microSDexp.format(0))
        self.assertFalse(microSDexp.exists("OLD.TXT"))


class TestPinsAndBitBang(unittest.TestCase):
    def test_pin_mode_dedup_and_save(self):
        microSDexp, bus = make_device()
        self.assertTrue(microSDexp.set_pin_mode(qwiic_sd_expansion_py.MICROSDEXP_PIN_PA5, 0))
        after_first = bus.microSDexp.transactions
        self.assertTrue(microSDexp.set_pin_mode(qwiic_sd_expansion_py.MICROSDEXP_PIN_PA5, 0))
        self.assertEqual(bus.microSDexp.transactions, after_first)
        self.assertTrue(microSDexp.write_pin(qwiic_sd_expansion_py.MICROSDEXP_PIN_PA5, 1))

        self.assertFalse(bus.microSDexp._eeprom_saved)
        self.assertTrue(microSDexp.save_pin_mode())
        self.assertTrue(bus.microSDexp._eeprom_saved)

        self.assertFalse(microSDexp.set_pin_mode(99, 0))
        self.assertEqual(microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.INVALID)

    def test_neopixel_frame_limits_and_chunking(self):
        microSDexp, bus = make_device()
        self.assertTrue(microSDexp.set_pin_mode(qwiic_sd_expansion_py.MICROSDEXP_PIN_PB2, 0))

        frame = bytes(bytearray(range(255)))
        self.assertTrue(microSDexp.show_neopixels(qwiic_sd_expansion_py.MICROSDEXP_PIN_PB2, frame))
        self.assertEqual(bus.microSDexp._bb_pin, qwiic_sd_expansion_py.MICROSDEXP_PIN_PB2)
        self.assertEqual(bytes(bus.microSDexp._bb_ws[:255]), frame)
        self.assertEqual(bus.microSDexp._bb_len, 255)
        self.assertEqual(
            bus.microSDexp._bb_profile, qwiic_sd_expansion_py.MICROSDEXP_BITBANG_PROFILE_NEOPIXEL
        )
        self.assertLessEqual(bus.microSDexp.largest_write_payload, 32)

        # 86 pixels = 258 bytes does not fit the 256 B workspace
        self.assertFalse(
            microSDexp.show_neopixels(qwiic_sd_expansion_py.MICROSDEXP_PIN_PB2, bytes(258))
        )
        self.assertEqual(microSDexp.last_error, qwiic_sd_expansion_py.MicroSDExpError.INVALID)

    def test_bitbang_clear(self):
        microSDexp, bus = make_device()
        microSDexp.bitbang_buffer(0, b"\xaa" * 40)
        self.assertTrue(microSDexp.bitbang_clear())
        self.assertEqual(bus.microSDexp._bb_len, 0)
        self.assertEqual(bytes(bus.microSDexp._bb_ws), bytes(256))

    def test_bitbang_workspace_bounds(self):
        microSDexp, bus = make_device()
        invalid = qwiic_sd_expansion_py.MicroSDExpError.INVALID

        # Filling the workspace to the last byte is legal.
        self.assertTrue(microSDexp.bitbang_buffer(240, bytes(16)))
        self.assertEqual(bus.microSDexp._bb_len, 256)
        self.assertTrue(microSDexp.bitbang_buffer(255, bytes(1)))

        # A request that would cross the 256 B end is refused, not clipped.
        self.assertFalse(microSDexp.bitbang_buffer(240, bytes(17)))
        self.assertEqual(microSDexp.last_error, invalid)
        self.assertFalse(microSDexp.bitbang_buffer(255, bytes(2)))
        self.assertFalse(microSDexp.bitbang_buffer(256, bytes(1)))
        self.assertFalse(microSDexp.bitbang_buffer(-1, bytes(1)))
        self.assertFalse(microSDexp.bitbang_buffer(0, b""))

        # The whole workspace in one call (split into transactions).
        self.assertTrue(microSDexp.bitbang_buffer(0, bytes(256)))
        self.assertEqual(bus.microSDexp._bb_len, 256)
        self.assertLessEqual(bus.microSDexp.largest_write_payload, 32)


if __name__ == "__main__":
    unittest.main()
