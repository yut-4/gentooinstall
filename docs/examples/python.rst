.. _examples.python:

Python module
=============

You can run `gentooinstall` in module mode and execute built-in scripts.

.. code-block:: console

    python -m gentooinstall --script list

.. code-block:: console

    python -m gentooinstall --script guided

Creating custom script entry points
-----------------------------------

Custom scripts can live under ``gentooinstall/scripts`` and be executed with
``--script <name>``.

Minimal example:

.. code-block:: python

    from gentooinstall.lib.disk.device_handler import device_handler
    from pprint import pprint

    pprint(device_handler.devices)

Most installer library calls require root privileges.
