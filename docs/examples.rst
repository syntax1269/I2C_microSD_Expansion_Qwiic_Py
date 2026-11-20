Examples
########

Each example is standalone and uses the Qwiic discovery mechanism where
available.

File write and read
-------------------

.. literalinclude:: ../examples/ex1_file_write_read.py
    :caption: examples/ex1_file_write_read.py
    :linenos:

Directory and card information
------------------------------

.. literalinclude:: ../examples/ex2_directory_and_card.py
    :caption: examples/ex2_directory_and_card.py
    :linenos:

Pins and NeoPixel output
------------------------

.. literalinclude:: ../examples/ex3_pins_and_neopixel.py
    :caption: examples/ex3_pins_and_neopixel.py
    :linenos:

Ring-buffer data logger
-----------------------

500 Hz sampling into a 512-byte ring, drained with ``write_now()``.

.. literalinclude:: ../examples/ex6_sensor_ring_logger.py
    :caption: examples/ex6_sensor_ring_logger.py
    :linenos:

Persistent config manager
-------------------------

Checked queries, a checksummed config file and a staged update.

.. literalinclude:: ../examples/ex7_config_save_load.py
    :caption: examples/ex7_config_save_load.py
    :linenos:

Dual-module mirror / failover
-----------------------------

Two modules on one bus, with ``sticky_error`` failover.

.. literalinclude:: ../examples/ex8_dual_module_mirror.py
    :caption: examples/ex8_dual_module_mirror.py
    :linenos:

Sensor alert with module-side strobe
------------------------------------

CSV logging plus a timed bit-bang script the module plays on PB2.

.. literalinclude:: ../examples/ex9_threshold_bitbang_alert.py
    :caption: examples/ex9_threshold_bitbang_alert.py
    :linenos:
