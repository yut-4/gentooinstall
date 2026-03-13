.. _installing.gentoo_real:

Gentoo Real Mode
================

This page describes the practical flow used by ``gentooinstall`` for real Gentoo installs,
including architecture handling, stage3 resolution, and GRUB setup.

Run from source
---------------

.. code-block:: sh

    python3 -m venv .venv
    . .venv/bin/activate
    pip install -e .
    gentooinstall --script guided

Run declarative install
-----------------------

.. code-block:: sh

    gentooinstall --config examples/gentoo-grub-uefi.json

or:

.. code-block:: sh

    gentooinstall --config examples/gentoo-grub-bios.json

Update device paths and interfaces before using these in production.

Architecture and stage3
-----------------------

Under the ``gentoo`` config key:

- ``architecture`` supports: ``auto``, ``amd64``, ``arm64``, ``arm``, ``x86``, ``ppc``, ``ppc64``, ``hppa``, ``mips``, ``riscv``, ``s390``, ``sparc``, ``alpha``, ``loong``.
- ``init_system`` supports: ``systemd`` or ``openrc``.
- ``sync_mode`` supports: ``sync``, ``webrsync``, ``none``.

Stage3 resolution uses Gentoo distfiles and can be tested directly:

.. code-block:: sh

    wgetload resolve-stage3 --arch amd64 --init-system systemd
    wgetload resolve-stage3 --arch riscv --init-system openrc

Bootloaders
-----------

Implemented in GentooInstaller:

- ``Grub``: UEFI and BIOS/legacy paths.
- ``Systemd-boot``: UEFI.
- ``Efistub``: UEFI.
- ``Refind``: UEFI.
- ``Limine``: UEFI and BIOS for ``amd64``/``x86``.

GRUB target selection is architecture-aware:

- UEFI: ``x86_64-efi``, ``i386-efi``, ``arm64-efi``, ``arm-efi``, ``riscv64-efi``, ``loongarch64-efi``.
- BIOS/legacy: ``i386-pc``, ``powerpc-ieee1275``.

If the requested firmware/architecture combination is unsupported for automatic setup,
installation fails with an explicit error instead of silently installing an incorrect target.

Config tips
-----------

- For UEFI + GRUB, keep a FAT ESP mounted as ``/boot`` and use ``bootloader_config.bootloader = "Grub"``.
- For BIOS + GRUB on GPT disks, ensure your partition layout includes what GRUB requires for your platform.
- If you override stage3/profile manually, keep profile and architecture aligned (for example ``amd64`` profile on ``amd64`` systems).
