# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT

"""mock_qwiic — desktop in-memory module for the qwiic_sd_expansion_py tests.

Provides a ``qwiic_i2c``-shaped bus driver (``MockI2CDriver``) on top of an
in-memory emulation of the I²C microSD Expansion module. No hardware and no
``qwiic_i2c`` install are required.

The emulation mirrors the real module closely enough for the suite:

* files are ``dict[path, bytearray]`` (paths normalized, leading slash
  stripped),
* ``op_done`` advances on every STOP operation and STATUS latches ``result``,
* WRITE appends to the open write file and ``result`` tracks committed bytes,
* READ stages file (or directory-stream) content into the TX buffer,
* LIST_DIR streams 'F'/'D' + NUL + size LE, 0xFF terminated,
* append (0x04) appends without opening a module file,
* SMBus I2C block writes are capped at 32 payload bytes, like smbus2.
"""

import os
import sys
import time
import types

# Make ``import qwiic_sd_expansion_py`` work on a desktop without the real qwiic_i2c
# package installed: register a minimal stand-in before the driver imports it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    import qwiic_i2c  # noqa: F401
except ImportError:
    _stub = types.ModuleType("qwiic_i2c")
    _stub.getI2CDriver = lambda *args, **kwargs: None
    sys.modules["qwiic_i2c"] = _stub

import qwiic_sd_expansion_py as protocol  # noqa: E402


class MockMicroSDExp(object):
    """In-memory I²C microSD Expansion module."""

    #: Mirror smbus2's I2C_SMBUS_BLOCK_MAX: a Linux qwiic_i2c backend rejects
    #: a larger payload, so the tests catch an over-sized WRITE chunk.
    MAX_BLOCK_WRITE = 32

    def __init__(self, address=0x6E, max_block_write=None):
        self.device_address = address
        self.max_block_write = (
            self.MAX_BLOCK_WRITE if max_block_write is None else max_block_write
        )
        self._files = {}
        self._dirs = {"/"}
        self._filename = ""
        self._open_path = None
        self._open_mode = None  # "w" | "r" | "readfile" | "list"
        self._write_pos = 0
        self._read_pos = 0
        self._op_done = 0
        self._state = protocol.MICROSDEXP_ST_IDLE
        self._pending_result = 0
        self._committed = 0
        # Firmware >= 18.8.0 answers 0x0F with the multi-line banner, not the
        # bare version. Tests override this to exercise the legacy shape.
        self._version = (
            b"Clock: 20000000 Hz (fuse OSCCFG=0x7E)\n"
            b"I2C microSD Expansion v18.8.22\n"
            b"Copyright (C) 2026 syntax1269@gmail.com\n"
        )
        self._list_payload = b""
        self._list_pos = 0
        self._pa5_mode = 0
        self._pb2_mode = 0
        self._pb3_mode = 0
        self._eeprom_saved = False
        self._clock = None
        self._rebooted = False
        # Bit-bang engine state (256 B workspace, buffered-length mark).
        self._bb_pin = 0
        self._bb_ws = bytearray(protocol.BITBANG_WORKSPACE_SIZE)
        self._bb_len = 0
        self._bb_profile = 0
        # Introspection for the tests.
        self.transactions = 0
        self.largest_write_payload = 0
        self.write_payload_sizes = []
        self.status_reads = 0
        # Test hook: fail this many CMD_WRITE transactions before accepting.
        self.nack_writes = 0

    # ---- helpers ----
    def _norm(self, path):
        p = path.strip()
        if p.startswith("/"):
            p = p[1:]
        return p

    def _bump(self, result=None):
        self._op_done = (self._op_done + 1) & 0xFF
        # completeOp() latches ST_COMPLETE and failOp() ST_ERROR; read and
        # list ops publish ST_TX_READY. Mirror that so a *state* check can
        # distinguish a completed op from a module that just rebooted.
        if self._state not in (
            protocol.MICROSDEXP_ST_TX_READY,
            protocol.MICROSDEXP_ST_ERROR,
        ):
            self._state = protocol.MICROSDEXP_ST_COMPLETE
        if result is not None:
            self._pending_result = result
            self._committed = result

    def seed_file(self, path, data):
        self._files[self._norm(path)] = bytearray(data)

    def file_bytes(self, path):
        return bytes(self._files.get(self._norm(path), bytearray()))

    def _status_bytes(self):
        tx_avail = 0
        if self._open_mode in ("r", "readfile") and self._open_path is not None:
            data = self._files.get(self._open_path, bytearray())
            tx_avail = min(128, max(0, len(data) - self._read_pos))
        elif self._open_mode == "list":
            tx_avail = min(128, max(0, len(self._list_payload) - self._list_pos))
        rx_free = 128 if self._open_mode == "w" else 0
        out = bytearray(12)
        out[0] = 2  # rev
        out[1] = self._state
        out[2] = self._op_done
        out[3] = protocol.MICROSDEXP_ERR_NONE
        out[4] = rx_free & 0xFF
        out[5] = (rx_free >> 8) & 0xFF
        out[6] = tx_avail & 0xFF
        out[7] = (tx_avail >> 8) & 0xFF
        r = self._pending_result
        out[8] = r & 0xFF
        out[9] = (r >> 8) & 0xFF
        out[10] = (r >> 16) & 0xFF
        out[11] = (r >> 24) & 0xFF
        return bytes(out)

    def _build_list(self):
        out = bytearray()
        for name in sorted(self._files):
            out.append(0x46)  # 'F'
            out.extend(name.encode("ascii"))
            out.append(0x00)
            sz = len(self._files[name])
            out.extend(
                bytes(
                    [sz & 0xFF, (sz >> 8) & 0xFF, (sz >> 16) & 0xFF, (sz >> 24) & 0xFF]
                )
            )
        out.append(protocol.LIST_END)
        return bytes(out)

    # ---- STOP transactions (writeCommand / writeBlock) ----
    def handle_write(self, cmd, data):
        self.transactions += 1
        if len(data) > self.max_block_write:
            raise OSError(3, "NACK: block write over %d bytes" % self.max_block_write)
        if len(data) > self.largest_write_payload:
            self.largest_write_payload = len(data)
        data = bytes(bytearray(data))
        if cmd == protocol.MICROSDEXP_CMD_WRITE:
            self.write_payload_sizes.append(len(data))

        if cmd == protocol.MICROSDEXP_CMD_FILENAME:
            if len(data) > 259:
                raise OSError(3, "NACK filename overflow")
            self._filename = data.split(b"\x00")[0].decode("ascii", "replace")
            return
        if cmd == protocol.MICROSDEXP_CMD_PA5_SET_MODE:
            if data and data[0] > 4:
                raise OSError(3, "NACK mode")
            self._pa5_mode = data[0] if data else 0
            return
        if cmd == protocol.MICROSDEXP_CMD_PB2_SET_MODE:
            if data and data[0] > 3:
                raise OSError(3, "NACK mode")
            self._pb2_mode = data[0] if data else 0
            return
        if cmd == protocol.MICROSDEXP_CMD_PB3_SET_MODE:
            if data and data[0] > 3:
                raise OSError(3, "NACK mode")
            self._pb3_mode = data[0] if data else 0
            return
        if cmd in (
            protocol.MICROSDEXP_CMD_PA5_CONTROL,
            protocol.MICROSDEXP_CMD_PB2_CONTROL,
            protocol.MICROSDEXP_CMD_PB3_CONTROL,
        ):
            mode = {
                protocol.MICROSDEXP_CMD_PA5_CONTROL: self._pa5_mode,
                protocol.MICROSDEXP_CMD_PB2_CONTROL: self._pb2_mode,
                protocol.MICROSDEXP_CMD_PB3_CONTROL: self._pb3_mode,
            }[cmd]
            if mode >= 2:
                raise OSError(3, "NACK control in input mode")
            return
        if cmd == protocol.MICROSDEXP_CMD_I2C_SET_ADDR:
            if not data or data[0] not in (0x6A, 0x6B, 0x6C, 0x6D, 0x6E, 0x6F):
                raise OSError(3, "NACK addr")
            self.device_address = data[0]
            return
        if cmd == protocol.MICROSDEXP_CMD_SAVEEEPROM:
            self._eeprom_saved = True
            return
        if cmd == protocol.MICROSDEXP_CMD_OPEN_WRITE:
            path = self._norm(data.split(b"\x00")[0].decode("ascii", "replace"))
            self._files[path] = bytearray()
            self._open_path = path
            self._open_mode = "w"
            self._write_pos = 0
            self._state = protocol.MICROSDEXP_ST_BUSY_SD
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_OPEN_READ:
            n = self._norm(data.split(b"\x00")[0].decode("ascii", "replace"))
            if n not in self._files:
                self._state = protocol.MICROSDEXP_ST_ERROR
                self._bump(0)
                return
            self._open_path = n
            self._open_mode = "r"
            self._read_pos = 0
            self._state = protocol.MICROSDEXP_ST_TX_READY
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_WRITE:
            if self.nack_writes:
                self.nack_writes -= 1
                raise OSError(3, "NACK: RX blocks busy")
            if self._open_mode != "w" or self._open_path is None:
                raise OSError(3, "NACK data")
            f = self._files[self._open_path]
            f.extend(data)
            self._write_pos += len(data)
            # The worker commits as it drains; surface progress via
            # STATUS.result so sync() (wait_for_committed) can complete.
            self._pending_result = len(f)
            self._committed = self._pending_result
            return
        if cmd == protocol.MICROSDEXP_CMD_READ:
            return  # STOP variant used to prime the read
        if cmd == protocol.MICROSDEXP_CMD_CLOSE_FLUSH:
            if self._open_mode == "w" and self._open_path is not None:
                self._pending_result = len(self._files[self._open_path])
                self._committed = self._pending_result
            self._open_path = None
            self._open_mode = None
            self._state = protocol.MICROSDEXP_ST_IDLE
            self._bump(self._pending_result)
            return
        if cmd == protocol.MICROSDEXP_CMD_APPEND_FILE:
            p = self._norm(self._filename)
            self._files.setdefault(p, bytearray())
            self._files[p].extend(data)
            self._pending_result = len(self._files[p])
            self._bump(self._pending_result)
            return
        if cmd in (
            protocol.MICROSDEXP_CMD_FILE_SIZE,
            protocol.MICROSDEXP_CMD_FILE_EXISTS,
            protocol.MICROSDEXP_CMD_IS_DIRECTORY,
            protocol.MICROSDEXP_CMD_LIST_DIR,
            protocol.MICROSDEXP_CMD_MAKE_DIR,
            protocol.MICROSDEXP_CMD_REMOVE_DIR,
            protocol.MICROSDEXP_CMD_REMOVE_FILE,
        ):
            p = self._norm(self._filename)
            if cmd == protocol.MICROSDEXP_CMD_FILE_SIZE:
                self._bump(len(self._files.get(p, bytearray())))
            elif cmd == protocol.MICROSDEXP_CMD_IS_DIRECTORY:
                self._bump(1 if (p == "" or ("/" + p) in self._dirs) else 0)
            elif cmd == protocol.MICROSDEXP_CMD_FILE_EXISTS:
                self._bump(1 if p in self._files or ("/" + p) in self._dirs else 0)
            elif cmd == protocol.MICROSDEXP_CMD_MAKE_DIR:
                if p and p not in self._files:
                    self._dirs.add("/" + p)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_REMOVE_FILE:
                self._files.pop(p, None)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_REMOVE_DIR:
                self._dirs.discard("/" + p)
                self._bump(0)
            elif cmd == protocol.MICROSDEXP_CMD_LIST_DIR:
                self._list_payload = self._build_list()
                self._list_pos = 0
                self._open_mode = "list"
                self._open_path = p
                self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_WRITE_FILE:
            p = self._norm(self._filename)
            self._files[p] = bytearray(data)
            self._pending_result = len(data)
            self._bump(len(data))
            return
        if cmd == protocol.MICROSDEXP_CMD_READ_FILE:
            p = self._norm(self._filename)
            if p not in self._files:
                self._state = protocol.MICROSDEXP_ST_ERROR
                self._bump(0)
                return
            self._open_path = p
            self._open_mode = "readfile"
            self._read_pos = 0
            self._state = protocol.MICROSDEXP_ST_TX_READY
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_FORMAT:
            if data and data[0] > 1:
                raise OSError(3, "NACK format mode")
            self._files = {}
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_CLOCK_SET:
            if len(data) != 6:
                raise OSError(3, "NACK clock len")
            self._clock = tuple(data)
            self._bump(0)
            return
        if cmd == protocol.MICROSDEXP_CMD_REBOOT:
            # A reset clears the sequence counter and the status mailbox.
            self._rebooted = True
            self._op_done = 0
            self._state = protocol.MICROSDEXP_ST_IDLE
            return
        if cmd == protocol.MICROSDEXP_CMD_BITBANG_SET_MODE:
            if not data or data[0] not in (2, 3, 5):
                raise OSError(3, "NACK bitbang pin")
            self._bb_pin = data[0]
            return
        if cmd == protocol.MICROSDEXP_CMD_BITBANG_BUFFER:
            # [offLSB, offMSB, len, ...data] — require the exact shape
            if len(data) < 3 or len(data) != 3 + data[2]:
                raise OSError(3, "NACK bitbang buffer")
            off = data[0] | (data[1] << 8)
            # The firmware NAKs data addressed past the 256 B workspace.
            if off >= protocol.BITBANG_WORKSPACE_SIZE or (
                off + data[2] > protocol.BITBANG_WORKSPACE_SIZE
            ):
                raise OSError(3, "NACK bitbang workspace overflow")
            for i in range(data[2]):
                self._bb_ws[off + i] = data[3 + i]
            end = min(protocol.BITBANG_WORKSPACE_SIZE, off + data[2])
            if end > self._bb_len:
                self._bb_len = end
            return
        if cmd == protocol.MICROSDEXP_CMD_BITBANG_EXECUTE:
            if not data:
                raise OSError(3, "NACK bitbang profile")
            self._bb_profile = data[0]
            return
        if cmd == protocol.MICROSDEXP_CMD_BITBANG_CLEAR:
            self._bb_ws = bytearray(protocol.BITBANG_WORKSPACE_SIZE)
            self._bb_len = 0
            return
        raise OSError(3, "unknown cmd 0x%02x" % cmd)

    # ---- repeated-START reads (writeReadBlock) ----
    def handle_read(self, cmd, want):
        self.transactions += 1
        if cmd == protocol.MICROSDEXP_CMD_STATUS:
            self.status_reads += 1
            data = self._status_bytes()
        elif cmd == protocol.MICROSDEXP_CMD_VERSION:
            data = self._version
        elif cmd == protocol.MICROSDEXP_CMD_TEMP_READ:
            data = bytes([0x10, 0x01])  # 0x0110 = 272 raw
        elif cmd == protocol.MICROSDEXP_CMD_ADC_READ_PA5:
            data = bytes([0x34, 0x12, 0x00])
        elif cmd == protocol.MICROSDEXP_CMD_ADC_READ_PB3:
            data = b"\xff"
        elif cmd == protocol.MICROSDEXP_CMD_PIN_STATE_READ:
            data = b"\x00"
        elif cmd == protocol.MICROSDEXP_CMD_CARD_INFO:
            data = (
                bytes([1, 32, 2, 0])
                + (8388608).to_bytes(4, "little")
                + (1048576).to_bytes(4, "little")
                + (4096).to_bytes(2, "little")
                + (0).to_bytes(2, "little")
                + (2097152).to_bytes(4, "little")
                + (5000000).to_bytes(4, "little")
            )
        elif cmd == protocol.MICROSDEXP_CMD_READ:
            if self._open_mode == "list":
                data = self._list_payload[self._list_pos : self._list_pos + want]
                self._list_pos += len(data)
                if self._list_pos >= len(self._list_payload):
                    self._open_mode = None
                    self._state = protocol.MICROSDEXP_ST_COMPLETE
            elif self._open_mode in ("r", "readfile") and self._open_path is not None:
                f = self._files[self._open_path]
                take = min(want, len(f) - self._read_pos)
                data = bytes(f[self._read_pos : self._read_pos + take])
                self._read_pos += len(data)
                if self._read_pos >= len(f):
                    self._state = protocol.MICROSDEXP_ST_COMPLETE
            else:
                data = b""
        else:
            raise OSError(3, "unknown read cmd 0x%02x" % cmd)
        return data[:want]


class MockRawBus(object):
    """Stand-in for the ``busio.I2C`` object behind a CircuitPython backend.

    qwiic_i2c's CircuitPython driver exposes its ``busio.I2C`` as ``_i2cbus``.
    The library detects ``writeto`` + ``try_lock`` and switches to its
    allocation-free buffers, so the mock provides just that surface plus call
    counters the tests assert on.
    """

    def __init__(self, driver):
        self._driver = driver
        self._locked = False
        self.writes = 0
        self.reads = 0

    def try_lock(self):
        if self._locked:
            return False
        self._locked = True
        return True

    def unlock(self):
        self._locked = False

    def writeto(self, address, buffer, *args, **kwargs):
        self._driver._check(address)
        payload = bytes(buffer)
        if not payload:
            raise OSError(3, "empty write")
        self.writes += 1
        self._driver.microSDexp.handle_write(payload[0], payload[1:])

    def writeto_then_readfrom(self, address, out_buffer, in_buffer, *args, **kwargs):
        self._driver._check(address)
        cmd = bytes(out_buffer)[0]
        n = len(in_buffer)
        data = self._driver.microSDexp.handle_read(cmd, n)
        self.reads += 1
        in_buffer[: len(data)] = data
        if len(data) < n:
            in_buffer[len(data) :] = b"\x00" * (n - len(data))


class MockI2CDriver(object):
    """A ``qwiic_i2c``-shaped driver backed by a :class:`MockMicroSDExp`."""

    def __init__(self, address=0x6E, microSDexp=None, raw=False):
        if microSDexp is None:
            microSDexp = MockMicroSDExp(address, max_block_write=128 if raw else 32)
        self.microSDexp = microSDexp
        self.raw = MockRawBus(self) if raw else None
        # Present only in raw mode; the driver's capability probe looks for it.
        self._i2cbus = self.raw

    # ---- bus plumbing ----
    def _check(self, address):
        if address != self.microSDexp.device_address:
            raise OSError(2, "NACK on address 0x%02X" % address)

    def isDeviceConnected(self, devAddress):
        return devAddress == self.microSDexp.device_address

    def is_device_connected(self, devAddress):
        return self.isDeviceConnected(devAddress)

    def ping(self, devAddress):
        return self.isDeviceConnected(devAddress)

    def scan(self):
        return [self.microSDexp.device_address]

    def writeCommand(self, address, commandCode):
        self._check(address)
        self.microSDexp.handle_write(commandCode, b"")

    def write_command(self, address, commandCode):
        return self.writeCommand(address, commandCode)

    def writeBlock(self, address, commandCode, value):
        self._check(address)
        self.microSDexp.handle_write(commandCode, list(value))

    def write_block(self, address, commandCode, value):
        return self.writeBlock(address, commandCode, value)

    def writeReadBlock(self, address, writeBytes, readNBytes):
        self._check(address)
        if len(writeBytes) != 1:
            raise OSError(3, "one command per transaction")
        return self.microSDexp.handle_read(writeBytes[0], readNBytes)

    def write_read_block(self, address, writeBytes, readNBytes):
        return self.writeReadBlock(address, writeBytes, readNBytes)

    def readBlock(self, address, commandCode, nBytes):
        self._check(address)
        return self.microSDexp.handle_read(commandCode, nBytes)

    def read_block(self, address, commandCode, nBytes):
        return self.readBlock(address, commandCode, nBytes)

    def sleep(self, seconds):
        # Keeps the suite fast without changing driver behaviour.
        time.sleep(0)
