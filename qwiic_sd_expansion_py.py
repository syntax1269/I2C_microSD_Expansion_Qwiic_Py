# SPDX-FileCopyrightText: 2026 I2C microSD Expansion contributors
# SPDX-License-Identifier: MIT
#
#-------------------------------------------------------------------------------
# qwiic_sd_expansion_py.py
#
# Python library for the I2C microSD Expansion module.
#
# This python library supports the SparkFun Qwiic ecosystem
#
# More information on Qwiic is at https://www.sparkfun.com/qwiic
#
# Do you like this library? Help support SparkFun. Buy a board!
#===============================================================================
# Copyright (c) 2026 I2C microSD Expansion contributors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#===============================================================================

"""
qwiic_sd_expansion_py
=====================
Python module for the I2C microSD Expansion module.

SD-card storage over just 2 wires (I2C): full FAT file storage on a micro-SD
card -- create, append, list, and stream files -- without running a FAT stack,
SPI driver, or level shifter on your host. The module owns the card; your code
speaks plain I2C.

The same board exposes three spare expansion pins (PA5, PB2, PB3) for digital
output and one ADC input, plus a module-side bit-bang engine that drives a
WS2812B strip or plays a timed token script with no host involvement at all.

This package can be used with the overall `SparkFun Qwiic Python Package
<https://github.com/sparkfun/Qwiic_Py>`_

New to Qwiic? Take a look at the entire `SparkFun Qwiic ecosystem
<https://www.sparkfun.com/qwiic>`_

Requires module firmware >= 18.7.6 (protocol rev 2) for the file API; the
pin/bit-bang API needs >= 18.5.2, and buffered-frame-only NeoPixel output (a
cleared workspace goes dark) needs >= 18.8.0. ``version()`` reports what the
module is running.
"""

#===============================================================================
# The Qwiic_I2C_Py platform driver is designed to work on almost any Python
# platform, check it out here: https://github.com/sparkfun/Qwiic_I2C_Py
import sys
import time

import qwiic_i2c

# Host-library version (kept in sync with setup.py and the other ports).
__version__ = "1.0.8"

# ---- Non-blocking API types ----------------------------------------------
ASYNC_IOERR = -2   # STATUS read failed
ASYNC_BUSY = -1    # operation not finished yet
ASYNC_OK = 0       # operation completed with no error

OP_OPEN_WRITE = 1
OP_OPEN_READ = 2
OP_CLOSE = 3
OP_FORMAT = 4
OP_QUERY = 5


class AsyncOp:
    """Token returned by a begin_*() call; pass to poll_op()."""
    __slots__ = ("done_before", "kind")

    def __init__(self):
        self.done_before = 0
        self.kind = 0



#===============================================================================
# Device identification
#
# These are set in the class definition as class variables, making them
# available without having to create a class instance. This allows higher level
# logic (qwiic.list_devices(), qwiic.create_device()) to rapidly build an index
# of Qwiic devices at runtime from ``available_addresses``.

_DEFAULT_NAME = "I2C microSD Expansion"

# The module answers at 0x6E out of the box and may be re-addressed to
# 0x6A-0x6F at runtime. NOTE: the first address in this list is the default
# I2C address for the device.
_DEFAULT_ADDRESS = 0x6E
_AVAILABLE_I2C_ADDRESS = [_DEFAULT_ADDRESS, 0x6A, 0x6B, 0x6C, 0x6D, 0x6F]

#===============================================================================
# Wire protocol (byte-for-byte mirror of protocol.h in the Arduino library)

# ---- Legacy command family (0x01-0x0B, 0x0E) ----
MICROSDEXP_CMD_FILENAME = 0x01  # write: filename bytes; STOP stores path
MICROSDEXP_CMD_WRITE_FILE = 0x02  # write: payload + STOP -> create/overwrite, write, close
MICROSDEXP_CMD_READ_FILE = 0x03  # STOP -> open for read, stream via TX buffers
MICROSDEXP_CMD_APPEND_FILE = 0x04  # write: payload + STOP -> append, write, close
MICROSDEXP_CMD_FILE_SIZE = 0x05  # STOP -> size (4 B LE) in STATUS.result
MICROSDEXP_CMD_FILE_EXISTS = 0x06  # STOP -> 1=exists, 0=not found in STATUS.result
MICROSDEXP_CMD_IS_DIRECTORY = 0x07  # STOP -> 1=directory, 0=not in STATUS.result
MICROSDEXP_CMD_LIST_DIR = 0x08  # STOP -> TX stream: 'F'/'D' + NUL name + 4 B size LE, 0xFF term
MICROSDEXP_CMD_MAKE_DIR = 0x09  # STOP -> create directory at Filename
MICROSDEXP_CMD_REMOVE_DIR = 0x0A  # STOP -> remove empty directory
MICROSDEXP_CMD_REMOVE_FILE = 0x0B  # STOP -> delete file at Filename
MICROSDEXP_CMD_CLOCK_SET = 0x0E  # write: 6 B [Y,M,D,h,m,s]; STOP applies
MICROSDEXP_CMD_VERSION = 0x0F  # read: version string; >=18.8.0 answers with a banner

# ---- Pin / extension commands ----
MICROSDEXP_CMD_PA5_SET_MODE = 0x10
MICROSDEXP_CMD_PA5_CONTROL = 0x11
MICROSDEXP_CMD_PB2_SET_MODE = 0x12
MICROSDEXP_CMD_PB2_CONTROL = 0x13
MICROSDEXP_CMD_PB3_SET_MODE = 0x14
MICROSDEXP_CMD_PB3_CONTROL = 0x15
MICROSDEXP_CMD_I2C_SET_ADDR = 0x16
MICROSDEXP_CMD_TEMP_READ = 0x17
MICROSDEXP_CMD_ADC_READ_PA5 = 0x18
MICROSDEXP_CMD_ADC_READ_PB3 = 0x19
MICROSDEXP_CMD_SAVEEEPROM = 0x1A  # STOP -> persist pin modes + I2C addr to EEPROM
MICROSDEXP_CMD_PIN_STATE_READ = 0x1C

# ---- Async protocol (rev 2) ----
MICROSDEXP_CMD_STATUS = 0x20  # read: 12-byte status frame
MICROSDEXP_CMD_OPEN_WRITE = 0x21  # write: filename bytes; STOP enqueues OPEN (truncate)
MICROSDEXP_CMD_WRITE = 0x22  # write: payload block -> RX buffers
MICROSDEXP_CMD_READ = 0x23  # write: request block; read: drain TX buffer
MICROSDEXP_CMD_CLOSE_FLUSH = 0x24  # write: STOP enqueues CLOSE (flush + close)
MICROSDEXP_CMD_OPEN_READ = 0x25  # write: filename bytes; STOP enqueues OPEN (read-only)
MICROSDEXP_CMD_FORMAT = 0x28  # write: 1 B mode (0=auto, 1=force FAT); STOP enqueues format
MICROSDEXP_CMD_CARD_INFO = 0x29  # read: 24-byte card/volume snapshot (LE)
MICROSDEXP_CMD_BITBANG_SET_MODE = 0x2B
MICROSDEXP_CMD_BITBANG_BUFFER = 0x2C
MICROSDEXP_CMD_BITBANG_EXECUTE = 0x2D
MICROSDEXP_CMD_BITBANG_CLEAR = 0x2E
MICROSDEXP_CMD_REBOOT = 0x2F  # write: reboot module

# ---- Module expansion pin IDs (bit-bang and pin control) ----
MICROSDEXP_PIN_PA5 = 5
MICROSDEXP_PIN_PB2 = 2
MICROSDEXP_PIN_PB3 = 3

# ---- Bit-bang engine profiles ----
MICROSDEXP_BITBANG_PROFILE_NEOPIXEL = 0x01
MICROSDEXP_BITBANG_PROFILE_SCRIPT = 0x02

# Frame/script workspace on the module (bytes). The firmware refuses (NACKs)
# data addressed past the end, so the whole workspace is usable but no single
# transaction may cross it: a NeoPixel frame is at most 255 B (85 pixels).
BITBANG_WORKSPACE_SIZE = 256

# ---- CARD_INFO.fat_type (SdFat's FatType) ----
MICROSDEXP_FAT_NONE = 0
MICROSDEXP_FAT12 = 12
MICROSDEXP_FAT16 = 16
MICROSDEXP_FAT32 = 32
MICROSDEXP_FAT_EXFAT = 64

# ---- STATUS.state ----
MICROSDEXP_ST_IDLE = 0
MICROSDEXP_ST_ACCEPTED = 1
MICROSDEXP_ST_BUSY_RX = 2
MICROSDEXP_ST_BUSY_SD = 3
MICROSDEXP_ST_TX_READY = 4
MICROSDEXP_ST_COMPLETE = 5
MICROSDEXP_ST_ERROR = 6
MICROSDEXP_ST_OVERFLOW = 7

# ---- STATUS.error ----
MICROSDEXP_ERR_NONE = 0
MICROSDEXP_ERR_NO_FILE = 1
MICROSDEXP_ERR_OPEN = 2
MICROSDEXP_ERR_CARD = 3
MICROSDEXP_ERR_QUEUE = 4
MICROSDEXP_ERR_INVALID = 5
MICROSDEXP_ERR_OVERFLOW = 6

# listDir stream terminator
LIST_END = 0xFF

#===============================================================================
# Defaults

# Master push size. The qwiic_i2c Linux backend uses SMBus I2C block writes,
# which carry at most 32 payload bytes per transaction (plus the command byte),
# so 32 is the value that is safe on every qwiic_i2c platform. Raise it with
# set_write_chunk_bytes() on a platform whose backend has a larger buffer.
#
# CircuitPython drives the hardware I2C peripheral directly and has no SMBus
# ceiling, so it starts at WRITE_CHUNK_MAX instead (see _auto_write_chunk).
CHUNK_BYTES = 32
# The firmware accepts one 128 B RX block per WRITE transaction.
WRITE_CHUNK_MAX = 128
# Bytes requested per READ drain. The firmware stages up to 256 B across both
# module TX buffers, so 256 empties the stream in one transaction (measured
# 32.3 KiB/s at 1 MHz versus 24.7 for 128 B); a port that caps a single read
# lower is handled by an automatic fallback to 32 B inside read().
READ_CHUNK_BYTES = 256

POLL_MS = 10
FLOW_POLL_MS = 2

OP_TIMEOUT_MS = 15000
COMMIT_TIMEOUT_MS = 30000
# A full FAT rebuild is not an ordinary op: a 7.4 GB card takes ~52 s on the
# device, so format() waits on its own budget instead of OP_TIMEOUT_MS.
FORMAT_TIMEOUT_MS = 300000

# 0x0F answers with a fixed 112 B banner buffer on firmware >= 18.8.0
# ("Clock: ... \nI2C microSD Expansion vX.Y.Z\nCopyright ..."). Older firmware
# returns the bare version string followed by NUL padding.
VERSION_BANNER_BYTES = 112

# STATUS.state values that mean "the submitted op has finished". Reads and
# directory listings hand back a TX stream, so TX_READY counts as completion;
# a rebooted module sits at IDLE/ACCEPTED and must NOT be taken as success.
_OP_DONE_STATES = (
    MICROSDEXP_ST_TX_READY,
    MICROSDEXP_ST_COMPLETE,
    MICROSDEXP_ST_ERROR,
)

# LFN path cap (the module enforces the FAT semantics).
PATH_MAX = 260


def _auto_write_chunk():
    """
    Pick the starting WRITE chunk for this interpreter.

    The module publishes one 128 B RX block per WRITE transaction, so 128 is
    the ceiling. A 32 B chunk costs four transactions per block, and each
    transaction carries a fixed turnaround (~1.3 ms on CircuitPython at 1 MHz,
    about the wire time of a block), which caps the link near 20 KiB/s.
    CircuitPython's ``busio.I2C`` has no SMBus 32 B limit, so start there at
    the full block. Everywhere else stay at the always-safe ``CHUNK_BYTES``;
    ``set_write_chunk_bytes()`` overrides either choice.
    """
    try:
        if "circuitpython" in sys.implementation.name:
            return WRITE_CHUNK_MAX
    except Exception:
        pass
    return CHUNK_BYTES

#===============================================================================
# Small value objects


class MicroSDExpError(object):
    """
    Normalized module errors (mirror of the Arduino ``MicroSDExpError`` enum).

    Python has no need for a C enum here -- class ints keep the same member
    names so ported sketches read identically.
    """

    OK = 0
    NO_MODULE = 1
    NO_FILE = 2
    OPEN_FAIL = 3
    CARD_ERR = 4
    QUEUE_FULL = 5
    INVALID = 6
    OVERFLOW = 7
    TIMEOUT = 8


class _ErrorSlot:
    """Error attribute: last result plus first failure since clear_error().

    Internal library calls may overwrite ``last_error``; a real fault stays
    visible in ``sticky_error`` until the caller explicitly clears it.
    """

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get("_last_error_value", MicroSDExpError.OK)

    def __set__(self, obj, value):
        obj.__dict__["_last_error_value"] = value
        if value != MicroSDExpError.OK:
            obj.__dict__["_sticky_error"] = value


class StatusFrame(object):
    """12-byte STATUS frame: rev, state, opDone, error, rxFree, txAvail, result."""

    __slots__ = ("rev", "state", "op_done", "error", "rx_free", "tx_avail", "result")

    def __init__(self):
        self.rev = 0
        self.state = 0
        self.op_done = 0
        self.error = 0
        self.rx_free = 0
        self.tx_avail = 0
        self.result = 0

    def __repr__(self):
        return (
            "StatusFrame(rev=%d, state=%d, op_done=%d, error=%d, rx_free=%d, "
            "tx_avail=%d, result=%d)"
            % (
                self.rev,
                self.state,
                self.op_done,
                self.error,
                self.rx_free,
                self.tx_avail,
                self.result,
            )
        )


class CardInfo(object):
    """24-byte CARD_INFO frame (all LE)."""

    __slots__ = (
        "mounted",
        "fat_type",
        "card_type",
        "sector_count",
        "free_clusters",
        "err_code",
        "err_data",
        "cluster_count",
        "sck_hz",
    )

    def __init__(self):
        self.mounted = 0
        self.fat_type = 0
        self.card_type = 0
        self.sector_count = 0
        self.free_clusters = 0
        self.err_code = 0
        self.err_data = 0
        self.cluster_count = 0
        self.sck_hz = 0

    def __repr__(self):
        return (
            "CardInfo(mounted=%d, fat=%d, sectors=%d, free_clusters=%d, "
            "sck_hz=%d)"
            % (
                self.mounted,
                self.fat_type,
                self.sector_count,
                self.free_clusters,
                self.sck_hz,
            )
        )


class DirEntry(object):
    """One list_dir() entry."""

    __slots__ = ("is_dir", "name", "size")

    def __init__(self, is_dir=False, name="", size=0):
        self.is_dir = is_dir
        self.name = name
        self.size = size

    def __repr__(self):
        kind = "D" if self.is_dir else "F"
        return "%s %r %d" % (kind, self.name, self.size)


# Expansion pin -> module command byte (the pair is per pin on the wire).
_PIN_IDS = (MICROSDEXP_PIN_PA5, MICROSDEXP_PIN_PB2, MICROSDEXP_PIN_PB3)
_PIN_MODE_CMD = {
    MICROSDEXP_PIN_PA5: MICROSDEXP_CMD_PA5_SET_MODE,
    MICROSDEXP_PIN_PB2: MICROSDEXP_CMD_PB2_SET_MODE,
    MICROSDEXP_PIN_PB3: MICROSDEXP_CMD_PB3_SET_MODE,
}
_PIN_CONTROL_CMD = {
    MICROSDEXP_PIN_PA5: MICROSDEXP_CMD_PA5_CONTROL,
    MICROSDEXP_PIN_PB2: MICROSDEXP_CMD_PB2_CONTROL,
    MICROSDEXP_PIN_PB3: MICROSDEXP_CMD_PB3_CONTROL,
}


def _le16(b, off):
    return b[off] | (b[off + 1] << 8)


def _le32(b, off):
    return b[off] | (b[off + 1] << 8) | (b[off + 2] << 16) | (b[off + 3] << 24)

def _diag_bytes(n):
    """Format a byte count like the ESP32 gateway's cardinfo."""
    return "%.1f MiB / %.2f GiB" % (n / 1048576.0, n / 1073741824.0)



#===============================================================================
class QwiicSDExpansion(object):
    """
    SparkFun I2C microSD Expansion

    Initialise the module at ``address`` with ``i2c_driver``.

    :param address:        The I2C address to use for the device (0x6A-0x6F).
                        If not provided, the default address is used.
    :param i2c_driver:    An existing i2c driver object. If not
                        provided a driver object is created.
    :param scl_hz:        The I2C clock, used for timeout scaling only.
    :param poll_ms:       STATUS poll pause while waiting for an operation.
    :param flow_poll_ms:  rxFree re-check pause while write-blocked.

    :return:            Constructor Initialization
                        True-    Successful
                        False-    Issue loading I2C driver
    :rtype:                Bool
    """

    # last_error is a descriptor so internal calls cannot erase a real fault.
    _last_error = _ErrorSlot()

    # Set default name and I2C address(es)
    device_name = _DEFAULT_NAME
    available_addresses = _AVAILABLE_I2C_ADDRESS
    DEFAULT_ADDRESS = _DEFAULT_ADDRESS

    def __init__(
        self,
        address=None,
        i2c_driver=None,
        scl_hz=400000,
        poll_ms=POLL_MS,
        flow_poll_ms=FLOW_POLL_MS,
    ):
        """
        Constructor
        """

        # Use address if provided, otherwise pick the default
        if address in self.available_addresses:
            self.address = address
        else:
            self.address = self.available_addresses[0]

        # Load the I2C driver if one isn't provided
        if i2c_driver is None:
            self._i2c = qwiic_i2c.getI2CDriver()
            if self._i2c is None:
                print("Unable to load I2C driver for this platform.")
                return
        else:
            self._i2c = i2c_driver

        self._scl_hz = scl_hz if scl_hz and scl_hz > 0 else 400000
        self._poll_ms = poll_ms
        self._flow_poll_ms = flow_poll_ms
        self._write_chunk = _auto_write_chunk()
        self._read_chunk = READ_CHUNK_BYTES
        # CircuitPython's qwiic_i2c backend exposes the underlying busio.I2C
        # object. Its writeBlock()/writeReadBlock() rebuild boxed lists per
        # call (bytes([cmd] + value) and list(buffer)), which costs more than
        # the wire time of a 128 B block; the raw bus takes reusable buffers
        # instead. Detect it once and use it for WRITE pushes and repeated-
        # START reads, falling back to the portable paths everywhere else.
        self._raw_i2c = None
        self._raw_read = None
        self._txbuf = None
        self._txmv = None
        self._rxbuf = None
        self._rxmv = None
        self._cmdbuf = None
        self._cmdmv = None
        raw = getattr(i2c_driver, "_i2cbus", None)
        if (
            raw is not None
            and hasattr(raw, "writeto")
            and hasattr(raw, "try_lock")
            and hasattr(raw, "unlock")
        ):
            self._raw_i2c = raw
            if hasattr(raw, "writeto_then_readfrom"):
                self._raw_read = raw
        self._last_error = MicroSDExpError.OK
        self._file_open = False
        self._async_pending = False
        self._append_mode = False
        self._read_started = False
        self._base_written = 0
        self._written = 0
        self._last_active = time.monotonic()
        self._append_path = ""
        # Last mode applied per expansion pin (None = "none yet"), so a
        # redundant set_pin_mode(pin, same) is a library-side no-op: no bus
        # transaction, no module EEPROM write.
        self._pin_last_mode = {pid: None for pid in _PIN_IDS}

    def __repr__(self):
        return "<QwiicSDExpansion address=0x%02X>" % self.address

    #---------------------------------------------------------------------------
    # Qwiic discovery API

    def is_connected(self):
        """
        Determines if this device is connected

        :return: `True` if connected, otherwise `False`
        :rtype: bool
        """
        if self._i2c is None:
            return False
        try:
            return bool(self._i2c.isDeviceConnected(self.address))
        except Exception:
            return False

    connected = property(is_connected)

    def begin(self):
        """
        Initializes this device with default parameters

        Probes the module by reading its STATUS frame. If the bound address
        does not answer, the runtime re-address range (0x6A-0x6F) is scanned
        once, so a module that was re-addressed in a previous session is still
        found.

        :return: Returns `True` if successful, otherwise `False`
        :rtype: bool
        """
        if self.read_status() is not None:
            self._last_error = MicroSDExpError.OK
            return True

        saved = self.address
        for addr in self.available_addresses:
            if addr == saved:
                continue
            self.address = addr
            if self.read_status() is not None:
                self._last_error = MicroSDExpError.OK
                return True

        self.address = saved
        self._last_error = MicroSDExpError.NO_MODULE
        return False

    def set_address(self, address):
        """
        Point this object at a different module address (no bus traffic).

        :param address: The 7-bit I2C address the module answers at
        :type address: int
        :return: `True` if the address is in the module's supported range
        :rtype: bool
        """
        if address not in self.available_addresses:
            self._last_error = MicroSDExpError.INVALID
            return False
        self.address = address
        return True

    def change_address(self, address):
        """
        Re-address the module itself (CMD_I2C_SET_ADDR, 0x16).

        The module applies the new address from STOP. The valid range is
        0x6A-0x6F; persist it with save_pin_mode() if it must survive a reset.

        :param address: The new 7-bit I2C address (0x6A-0x6F)
        :type address: int
        :return: `True` if the command was acknowledged
        :rtype: bool
        """
        if address not in self.available_addresses:
            self._last_error = MicroSDExpError.INVALID
            return False
        if not self._write(bytes([MICROSDEXP_CMD_I2C_SET_ADDR, address & 0xFF])):
            return False
        self.address = address
        self._last_error = MicroSDExpError.OK
        return True

    #---------------------------------------------------------------------------
    # Configuration

    def set_poll_interval(self, ms):
        """
        Set the STATUS poll pause used while waiting for an operation
        (default 10 ms).

        :param ms: Poll pause in milliseconds
        :type ms: int
        """
        self._poll_ms = ms

    def set_flow_poll_ms(self, ms):
        """
        Set the pause after a WRITE NACK, before the retry (default 2 ms).

        A NACK from CMD_WRITE means both module RX blocks are still busy
        draining to the card. Lower it when the card drains a block faster
        than 2 ms; raise it on a slow bus to spend less time retrying.

        :param ms: Retry pause in milliseconds
        :type ms: int
        """
        if ms < 0:
            ms = 0
        self._flow_poll_ms = ms

    def flow_poll_ms(self):
        """
        :return: The configured WRITE-NACK retry pause in milliseconds
        :rtype: int
        """
        return self._flow_poll_ms

    def set_read_chunk_bytes(self, n):
        """
        Bytes requested per READ drain, clamped to 1..256.

        Defaults to 256, the total the firmware stages across both TX buffers.
        Lower it for a bus/port that cannot carry the full chunk in one
        transaction; read() also falls back to 32 B on its own if a drain
        raises.

        :param n: Bytes per READ transaction
        :type n: int
        """
        if n < 1:
            n = 1
        if n > 256:
            n = 256
        self._read_chunk = n

    def read_chunk_bytes(self):
        """
        :return: The configured per-drain READ chunk size
        :rtype: int
        """
        return self._read_chunk

    def set_write_chunk_bytes(self, n):
        """
        Payload bytes pushed per WRITE transaction, clamped to 1..128.

        Defaults to 32 on a generic (SMBus) backend, which is the I2C-block
        ceiling of the qwiic_i2c Linux backend, and to 128 on CircuitPython,
        whose busio.I2C carries a full module RX block. Raise or lower it for a
        platform whose backend differs.

        :param n: Payload bytes per WRITE transaction
        :type n: int
        """
        if n < 1:
            n = 1
        if n > WRITE_CHUNK_MAX:
            n = WRITE_CHUNK_MAX
        self._write_chunk = n

    def write_chunk_bytes(self):
        """
        :return: The configured per-transaction WRITE chunk size
        :rtype: int
        """
        return self._write_chunk

    def scale_timeout(self, base_ms):
        """
        ``base * 100000 / scl_hz``, never below ``base``, >= 2x below 50 kHz,
        capped at 120 s.

        :param base_ms: Unscaled timeout in milliseconds
        :type base_ms: int
        :return: The scaled timeout in milliseconds
        :rtype: int
        """
        if self._scl_hz == 0:
            return base_ms
        scaled = base_ms * 100000 // self._scl_hz
        if scaled < base_ms:
            scaled = base_ms
        if self._scl_hz < 50000:
            dbl = base_ms * 2
            if scaled < dbl:
                scaled = dbl
        if scaled > 120000:
            scaled = 120000
        return scaled

    @property
    def last_error(self):
        """
        :return: The normalized error code of the last operation
        :rtype: int
        """
        return self._last_error

    @property
    def last_ok(self):
        """True when the most recent call completed without error."""
        return self._last_error == MicroSDExpError.OK

    @property
    def sticky_error(self):
        """First error since clear_error(); OK if no failure was recorded."""
        return self.__dict__.get("_sticky_error", MicroSDExpError.OK)

    def clear_error(self):
        """Reset both last_error and sticky_error to OK."""
        self._last_error = MicroSDExpError.OK
        self.__dict__["_sticky_error"] = MicroSDExpError.OK

    @property
    def file_open(self):
        """
        :return: `True` while a file is open on the module
        :rtype: bool
        """
        return self._file_open

    #---------------------------------------------------------------------------
    # Transport
    #
    # qwiic_i2c gives us a register-style bus: writeCommand()/writeBlock() send
    # a command byte plus data with a STOP, writeReadBlock() sends the command
    # and reads back with a repeated START. The module protocol is exactly one
    # command per transaction, so the payload simply rides in the data field.

    def _write(self, payload):
        """
        Send `payload` (command byte first) with a STOP. Returns True on ACK.
        """
        self._last_active = time.monotonic()
        cmd = payload[0]
        data = [b & 0xFF for b in payload[1:]]
        try:
            if data:
                self._i2c.writeBlock(self.address, cmd, data)
            else:
                self._i2c.writeCommand(self.address, cmd)
        except Exception:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        return True

    def _write_block_from(self, cmd, data, start, n):
        """
        Send `cmd` plus ``data[start:start + n]`` with a STOP.

        This is the allocation-free form of ``_write`` for streamed payloads:
        the command byte and the payload are copied into one reusable buffer
        and handed straight to ``busio.I2C.writeto``. On CircuitPython the
        portable ``writeBlock`` path rebuilds a boxed 130-element list for
        every 128 B block, which measured ~1 ms per push -- more than the
        block's wire time -- and capped 1 MHz writes near 33 KiB/s. Returns
        True on ACK.

        :param cmd: The command byte
        :type cmd: int
        :param data: The source buffer (bytes/bytearray/memoryview)
        :param start: Offset of the first payload byte
        :type start: int
        :param n: Number of payload bytes
        :type n: int
        :return: `True` when the module ACKed the transaction
        :rtype: bool
        """
        self._last_active = time.monotonic()
        buf = self._txbuf
        if buf is None or len(buf) < n + 1:
            buf = bytearray(n + 1)
            self._txbuf = buf
            self._txmv = memoryview(buf)
        buf[0] = cmd
        if n:
            buf[1 : n + 1] = memoryview(data)[start : start + n]
        raw = self._raw_i2c
        try:
            while not raw.try_lock():
                pass
            raw.writeto(self.address, self._txmv[: n + 1])
        except Exception:
            self._last_error = MicroSDExpError.NO_MODULE
            try:
                raw.unlock()
            except Exception:
                pass
            return False
        raw.unlock()
        return True

    def _read(self, cmd, n):
        """
        Repeated-START read of n bytes after `cmd`. Returns bytes, or None when
        the bus did not answer.
        """
        if n > 0 and self._raw_read is not None:
            return self._read_raw(cmd, n)
        self._last_active = time.monotonic()
        try:
            raw = self._i2c.writeReadBlock(self.address, [cmd], n)
        except Exception:
            self._last_error = MicroSDExpError.NO_MODULE
            return None
        if raw is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return None
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        try:
            return bytes(bytearray(raw))
        except Exception:
            self._last_error = MicroSDExpError.CARD_ERR
            return None

    def _read_raw(self, cmd, n):
        """
        Repeated-START read of n bytes using the raw ``busio.I2C`` object.

        The portable ``writeReadBlock`` path builds two boxed lists per call
        (the one-byte command and the returned buffer), which is significant
        here because a streaming read issues a STATUS query before every
        drain -- 4-5 list rebuilds per 256 B block on a 1 MHz I²C host.
        This variant reuses a one-byte command buffer and a growable RX
        buffer, so the only allocation is the ``bytes`` copy returned to the
        caller.

        :param cmd: The command byte
        :type cmd: int
        :param n: Number of bytes to read
        :type n: int
        :return: The bytes read, or None when the bus did not answer
        :rtype: bytes
        """
        self._last_active = time.monotonic()
        cmdbuf = self._cmdbuf
        if cmdbuf is None:
            cmdbuf = bytearray(1)
            self._cmdbuf = cmdbuf
            self._cmdmv = memoryview(cmdbuf)
        cmdbuf[0] = cmd
        rxbuf = self._rxbuf
        if rxbuf is None or len(rxbuf) < n:
            rxbuf = bytearray(n)
            self._rxbuf = rxbuf
            self._rxmv = memoryview(rxbuf)
        raw = self._raw_read
        try:
            while not raw.try_lock():
                pass
            raw.writeto_then_readfrom(
                self.address, self._cmdmv, self._rxmv[:n]
            )
        except Exception:
            self._last_error = MicroSDExpError.NO_MODULE
            try:
                raw.unlock()
            except Exception:
                pass
            return None
        raw.unlock()
        return bytes(self._rxmv[:n])

    def read_status(self, st=None):
        """
        Read the 12-byte STATUS frame.

        :param st: An existing StatusFrame to fill in, or None
        :type st: StatusFrame
        :return: The status frame, or None when the module did not answer
        :rtype: StatusFrame
        """
        if st is None:
            st = StatusFrame()
        b = self._read(MICROSDEXP_CMD_STATUS, 12)
        if b is None or len(b) < 12:
            return None
        st.rev = b[0]
        st.state = b[1]
        st.op_done = b[2]
        st.error = b[3]
        st.rx_free = _le16(b, 4)
        st.tx_avail = _le16(b, 6)
        st.result = _le32(b, 8)
        return st

    def _wait_for_op(self, done_before, limit_s):
        """
        Poll STATUS until the submitted op has genuinely finished.

        ``opDone`` is an 8-bit sequence number that also resets to 0 when the
        module reboots, so a *change* is not proof of completion: a module that
        reset mid-op would look "done" (and format() would report success on an
        untouched card). Require a completion state as well.

        :param done_before: The opDone value captured before submitting
        :type done_before: int
        :param limit_s: Timeout in seconds
        :type limit_s: float
        :return: ``status.error`` (0 = COMPLETE), or -1 on timeout
        :rtype: int
        """
        t0 = time.monotonic()
        while (time.monotonic() - t0) < limit_s:
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.op_done != done_before and st.state in _OP_DONE_STATES:
                self._last_error = MicroSDExpError.OK
                return st.error
            time.sleep(self._poll_ms / 1000.0)
        self._last_error = MicroSDExpError.TIMEOUT
        return -1

    def wait_for_op_complete(self, done_before, timeout_ms=OP_TIMEOUT_MS):
        """
        Poll STATUS until the submitted op has completed or failed.

        :param done_before: The opDone value captured before submitting
        :type done_before: int
        :param timeout_ms: Unscaled timeout in milliseconds
        :type timeout_ms: int
        :return: ``status.error`` (0 = COMPLETE), or -1 on timeout
        :rtype: int
        """
        return self._wait_for_op(done_before, self.scale_timeout(timeout_ms) / 1000.0)

    def wait_for_committed(self, target, timeout_ms=COMMIT_TIMEOUT_MS):
        """
        Poll STATUS until ``result >= target`` (bytes committed to the card).

        :param target: Total committed byte count to reach
        :type target: int
        :param timeout_ms: Unscaled timeout in milliseconds
        :type timeout_ms: int
        :return: `True` when the target was reached
        :rtype: bool
        """
        limit = self.scale_timeout(timeout_ms) / 1000.0
        t0 = time.monotonic()
        while (time.monotonic() - t0) < limit:
            st = self.read_status()
            if st is not None:
                if st.state == MICROSDEXP_ST_ERROR:
                    self._last_error = MicroSDExpError.CARD_ERR
                    return False
                if st.result >= target:
                    return True
            time.sleep(self._poll_ms / 1000.0)
        self._last_error = MicroSDExpError.TIMEOUT
        return False

    #---------------------------------------------------------------------------
    # Barriers

    def _barrier_close_flush(self):
        st = self.read_status()
        db = st.op_done if st is not None else 0
        if not self._write(bytes([MICROSDEXP_CMD_CLOSE_FLUSH])):
            return False
        return self.wait_for_op_complete(db) == 0

    def _barrier_if_gap(self):
        if (time.monotonic() - self._last_active) > 4.0:
            self._barrier_close_flush()

    #---------------------------------------------------------------------------
    # Paths

    def valid_path(self, path):
        """
        Length-gate a path (the module handles the FAT path semantics).

        Invalid: None/empty/overlong -- no I2C is sent.

        :param path: The path to check
        :type path: str
        :return: `True` if the path can be submitted
        :rtype: bool
        """
        if not path or len(path) == 0 or len(path) >= PATH_MAX:
            self._last_error = MicroSDExpError.INVALID
            return False
        return True

    def _submit_filename(self, path):
        if not self.valid_path(path):
            return False
        try:
            data = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        if len(data) > PATH_MAX:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([MICROSDEXP_CMD_FILENAME]) + data)

    def _legacy_op(self, cmd, path, want_result=False):
        """
        doneBefore -> FILENAME -> cmd -> wait -> STATUS.result latch.
        """
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(path):
            return (100, 0)
        if not self._write(bytes([cmd])):
            return (101, 0)
        err = self.wait_for_op_complete(done_before)
        if err < 0:
            self._last_error = MicroSDExpError.TIMEOUT
            return (err, 0)
        result = 0
        if want_result:
            st2 = self.read_status()
            result = st2.result if st2 is not None else 0
        if err != 0:
            self._last_error = (
                MicroSDExpError.OPEN_FAIL if err == MICROSDEXP_ERR_OPEN else MicroSDExpError.CARD_ERR
            )
        else:
            self._last_error = MicroSDExpError.OK
        return (err, result)

    #---------------------------------------------------------------------------
    # Directory and query operations

    def mkdir(self, path):
        """
        Create a directory.

        :param path: Directory path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        if not self.valid_path(path):
            return False
        return self._legacy_op(MICROSDEXP_CMD_MAKE_DIR, path)[0] == 0

    def rmdir(self, path):
        """
        Remove an empty directory.

        :param path: Directory path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        if not self.valid_path(path):
            return False
        return self._legacy_op(MICROSDEXP_CMD_REMOVE_DIR, path)[0] == 0

    def remove(self, path):
        """
        Delete a file.

        :param path: File path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        if not self.valid_path(path):
            return False
        return self._legacy_op(MICROSDEXP_CMD_REMOVE_FILE, path)[0] == 0

    def exists_checked(self, path):
        """Return (ok, exists). ``ok`` is False on I2C/card/path error."""
        if not self.valid_path(path):
            return (False, False)
        err, res = self._legacy_op(MICROSDEXP_CMD_FILE_EXISTS, path, want_result=True)
        return (err == 0, err == 0 and res == 1)

    def exists(self, path):
        """True if the path exists. On error returns False — check last_ok."""
        return self.exists_checked(path)[1]

    def file_size_checked(self, path):
        """Return (ok, size_bytes). ``ok`` distinguishes 0 bytes from an error."""
        if not self.valid_path(path):
            return (False, 0)
        err, res = self._legacy_op(MICROSDEXP_CMD_FILE_SIZE, path, want_result=True)
        return (err == 0, res if err == 0 else 0)

    def file_size(self, path):
        """Size in bytes, 0 if not found or on error — check last_ok."""
        return self.file_size_checked(path)[1]

    def is_directory_checked(self, path):
        """Return (ok, is_directory). ``ok`` is False on error."""
        if not self.valid_path(path):
            return (False, False)
        err, res = self._legacy_op(MICROSDEXP_CMD_IS_DIRECTORY, path, want_result=True)
        return (err == 0, err == 0 and res == 1)

    def is_directory(self, path):
        """True if the path is a directory — check last_ok on error."""
        return self.is_directory_checked(path)[1]

    def firmware_banner(self):
        """
        Read the firmware's full identification banner.

        Firmware >= 18.8.0 answers CMD_VERSION with a multi-line banner::

            Clock: 20000000 Hz (fuse OSCCFG=0x7E)
            I2C microSD Expansion v18.8.22
            Copyright (C) 2026 syntax1269@gmail.com

        Older firmware answers with the bare version string ("18.7.6").

        :return: The banner text (newline separated), or "" on error
        :rtype: str
        """
        buf = self._read(MICROSDEXP_CMD_VERSION, VERSION_BANNER_BYTES)
        if not buf:
            return ""
        end = 0
        while end < len(buf) and buf[end] != 0:
            end += 1
        self._last_error = MicroSDExpError.OK
        return bytes(buf[:end]).decode("ascii", "replace").strip()

    def version(self):
        """
        Read the module firmware version.

        Handles both answer shapes: the bare string used up to v18.7.x and the
        multi-line banner used from v18.8.0 (where the first line is the
        measured clock, not the version).

        :return: The version string (e.g. "18.8.22"), or "" on error
        :rtype: str
        """
        text = self.firmware_banner()
        if not text:
            return ""
        for raw in text.split():
            token = raw.strip("(),;")
            if token[:1] in ("v", "V"):
                token = token[1:]
            parts = token.split(".")
            if len(parts) >= 2 and all(part.isdigit() for part in parts):
                return token
        # No dotted token: banner truncated by the buffer or malformed.
        self._last_error = MicroSDExpError.INVALID
        return ""

    def firmware_clock_hz(self):
        """
        Read the clock the module measured at power-up (firmware >= 18.8.0).

        :return: The clock in Hz, or 0 when the banner does not report one
        :rtype: int
        """
        text = self.firmware_banner()
        for line in text.splitlines():
            line = line.strip()
            if line.lower().startswith("clock:"):
                parts = line.replace(":", " ").replace("(", " ").split()
                for part in parts:
                    if part.isdigit():
                        return int(part)
        return 0

    def temperature_k(self):
        """
        Read the module die temperature in whole kelvin (2-byte LE integer).

        :return: Die temperature in whole kelvin (e.g. 294 ≈ 21 °C), or
                 0xFFFF on error
        :rtype: int
        """
        buf = self._read(MICROSDEXP_CMD_TEMP_READ, 2)
        if buf is None or len(buf) < 2:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        self._last_error = MicroSDExpError.OK
        return _le16(buf, 0)

    def adc_pa5(self):
        """
        Read the PA5 ADC channel (12-bit, VREF 1.024 V).

        :return: The raw ADC word, or 0xFFFF on error / unavailable channel
        :rtype: int
        """
        buf = self._read(MICROSDEXP_CMD_ADC_READ_PA5, 3)
        if buf is None or len(buf) < 2:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        if buf[0] == 0xFF and buf[1] == 0xFF:
            self._last_error = MicroSDExpError.INVALID
            return 0xFFFF
        self._last_error = MicroSDExpError.OK
        return _le16(buf, 0)

    def card_info(self):
        """
        Read the card/volume snapshot.

        :return: A CardInfo object, or None on error
        :rtype: CardInfo
        """
        buf = self._read(MICROSDEXP_CMD_CARD_INFO, 24)
        if buf is None or len(buf) < 24:
            self._last_error = MicroSDExpError.INVALID
            return None
        out = CardInfo()
        out.mounted = buf[0]
        out.fat_type = buf[1]
        out.card_type = buf[2]
        out.sector_count = _le32(buf, 4)
        out.free_clusters = _le32(buf, 8)
        out.err_code = _le16(buf, 12)
        out.err_data = _le16(buf, 14)
        out.cluster_count = _le32(buf, 16)
        out.sck_hz = _le32(buf, 20)
        self._last_error = MicroSDExpError.OK
        return out

    def diagnostics(self):
        """
        Return a one-page health report for troubleshooting.

        Reports module presence, firmware and protocol version, card/filesystem
        state, capacity and free space, the bound I2C address and a communication
        verdict. Safe to call before ``begin()``: fields that could not be read
        are shown as ``n/a``. The call does not change ``last_error``.

        Free space uses the module's ``free_clusters`` value; a reported 0 means
        unknown (scan pending) or a full card, so the report says ``unknown``.
        The Qwiic bus speed is owned by the host driver, so it is shown as
        ``n/a (host bus)``.
        """
        preserved = self.last_error
        lines = ["I2C microSD Expansion", "---------------------"]
        st = self.read_status()
        lines.append("Module detected:   %s" % ("yes" if st is not None else "no"))
        lines.append("Protocol version:  %s" % (str(st.rev) if st is not None else "n/a"))

        fw = self.version()
        lines.append("Firmware version:  %s" % (fw if fw else "unknown"))

        ci = self.card_info()
        lines.append("SD card detected:  %s" % ("yes" if ci is not None and ci.mounted else "no"))
        if ci is not None:
            fat_names = {12: "FAT12", 16: "FAT16", 32: "FAT32", 64: "exFAT"}
            lines.append("Filesystem:        %s" % fat_names.get(ci.fat_type, "unknown"))
            capacity = ci.sector_count * 512
            lines.append("Capacity:          %s" % (
                _diag_bytes(capacity) if capacity else "n/a"))
            if ci.cluster_count > 0 and ci.free_clusters > 0:
                cluster = ((capacity // ci.cluster_count + 256) // 512) * 512
                lines.append("Free space:        %s" % _diag_bytes(ci.free_clusters * cluster))
            elif ci.free_clusters == 0:
                lines.append("Free space:        unknown")
            else:
                lines.append("Free space:        n/a")
        else:
            lines.extend(["Filesystem:        n/a",
                          "Capacity:          n/a",
                          "Free space:        n/a"])

        lines.append("I2C address:       0x%02X" % self.address)
        lines.append("I2C speed:         n/a (host bus)")
        lines.append("Communication:     %s" % (
            "OK" if st is not None and st.error == 0 else "CHECK"))

        self._last_error = preserved
        return "\n".join(lines)

    # ---- Non-blocking API (no sleeps; call from your loop) -----------------
    def _async_submit_open(self, cmd, path, op, kind):
        if self._async_pending or not self.valid_path(path):
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        try:
            raw = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        if not self._write(bytes([cmd]) + raw):
            return False
        op.done_before = st.op_done
        op.kind = kind
        self._async_pending = True
        self._append_mode = False
        self._read_started = False
        self._written = 0
        self._file_open = kind in (OP_OPEN_WRITE, OP_OPEN_READ)
        self._last_error = MicroSDExpError.OK
        return True

    def begin_open_write(self, path, op):
        """Submit OPEN_WRITE without waiting; poll with poll_op()."""
        return self._async_submit_open(MICROSDEXP_CMD_OPEN_WRITE, path, op, OP_OPEN_WRITE)

    def begin_open_read(self, path, op):
        """Submit OPEN_READ without waiting; poll with poll_op()."""
        return self._async_submit_open(MICROSDEXP_CMD_OPEN_READ, path, op, OP_OPEN_READ)

    def begin_close(self, op):
        """Submit CLOSE_FLUSH without waiting; poll with poll_op()."""
        if self._async_pending or not self._file_open:
            return False
        if self._append_mode:  # append chunks are atomic; no module op
            self._file_open = False
            self._append_mode = False
            self._read_started = False
            self._last_error = MicroSDExpError.OK
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if not self._write(bytes([MICROSDEXP_CMD_CLOSE_FLUSH])):
            return False
        op.done_before = st.op_done
        op.kind = OP_CLOSE
        self._async_pending = True
        return True

    def begin_format(self, mode, op):
        """Submit FORMAT without waiting (destructive)."""
        if mode not in (0, 1) or self._async_pending:
            self._last_error = MicroSDExpError.INVALID
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if not self._write(bytes([MICROSDEXP_CMD_FORMAT, mode])):
            return False
        op.done_before = st.op_done
        op.kind = OP_FORMAT
        self._async_pending = True
        return True

    def begin_query(self, cmd, path, op):
        """Submit a queued command (optionally with a path) without waiting."""
        if self._async_pending:
            return False
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return False
        if path and not self._submit_filename(path):
            return False
        if not self._write(bytes([cmd])):
            return False
        op.done_before = st.op_done
        op.kind = OP_QUERY
        self._async_pending = True
        return True

    def poll_op(self, op):
        """One STATUS read: ASYNC_BUSY, ASYNC_OK, module error, or ASYNC_IOERR."""
        st = self.read_status()
        if st is None:
            return ASYNC_IOERR
        if st.op_done == op.done_before:
            return ASYNC_BUSY
        if not self._async_pending:
            return st.error
        self._async_pending = False
        if op.kind == OP_OPEN_WRITE:
            self._base_written = st.result
        elif op.kind == OP_OPEN_READ:
            self._base_written = st.result
            self._write(bytes([MICROSDEXP_CMD_READ]))  # prime the stream
            self._read_started = True
        elif op.kind == OP_CLOSE:
            self._file_open = False
            self._read_started = False
        if st.error == 0:
            self._last_error = MicroSDExpError.OK
        else:
            self._last_error = (MicroSDExpError.OPEN_FAIL
                                if st.error == MICROSDEXP_ERR_OPEN
                                else MicroSDExpError.CARD_ERR)
        return st.error

    def write_now(self, data):
        """Push at most one chunk if RX has room now. Returns bytes accepted."""
        if not data or not self._file_open or self._async_pending:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return 0
        if self._append_mode:
            self._last_error = MicroSDExpError.INVALID
            return 0
        chunk = bytes(data[:CHUNK_BYTES])
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return 0
        if st.state == MICROSDEXP_ST_ERROR:
            self._last_error = MicroSDExpError.CARD_ERR
            return 0
        if st.rx_free < len(chunk):
            return 0  # would block
        if not self._write(bytes([MICROSDEXP_CMD_WRITE]) + chunk):
            return 0
        self._written += len(chunk)
        self._last_error = MicroSDExpError.OK
        return len(chunk)

    def read_now(self, n):
        """Drain only what is staged right now. Returns bytes (b"" = try later)."""
        if n <= 0 or not self._file_open or not self._read_started or self._async_pending:
            return b""
        st = self.read_status()
        if st is None:
            self._last_error = MicroSDExpError.NO_MODULE
            return b""
        if st.state == MICROSDEXP_ST_ERROR:
            self._last_error = MicroSDExpError.CARD_ERR
            return b""
        if st.tx_avail == 0:
            return b""
        want = min(st.tx_avail, n, self._read_chunk)
        chunk = self._read(MICROSDEXP_CMD_READ, want)
        if chunk is None:
            self._last_error = MicroSDExpError.CARD_ERR
            got_bytes = b""
        else:
            got_bytes = bytes(chunk[:want])
        self._last_error = MicroSDExpError.OK
        return got_bytes

    def committed_bytes(self):
        """Committed byte count from one STATUS read (0 on I/O error)."""
        st = self.read_status()
        return st.result if st is not None else 0

    def list_dir(self, path, max_entries=64):
        """
        Enumerate a directory via the LIST_DIR TX stream.

        Stream: 'F'/'D' + NUL basename + 4 B size LE; 0xFF terminates.

        :param path: Directory path on the card
        :type path: str
        :param max_entries: Maximum number of entries to collect
        :type max_entries: int
        :return: A list of DirEntry objects
        :rtype: list
        """
        if not self.valid_path(path) or max_entries == 0:
            return []
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(path):
            return []
        if not self._write(bytes([MICROSDEXP_CMD_LIST_DIR])):
            return []
        if self.wait_for_op_complete(done_before) != 0:
            self._barrier_close_flush()
            return []
        stchk = self.read_status()
        if stchk is not None and stchk.state == MICROSDEXP_ST_ERROR:
            self._barrier_close_flush()
            return []

        entries = []
        p_type, p_name, p_size = 0, 1, 2
        pstate = p_type
        is_dir = False
        sz_acc = 0
        sz_idx = 0
        name = bytearray()
        finished = False
        t0 = time.monotonic()
        limit = self.scale_timeout(COMMIT_TIMEOUT_MS) / 1000.0

        while not finished:
            if (time.monotonic() - t0) >= limit:
                self._last_error = MicroSDExpError.TIMEOUT
                break
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.state == MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                entries = []
                break
            if st.tx_avail > 0:
                want = min(st.tx_avail, self._read_chunk)
                chunk = self._read(MICROSDEXP_CMD_READ, want)
                if chunk is None:
                    if want > 32:
                        self._read_chunk = 32
                        continue
                    self._last_error = MicroSDExpError.CARD_ERR
                    entries = []
                    break
                for i in range(len(chunk)):
                    if finished:
                        break
                    b = chunk[i]
                    if pstate == p_type:
                        if b == LIST_END:
                            finished = True
                        elif b == 0x46 or b == 0x44:  # 'F'/'D'
                            is_dir = b == 0x44
                            name = bytearray()
                            sz_acc = 0
                            sz_idx = 0
                            pstate = p_name
                        else:
                            finished = True  # corrupt stream
                    elif pstate == p_name:
                        if b == 0x00:
                            pstate = p_size
                        else:
                            if len(name) < 63:
                                name.append(b)
                    else:  # p_size
                        sz_acc |= b << (8 * sz_idx)
                        sz_idx += 1
                        if sz_idx >= 4:
                            if len(entries) < max_entries:
                                entries.append(
                                    DirEntry(
                                        is_dir=is_dir,
                                        name=bytes(name).decode("ascii", "replace"),
                                        size=0 if is_dir else sz_acc,
                                    )
                                )
                            pstate = p_type
                continue
            if st.state == MICROSDEXP_ST_COMPLETE:
                break
            time.sleep(self._poll_ms / 1000.0)

        preserved = self._last_error
        self._barrier_close_flush()
        # Preserve a drain error across the barrier (the barrier resets it).
        if self._last_error == MicroSDExpError.OK and preserved != MicroSDExpError.OK:
            self._last_error = preserved
        return entries

    #---------------------------------------------------------------------------
    # Async file core

    def open_append(self, path):
        """
        Open a file for append.

        There is no module OPEN for append: each write() is one atomic APPEND
        transaction (FILENAME + APPEND_FILE + payload).

        :param path: File path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        if not self.valid_path(path):
            return False
        self._append_path = path
        self._append_mode = True
        self._file_open = True
        self._read_started = False
        self._written = 0
        self._last_error = MicroSDExpError.OK
        self._last_active = time.monotonic()
        return True

    def _append_chunk(self, data):
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._submit_filename(self._append_path):
            return False
        if not self._write(bytes([MICROSDEXP_CMD_APPEND_FILE]) + bytes(data)):
            return False
        err = self.wait_for_op_complete(done_before)
        if err != 0:
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return True

    def _open_via_cmd(self, cmd, path):
        if not self.valid_path(path):
            return False
        self._append_mode = False
        try:
            raw = path.encode("ascii") + b"\x00"
        except (UnicodeEncodeError, AttributeError):
            self._last_error = MicroSDExpError.INVALID
            return False
        for _attempt in range(6):
            self._barrier_close_flush()
            st = self.read_status()
            done_before = st.op_done if st is not None else 0
            if not self._write(bytes([cmd]) + raw):
                time.sleep(0.2)
                continue
            err = self.wait_for_op_complete(done_before)
            if err == 0:
                st2 = self.read_status()
                self._base_written = st2.result if st2 is not None else 0
                self._file_open = True
                self._read_started = False
                self._written = 0
                self._last_error = MicroSDExpError.OK
                return True
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.OPEN_FAIL
            time.sleep(0.2)
        self._file_open = False
        return False

    def open_write(self, path):
        """
        Create/truncate and open a file for writing.

        :param path: File path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        return self._open_via_cmd(MICROSDEXP_CMD_OPEN_WRITE, path)

    def open_read(self, path):
        """
        Open a file for reading and prime the TX stream.

        :param path: File path on the card
        :type path: str
        :return: `True` on success
        :rtype: bool
        """
        if not self._open_via_cmd(MICROSDEXP_CMD_OPEN_READ, path):
            return False
        # Prime the read stream (the C++ openRead does this STOP).
        if not self._write(bytes([MICROSDEXP_CMD_READ])):
            self._last_error = MicroSDExpError.NO_FILE
        self._read_started = True
        st = self.read_status()
        if st is not None:
            self._base_written = st.result
        self._last_error = MicroSDExpError.OK
        return True

    def write(self, data):
        """
        Write bytes to the open file, ACK-paced by the module's RX-block flow
        control.

        :param data: The bytes to write
        :type data: bytes, bytearray or list of ints
        :return: The number of bytes accepted
        :rtype: int
        """
        if not data or not self._file_open:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return 0
        if self._append_mode:
            off = 0
            buf = bytes(bytearray(data))
            while off < len(buf):
                chunk = buf[off : off + self._write_chunk]
                if not self._append_chunk(chunk):
                    self._written += off
                    return off
                off += len(chunk)
            self._written += off
            self._last_error = MicroSDExpError.OK
            return off

        buf = bytes(bytearray(data))
        off = 0
        while off < len(buf):
            n = self._push_write_block(buf, off, len(buf) - off)
            if n <= 0:
                self._written += off
                return off
            off += n
        self._written += off
        self._last_error = MicroSDExpError.OK
        return off

    def _push_write_block(self, data, off, count):
        """
        Push up to ``count`` bytes from ``data[off:]`` into module RX blocks.

        Pacing is ACK-driven. Each firmware WRITE transaction occupies one
        128 B RX block and a STOP publishes it, so a fresh transaction always
        starts with a clean block; taking a NACK means both blocks are still
        busy draining to the card (the NACK lands on the first data byte, so
        the failed attempt is cheap). Polling STATUS before every push instead
        costs a full turnaround -- ~1.3 ms at 1 MHz on CircuitPython, about
        the wire time of a block -- which throttled writes by roughly a third.

        A NACK is also how the firmware reports a card error or a closed file,
        so STATUS is read whenever a push fails and its state decides whether
        to wait or to abort.

        :return: Bytes accepted (0 on error, with ``last_error`` set)
        :rtype: int
        """
        max_fails = 1200 if 0 < self._scl_hz < 50000 else 400
        sent = 0
        fails = 0
        raw = self._raw_i2c
        while sent < count:
            n = count - sent
            if n > self._write_chunk:
                n = self._write_chunk
            if raw is not None:
                ok = self._write_block_from(
                    MICROSDEXP_CMD_WRITE, data, off + sent, n
                )
            else:
                ok = self._write(
                    bytes([MICROSDEXP_CMD_WRITE])
                    + bytes(data[off + sent : off + sent + n])
                )
            if ok:
                sent += n
                fails = 0
                continue
            fails += 1
            if fails > max_fails:
                self._last_error = MicroSDExpError.TIMEOUT
                return sent
            st = self.read_status()
            if st is not None and st.state == MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                return sent
            if st is not None and st.rx_free > 0:
                # Space became available (e.g. the NACK landed mid-block):
                # retry at once instead of idling a poll interval.
                continue
            time.sleep(self._flow_poll_ms / 1000.0)
        return sent

    def read(self, n):
        """
        Read up to ``n`` bytes from the open file.

        :param n: The number of bytes to read
        :type n: int
        :return: The bytes read (short at end of file)
        :rtype: bytes
        """
        if n == 0 or not self._file_open:
            if not self._file_open:
                self._last_error = MicroSDExpError.NO_FILE
            return b""
        if self._append_mode:
            self._last_error = MicroSDExpError.INVALID
            return b""
        out = bytearray()
        t0 = time.monotonic()
        limit = self.scale_timeout(COMMIT_TIMEOUT_MS) / 1000.0
        while len(out) < n:
            if (time.monotonic() - t0) >= limit:
                self._last_error = MicroSDExpError.TIMEOUT
                break
            st = self.read_status()
            if st is None:
                time.sleep(self._poll_ms / 1000.0)
                continue
            if st.state == MICROSDEXP_ST_ERROR:
                self._last_error = MicroSDExpError.CARD_ERR
                break
            if st.tx_avail > 0:
                want = min(st.tx_avail, n - len(out), self._read_chunk)
                chunk = self._read(MICROSDEXP_CMD_READ, want)
                if chunk is None:
                    if want > 32:
                        # This backend caps one bus transaction below the
                        # configured chunk -- drop to an always-safe 32 B and
                        # retry the drain.
                        self._read_chunk = 32
                        continue
                    self._last_error = MicroSDExpError.CARD_ERR
                    break
                out.extend(chunk[:want])
                continue
            if st.state == MICROSDEXP_ST_COMPLETE:
                break
            time.sleep(self._poll_ms / 1000.0)

        self._last_error = MicroSDExpError.OK if len(out) > 0 else self._last_error
        if len(out) == n:
            self._last_error = MicroSDExpError.OK
        self._written = len(out)
        return bytes(out)

    def sync(self):
        """
        Wait until every byte written so far is committed to the card.

        :return: `True` when the data is on the card
        :rtype: bool
        """
        if not self._file_open or self._append_mode or self._read_started:
            return True
        target = self._base_written + self._written
        ok = self.wait_for_committed(target)
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.TIMEOUT
        return ok

    def close(self):
        """
        Flush, close and wait for the data to be committed to the card.

        :return: `True` on success
        :rtype: bool
        """
        if not self._file_open:
            return True
        if self._append_mode:
            self._file_open = False
            self._append_mode = False
            self._read_started = False
            self._last_error = MicroSDExpError.OK
            return True
        ok = self.sync()
        st = self.read_status()
        db = st.op_done if st is not None else 0
        if not self._write(bytes([MICROSDEXP_CMD_CLOSE_FLUSH])):
            self._last_error = MicroSDExpError.CARD_ERR
            self._file_open = False
            self._read_started = False
            return False
        cw = self.wait_for_op_complete(db)
        self._file_open = False
        self._read_started = False
        if cw != 0:
            self._last_error = MicroSDExpError.TIMEOUT if cw == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return ok

    def open(self, path, mode="r"):
        """
        ``open(path, "r"|"w"|"a")`` -> a MicroSDExpFile handle, or None.

        The module supports one open file at a time.

        :param path: File path on the card
        :type path: str
        :param mode: "r" (read), "w" (write/truncate) or "a" (append)
        :type mode: str
        :return: A file handle, or None if the open failed
        :rtype: MicroSDExpFile
        """
        m = (mode or "")[:1].lower()
        if m == "w":
            ok = self.open_write(path)
        elif m == "a":
            ok = self.open_append(path)
        elif m == "r":
            ok = self.open_read(path)
        else:
            return None
        if not ok:
            return None
        return MicroSDExpFile(self, mode_code={"r": 0, "w": 1, "a": 2}.get(m, 0))

    #---------------------------------------------------------------------------
    # Expansion pins + bit-bang engine

    def set_pin_mode(self, pin, mode):
        """
        Put an expansion pin in ``mode`` (0 = digital output).

        Applies immediately in RAM. Modes persist to the module EEPROM only on
        an explicit save_pin_mode() -- the module never writes EEPROM on a mode
        change, so repeated identical applies are a library-side no-op.

        :param pin: MICROSDEXP_PIN_PA5 / MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3
        :type pin: int
        :param mode: The pin mode (0 = digital output)
        :type mode: int
        :return: `True` on success
        :rtype: bool
        """
        cmd = _PIN_MODE_CMD.get(pin)
        if cmd is None:
            self._last_error = MicroSDExpError.INVALID
            return False
        # Dedup: only RAM applies, only an explicit save persists, so a
        # redundant apply writes nothing and never churns the EEPROM.
        if self._pin_last_mode.get(pin) == mode:
            return True
        self._pin_last_mode[pin] = mode
        return self._write(bytes([cmd, mode & 0xFF]))

    def save_pin_mode(self):
        """
        Persist the configured pin modes + I2C address to module EEPROM.

        Sends CMD_SAVEEEPROM (0x1A): STOP only, no payload. This is the only
        command that persists -- call it once when configuration is final to
        avoid wearing the EEPROM on dev-loop churn.

        :return: `True` if the command was acknowledged
        :rtype: bool
        """
        return self._write(bytes([MICROSDEXP_CMD_SAVEEEPROM]))

    def write_pin(self, pin, value):
        """
        Drive an output-mode expansion pin high (1) or low (0).

        :param pin: MICROSDEXP_PIN_PA5 / MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3
        :type pin: int
        :param value: 1 = high, 0 = low
        :type value: int
        :return: `True` on success
        :rtype: bool
        """
        cmd = _PIN_CONTROL_CMD.get(pin)
        if cmd is None:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([cmd, 1 if value else 0]))

    def bitbang_set_mode(self, pin):
        """
        Select the bit-bang engine's data pin (PA5 / PB2 / PB3).

        This only selects the pin for the engine; it does not set its
        direction -- call set_pin_mode(pin, 0) first.

        :param pin: MICROSDEXP_PIN_PA5 / MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3
        :type pin: int
        :return: `True` on success
        :rtype: bool
        """
        if pin not in _PIN_IDS:
            self._last_error = MicroSDExpError.INVALID
            return False
        return self._write(bytes([MICROSDEXP_CMD_BITBANG_SET_MODE, pin]))

    def bitbang_buffer(self, offset, data, length=None):
        """
        Copy bytes into the module's 256 B workspace at ``offset``.

        Long payloads are split so the 3-byte header and its payload travel in
        one transaction. The whole workspace is addressable, but a single
        request must stay inside it: the firmware refuses (NACKs) any data byte
        at ``offset + index >= 256``, so ``offset + count <= 256`` is enforced
        here instead of relying on NAK detection.

        :param offset: Workspace offset (0-255)
        :type offset: int
        :param data: The bytes to copy
        :type data: bytes, bytearray or list of ints
        :param length: Optional byte count (defaults to len(data))
        :type length: int
        :return: `True` on success
        :rtype: bool
        """
        if not data:
            self._last_error = MicroSDExpError.INVALID
            return False
        buf = bytes(bytearray(data))
        count = len(buf) if length is None else min(int(length), len(buf))
        if (
            count <= 0
            or offset < 0
            or offset >= BITBANG_WORKSPACE_SIZE
            or (offset + count) > BITBANG_WORKSPACE_SIZE
        ):
            self._last_error = MicroSDExpError.INVALID
            return False
        # One workspace write is command + 3 header bytes + payload.
        per_write = self._write_chunk - 3
        if per_write < 1:
            per_write = 1
        sent = 0
        while sent < count:
            chunk = count - sent
            if chunk > per_write:
                chunk = per_write
            at = offset + sent
            payload = (
                bytes(
                    [
                        MICROSDEXP_CMD_BITBANG_BUFFER,
                        at & 0xFF,
                        (at >> 8) & 0xFF,
                        chunk,
                    ]
                )
                + buf[sent : sent + chunk]
            )
            if not self._write(payload):
                return False
            sent += chunk
        return True

    def bitbang_execute(self, profile):
        """
        Run a bit-bang profile (0x01 NeoPixel, 0x02 script).

        The module plays it from its own loop with interrupts masked, so it
        serves no I2C until the blit or script finishes.

        :param profile: MICROSDEXP_BITBANG_PROFILE_NEOPIXEL or _SCRIPT
        :type profile: int
        :return: `True` on success
        :rtype: bool
        """
        return self._write(bytes([MICROSDEXP_CMD_BITBANG_EXECUTE, profile & 0xFF]))

    def bitbang_clear(self):
        """
        Zero the workspace and the module's buffered-length mark.

        :return: `True` on success
        :rtype: bool
        """
        return self._write(bytes([MICROSDEXP_CMD_BITBANG_CLEAR]))

    def show_neopixels(self, pin, grb, pixel_count=None):
        """
        Push a WS2812B frame (raw GRB triplets) and latch it.

        ``grb`` holds three bytes per pixel, green first; ``pixel_count``
        defaults to ``len(grb) // 3``. A frame holds at most 85 pixels (255 of
        the 256 B workspace).

        The pin must already be a digital output (set_pin_mode(pin, 0)), and
        the caller must leave a frame time (~30 us/pixel plus the latch reset)
        before the next I2C command -- the module clocks the frame out after it
        ACKs the execute.

        :param pin: MICROSDEXP_PIN_PA5 / MICROSDEXP_PIN_PB2 / MICROSDEXP_PIN_PB3
        :type pin: int
        :param grb: The GRB frame bytes
        :type grb: bytes, bytearray or list of ints
        :param pixel_count: Optional pixel count (defaults to len(grb)//3)
        :type pixel_count: int
        :return: `True` on success
        :rtype: bool
        """
        if not grb:
            self._last_error = MicroSDExpError.INVALID
            return False
        buf = bytes(bytearray(grb))
        count = len(buf) // 3 if pixel_count is None else int(pixel_count)
        if count <= 0 or count * 3 > 255:
            self._last_error = MicroSDExpError.INVALID
            return False
        if not self.bitbang_set_mode(pin):
            return False
        if not self.bitbang_buffer(0, buf[: count * 3]):
            return False
        return self.bitbang_execute(MICROSDEXP_BITBANG_PROFILE_NEOPIXEL)

    #---------------------------------------------------------------------------
    # Housekeeping

    def set_clock_time(self, year, month, day, hour, minute, second):
        """
        Write the module's clock (CMD_CLOCK_SET, 0x0E: 6 B [Y,M,D,h,m,s]).

        :param year: Year (firmware-defined offset)
        :type year: int
        :param month: Month 1-12
        :type month: int
        :param day: Day 1-31
        :type day: int
        :param hour: Hour 0-23
        :type hour: int
        :param minute: Minute 0-59
        :type minute: int
        :param second: Second 0-59
        :type second: int
        :return: `True` if the command was acknowledged
        :rtype: bool
        """
        ok = self._write(
            bytes(
                [
                    MICROSDEXP_CMD_CLOCK_SET,
                    year & 0xFF,
                    month & 0xFF,
                    day & 0xFF,
                    hour & 0xFF,
                    minute & 0xFF,
                    second & 0xFF,
                ]
            )
        )
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.NO_MODULE
        return ok

    def reboot(self):
        """
        Reboot the module (watchdog reset from its loop).

        :return: `True` if the command was acknowledged
        :rtype: bool
        """
        ok = self._write(bytes([MICROSDEXP_CMD_REBOOT]))
        self._last_error = MicroSDExpError.OK if ok else MicroSDExpError.NO_MODULE
        return ok

    def format(self, mode=0):
        """
        Format the card -- DESTRUCTIVE. Explicit call only: the library keeps
        no token, the guard belongs in the sketch/UI.

        :param mode: 0 = auto, 1 = force FAT
        :type mode: int
        :return: `True` on success
        :rtype: bool
        """
        if mode > 1:
            self._last_error = MicroSDExpError.INVALID
            return False
        st = self.read_status()
        done_before = st.op_done if st is not None else 0
        if not self._write(bytes([MICROSDEXP_CMD_FORMAT, mode & 0xFF])):
            return False
        # A full FAT rebuild takes tens of seconds on a multi-GB card (a 7.4 GB
        # card measures ~52 s), which is well past OP_TIMEOUT_MS.
        limit_ms = self.scale_timeout(FORMAT_TIMEOUT_MS)
        if limit_ms < FORMAT_TIMEOUT_MS:
            limit_ms = FORMAT_TIMEOUT_MS
        err = self._wait_for_op(done_before, limit_ms / 1000.0)
        if err != 0:
            self._last_error = MicroSDExpError.TIMEOUT if err == -1 else MicroSDExpError.CARD_ERR
            return False
        self._last_error = MicroSDExpError.OK
        return True


#===============================================================================
class MicroSDExpFile(object):
    """
    Single-file handle returned by QwiicSDExpansion.open().

    The module supports one open file at a time, so the handle is a thin view
    over its owning module object.
    """

    def __init__(self, microSDexp, mode_code=0):
        self._microSDexp = microSDexp
        self._open = True
        self.mode = mode_code  # 0 = r, 1 = w, 2 = a
        self.nil = False

    @property
    def microSDexp(self):
        """:return: The owning QwiicSDExpansion object"""
        return self._microSDexp

    @property
    def is_open(self):
        """:return: `True` while the handle is open"""
        return self._open

    def write(self, data):
        """Write bytes to the file. Returns the number of bytes accepted."""
        if not self._open or self._microSDexp is None:
            return 0
        return self._microSDexp.write(bytes(bytearray(data)))

    def read(self, n):
        """Read up to n bytes. Returns bytes (short at end of file)."""
        if not self._open or self._microSDexp is None:
            return b""
        return self._microSDexp.read(n)

    def sync(self):
        """Wait until the written data is committed to the card."""
        if not self._open or self._microSDexp is None:
            return False
        return self._microSDexp.sync()

    def close(self):
        """Flush, close and wait for the data to be committed."""
        if not self._open or self._microSDexp is None:
            return False
        ok = self._microSDexp.close()
        self._open = False
        return ok

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False


#===============================================================================
# Qwiic_Py derives the class name from the module name by title-casing the
# underscored parts, which yields "QwiicSdExpansionPy" for
# "qwiic_sd_expansion_py". Keep that spelling as an alias so the package
# loader binds the exact name it looks for.
QwiicSdExpansionPy = QwiicSDExpansion

__all__ = [
    "QwiicSDExpansion",
    "QwiicSdExpansionPy",
    "MicroSDExpFile",
    "MicroSDExpError",
    "StatusFrame",
    "CardInfo",
    "DirEntry",
    "MICROSDEXP_PIN_PA5",
    "MICROSDEXP_PIN_PB2",
    "MICROSDEXP_PIN_PB3",
    "MICROSDEXP_BITBANG_PROFILE_NEOPIXEL",
    "MICROSDEXP_BITBANG_PROFILE_SCRIPT",
]
