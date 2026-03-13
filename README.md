<img src="docs/logo.png" alt="gentooinstall logo" width="200"/>

# gentooinstall

Guided and scriptable installer for Gentoo Linux.

`gentooinstall` can be used as:
- Interactive TUI installer (`guided` script)
- Non-interactive installer from JSON config
- Python library for custom install flows

## Run this project

Run on a live system as root:

```sh
gentooinstall
```

Run from this repository (recommended for development/testing):

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
gentooinstall --script guided
```

Other built-in scripts:

```sh
gentooinstall --script list
gentooinstall --script minimal
gentooinstall --script only_hd
```

## Declarative installs (JSON)

Use config and credentials files:

```sh
gentooinstall --config ./user_configuration.json --creds ./user_credentials.json
```

Sample files:
- [`examples/config-sample.json`](examples/config-sample.json)
- [`examples/gentoo-grub-uefi.json`](examples/gentoo-grub-uefi.json)
- [`examples/gentoo-grub-bios.json`](examples/gentoo-grub-bios.json)
- [`examples/creds-sample.json`](examples/creds-sample.json)

Credentials decryption key can be passed via:
- `--creds-decryption-key`
- `GENTOOINSTALL_CREDS_DECRYPTION_KEY`

## Gentoo real mode (stage3 + architecture)

`gentooinstall` resolves stage3 artifacts directly from Gentoo distfiles and can use `wgetload` for robust downloads.

`gentoo.architecture` supports:
- `auto`, `amd64`, `arm64`, `arm`, `x86`, `ppc`, `ppc64`, `hppa`, `mips`, `riscv`, `s390`, `sparc`, `alpha`, `loong`

`gentoo.init_system`:
- `systemd` or `openrc`

`gentoo.sync_mode`:
- `sync`, `webrsync`, `none`

`gentoo.make_conf`:
- `COMMON_FLAGS`/`CFLAGS`/`CXXFLAGS`/`MAKEOPTS`/`USE`/`FEATURES` and extra keys

## Bootloader support in GentooInstaller

Implemented bootloaders:
- `Grub` (UEFI + BIOS targets with architecture mapping)
- `Systemd-boot` (UEFI)
- `Efistub` (UEFI)
- `Refind` (UEFI)
- `Limine` (UEFI + BIOS for x86/amd64)

GRUB target mapping used automatically:
- UEFI: `x86_64-efi`, `i386-efi`, `arm64-efi`, `arm-efi`, `riscv64-efi`, `loongarch64-efi`
- BIOS/legacy: `i386-pc`, `powerpc-ieee1275`

## Ready-to-run GRUB examples

UEFI profile:

```sh
gentooinstall --config examples/gentoo-grub-uefi.json
```

BIOS profile:

```sh
gentooinstall --config examples/gentoo-grub-bios.json
```

Both examples are designed as starting templates. Update `disk_config.device_modifications[].device` and network interface values before production installs.

## wgetload helper

The helper module [`gentooinstall/wgetload.py`](gentooinstall/wgetload.py) resolves stage3 tarballs per architecture/init-system and handles downloads (`wget` -> `curl` -> urllib fallback).

Examples:

```sh
wgetload resolve-stage3 --arch arm64 --init-system systemd
wgetload resolve-stage3 --arch riscv --init-system openrc
wgetload download https://distfiles.gentoo.org/.../stage3-*.tar.xz /tmp/stage3.tar.xz
```

## Logs and support

Main log file:

```text
/var/log/gentooinstall/install.log
```

Issue tracker:
- https://github.com/gentooinstall/gentooinstall/issues

Community chat:
- Discord: https://discord.gg/aDeMffrxNg
- Matrix: https://matrix.to/#/#gentooinstall:matrix.org
- Libera IRC: https://web.libera.chat/?channel=#gentooinstall

## Profiles

Built-in profiles:
- [`gentooinstall/default_profiles/desktops`](gentooinstall/default_profiles/desktops)
- [`gentooinstall/default_profiles/servers`](gentooinstall/default_profiles/servers)

## Documentation

- https://gentooinstall.readthedocs.io/
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`docs/README.md`](docs/README.md)
