Qwiic Python — I2C microSD Expansion
====================================

``qwiic_sd_expansion_py`` is the SparkFun Qwiic Python driver for the I²C
microSD Expansion module. It is dynamically discoverable by the Qwiic Python
package and works on any platform supported by ``qwiic_i2c`` — Raspberry Pi,
other Linux single-board computers, or desktop CPython with an I²C adapter.

The module owns the SD card and the FAT filesystem. Your Python code opens
files, writes and reads bytes, lists directories, queries card health and
drives the module's expansion pins and bit-bang engine over plain I²C.

.. code-block:: python

   import qwiic_sd_expansion_py

   microSDexp = qwiic_sd_expansion_py.QwiicSDExpansion()
   if not microSDexp.begin():
       raise SystemExit("microSD expansion not found")

   print(microSDexp.version())          # e.g. "18.8.22"

   f = microSDexp.open("HELLO.TXT", "w")
   f.write(b"HELLO-WORLD")
   f.close()                            # returns once it is on the card

   r = microSDexp.open("HELLO.TXT", "r")
   print(r.read(32))                    # b'HELLO-WORLD'
   r.close()

Use ``QwiicSDExpansion(address=0x6C)`` for a re-addressed module, or
``QwiicSDExpansion(i2c_driver=bus)`` to reuse a bus driver you already created.

Requirements
------------

* A Python 3 host with ``qwiic_i2c`` and an I²C bus.
* An I²C microSD Expansion module with a FAT16/FAT32-formatted microSD card.
* Module firmware 18.5.x or newer for files, 18.5.2 for pins/bit-bang and
  18.8.0 for banner frames and the measured-clock report.

Installation
------------

.. code-block:: sh

   pip install sparkfun_qwiic_sd_expansion_py

Or clone the repository and run ``pip install -r requirements.txt``.

Design notes
------------

* One file can be open at a time. ``close()`` and ``sync()`` return only after
  the bytes are committed to the card.
* ``last_error`` is the result of the most recent call and may be overwritten
  by internal traffic. ``sticky_error`` is the first failure since
  ``clear_error()`` and cannot be hidden.
* ``temperature_k()`` and ``adc_pa5()`` return ``0xFFFF`` on any failure.

Diagnostics
-----------

:meth:`~qwiic_sd_expansion_py.QwiicSDExpansion.diagnostics` returns a one-page
health report for troubleshooting. It is safe before ``begin()`` (unreadable
fields show as ``n/a``) and does not change ``last_error``.

.. code-block:: python

   print(microSDexp.diagnostics())

.. toctree::
    :caption: API Reference
    :maxdepth: 3

    api

.. toctree::
    :caption: Examples

    examples

.. toctree::
    :caption: Links

    Source repository <https://github.com/syntax1269/I2C_microSD_Expansion_Qwiic_Py>
    Qwiic Python (transport) <https://github.com/sparkfun/Qwiic_I2C_Py>
    Arduino port <https://i2c-microsd-expansion.readthedocs.io/>
    CircuitPython port <https://i2c-microsd-expansion-circuitpython.readthedocs.io/>
    PyPI package <https://pypi.org/project/sparkfun-qwiic-sd-expansion-py/>

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Building these docs locally
---------------------------

From the repository root::

    pip install -r docs/requirements.txt
    python -m sphinx -b html -W docs docs/_build/html

Blocking behavior
-----------------

Most high-level methods are **synchronous**: they poll the module's STATUS
frame with a short ``delay()`` until the operation completes or a timeout
expires. The I²C bus stays protocol-responsive, but your sketch/application is
blocked for the duration — plan for watchdogs, real-time loops, cooperative
schedulers and ESP32 tasks.

Timeouts scale up on slow buses and are capped at 120 s by the host.
``begin()`` takes ~1.5 s; ``openWrite()``/``openRead()`` may retry up to six
times; ``write()``/``read()``/``sync()``/``close()`` can each wait tens of
seconds; ``format()`` is destructive and can take minutes (per-wait cap 120 s).
``bitbang*()``/``showNeoPixels()``/``savePINMode()``/``diagnostics()`` only do a
bounded number of I²C transactions.

Non-blocking API
----------------

If your application cannot block, use the submit/poll API: ``begin_open_write``,
``begin_open_read``, ``begin_close``, ``begin_format`` and ``begin_query`` submit
a command without waiting; :meth:`~i2c_microsd_module.I2CmicroSD.poll_op` or
:meth:`~qwiic_sd_expansion_py.QwiicSDExpansion.poll_op` performs one STATUS read
and returns ``ASYNC_BUSY``, ``ASYNC_OK`` or a module error. ``write_now`` and
``read_now`` move only what fits right now (zero/empty means "try again"), and
``committed_bytes`` reports the commit counter. Only one operation may be
pending at a time. No feature flag is needed; the blocking API is unchanged.

Checked queries
---------------

The ``*_checked`` query variants (``exists_checked``, ``file_size_checked``,
``is_directory_checked``) return ``(ok, value)``, so "not found" is distinct
from a failed I²C transaction. ``last_ok`` is shorthand for checking
``last_error``. The original methods are unchanged.

