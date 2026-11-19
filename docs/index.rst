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
