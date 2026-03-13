gentooinstall Documentation
=========================

**gentooinstall** is a library which can be used to install Gentoo Linux.
The library comes packaged with different pre-configured installers, such as the default :ref:`guided` installer.

Some of the features of gentooinstall are:

* **Context friendly.** The library always executes calls in sequential order to ensure installation-steps don't overlap or execute in the wrong order. It also supports *(and uses)* context wrappers to ensure cleanup and final kernel/initramfs tasks are called when needed.

* **Full transparency** Logs and insights can be found at ``/var/log/gentooinstall`` both in the live ISO and partially on the installed system.

* **Accessibility friendly** gentooinstall works with ``espeakup`` and other accessibility tools thanks to the use of a TUI.

.. toctree::
   :maxdepth: 1
   :caption: Running gentooinstall

   installing/guided
   installing/gentoo_real

.. toctree::
   :maxdepth: 3
   :caption: Getting help

   help/known_issues
   help/report_bug
   help/discord

.. toctree::
   :maxdepth: 3
   :caption: gentooinstall as a library

   installing/python
   examples/python
   gentooinstall/plugins

.. toctree::
   :maxdepth: 3
   :caption: API Reference

   gentooinstall/Installer
