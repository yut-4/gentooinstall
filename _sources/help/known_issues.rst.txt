.. _help.known_issues:

Known Issues
============

Some issues are outside ``gentooinstall`` itself and come from the live
environment, mirror/network availability, or hardware-specific kernel support.

Waiting for time sync
---------------------

If ``timedatectl`` never reports synchronized time, NTP or DNS is usually not
working yet.

Workarounds:

- Verify network connectivity first.
- Restart ``systemd-timesyncd``.
- If system time is already correct, run with ``--skip-ntp``.

Missing kernel modules or firmware
----------------------------------

Some devices need extra firmware or kernel module packages after first boot.
This is hardware-specific and may require adding packages in profile or
``packages`` configuration.

Mirror reachability issues
--------------------------

When many mirrors are unreachable, installation can fail or stall.
Set a stable mirror list in ``mirror_config`` or ``GENTOO_MIRRORS`` before
running installation.

Bug reporting
-------------

When reporting issues, attach ``/var/log/gentooinstall/install.log`` and share
exact configuration inputs used during the run.

Issue tracker:
`https://github.com/gentooinstall/gentooinstall/issues <https://github.com/gentooinstall/gentooinstall/issues>`_
