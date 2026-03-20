.. _guided:

Guided installation
===================

`gentooinstall` ships with a guided TUI installer that walks through disk,
bootloader, network, user, and profile configuration.

Run guided installer
--------------------

.. code-block:: sh

    gentooinstall

The `guided` script is the default. The command above is equivalent to:

.. code-block:: sh

    gentooinstall --script guided

Run other built-in scripts
--------------------------

.. code-block:: sh

    gentooinstall --script list
    gentooinstall --script minimal
    gentooinstall --script only_hd

Declarative mode
----------------

You can provide saved answers with JSON files:

.. code-block:: sh

    gentooinstall --config config.json
    gentooinstall --config-url https://example.org/config.json

Credentials can be passed separately:

.. code-block:: sh

    gentooinstall --creds credentials.json

Notes
-----

- Use ``--dry-run`` to generate a config file without running installation steps.
- Use ``--silent`` only with complete config input.
- Use ``--skip-ntp`` or ``--skip-wkd`` only when you understand the tradeoffs.

Reference files
---------------

- ``examples/config-sample.json``
- ``examples/gentoo-grub-uefi.json``
- ``examples/gentoo-grub-bios.json``
- ``examples/creds-sample.json``
- ``examples/full_automated_installation.py``
