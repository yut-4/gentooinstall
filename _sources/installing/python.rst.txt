.. _installing.python:

Python library
==============

`gentooinstall` can be installed from PyPI or from source.

Install from PyPI
-----------------

.. code-block:: console

    pip install gentooinstall

.. _installing.python.manual:

Install from source
-------------------

.. code-block:: console

    git clone https://github.com/gentooinstall/gentooinstall
    cd gentooinstall
    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e .

Use as a module
---------------

.. code-block:: console

    python -m gentooinstall --script list

.. code-block:: console

    python -m gentooinstall --script guided

Declarative examples
--------------------

.. code-block:: console

    gentooinstall --config examples/gentoo-grub-uefi.json
    gentooinstall --config examples/gentoo-grub-bios.json
