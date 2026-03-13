.. _help.issues:

Report Issues & Bugs
====================

Issues and bugs should be reported at:
`https://github.com/gentooinstall/gentooinstall/issues <https://github.com/gentooinstall/gentooinstall/issues>`_.

Log files
---------

When submitting a help ticket, include:

- ``/var/log/gentooinstall/install.log``

Quick upload example:

.. code-block:: console

   curl -F 'file=@/var/log/gentooinstall/install.log' https://0x0.st

Additional logs under ``/var/log/gentooinstall/`` may help, but can include
sensitive information. Review them before sharing.
