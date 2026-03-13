from __future__ import annotations

import glob
import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path
from subprocess import CalledProcessError
from types import TracebackType
from typing import Any, ClassVar
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from gentooinstall.lib.command import SysCommand, run
from gentooinstall.lib.disk.utils import get_parent_device_path
from gentooinstall.lib.exceptions import RequirementError, SysCallError
from gentooinstall.lib.hardware import SysInfo
from gentooinstall.lib.installer import Installer
from gentooinstall.lib.mirrors import MirrorListHandler
from gentooinstall.lib.models.bootloader import Bootloader
from gentooinstall.lib.models.device import PartitionModification, Size, SnapshotType, Unit
from gentooinstall.lib.models.gentoo import GentooConfiguration, GentooInitSystem, PortageSyncMode
from gentooinstall.lib.models.locale import LocaleConfiguration
from gentooinstall.lib.models.mirrors import MirrorConfiguration
from gentooinstall.lib.models.network import Nic
from gentooinstall.lib.models.packages import Repository
from gentooinstall.lib.models.users import User
from gentooinstall.lib.output import debug, error, info, warn
from gentooinstall.lib.translationhandler import tr
from gentooinstall.wgetload import canonical_architecture, download_file, resolve_stage3_source

_DEFAULT_STAGE3_SOURCE = 'https://distfiles.gentoo.org/releases/amd64/autobuilds/latest-stage3-amd64-systemd.txt'


class GentooInstaller(Installer):
	"""
	Gentoo-focused installer.
	Keeps the general gentooinstall workflow while bootstrapping stage3 + Portage.
	"""

	_PACKAGE_MAP: ClassVar[dict[str, str | None]] = {
		'base': None,
		'sudo': 'app-admin/sudo',
		'linux-firmware': 'sys-kernel/linux-firmware',
		'linux': 'sys-kernel/gentoo-kernel-bin',
		'linux-lts': 'sys-kernel/gentoo-kernel-bin',
		'linux-zen': 'sys-kernel/gentoo-kernel',
		'linux-hardened': 'sys-kernel/hardened-sources',
		'gentoo-kernel': 'sys-kernel/gentoo-kernel',
		'gentoo-kernel-bin': 'sys-kernel/gentoo-kernel-bin',
		'linux-headers': 'sys-kernel/linux-headers',
		'linux-lts-headers': 'sys-kernel/linux-headers',
		'linux-zen-headers': 'sys-kernel/linux-headers',
		'linux-hardened-headers': 'sys-kernel/linux-headers',
		'grub': 'sys-boot/grub',
		'efibootmgr': 'sys-boot/efibootmgr',
		'refind': 'sys-boot/refind',
		'limine': 'sys-boot/limine',
		'networkmanager': 'net-misc/networkmanager',
		'network-manager-applet': 'gnome-extra/nm-applet',
		'wpa_supplicant': 'net-wireless/wpa_supplicant',
		'iwd': 'net-wireless/iwd',
		'openssh': 'net-misc/openssh',
		'bluez': 'net-wireless/bluez',
		'bluez-utils': 'net-wireless/bluez',
		'pipewire': 'media-video/pipewire',
		'pipewire-pulse': 'media-video/pipewire',
		'wireplumber': 'media-video/wireplumber',
		'pulseaudio': 'media-sound/pulseaudio',
		'alsa-utils': 'media-sound/alsa-utils',
		'alsa-firmware': 'sys-kernel/linux-firmware',
		'sof-firmware': 'sys-kernel/linux-firmware',
		'cups': 'net-print/cups',
		'system-config-printer': 'net-print/system-config-printer',
		'cups-pk-helper': 'net-print/cups-pk-helper',
		'ufw': 'net-firewall/ufw',
		'nftables': 'net-firewall/nftables',
		'iptables': 'net-firewall/iptables',
		'firewalld': 'net-firewall/firewalld',
		'docker': 'app-containers/docker',
		'nginx': 'www-servers/nginx',
		'apache': 'www-servers/apache',
		'httpd': 'www-servers/apache',
		'lighttpd': 'www-servers/lighttpd',
		'mariadb': 'dev-db/mariadb',
		'postgresql': 'dev-db/postgresql',
		'tomcat10': 'www-servers/tomcat',
		'cockpit': 'sys-apps/cockpit',
		'udisks2': 'sys-fs/udisks',
		'packagekit': 'sys-apps/packagekit',
		'cronie': 'sys-process/cronie',
		'timeshift': 'sys-backup/timeshift',
		'grub-btrfs': 'sys-boot/grub-btrfs',
		'inotify-tools': 'dev-util/inotify-tools',
		'zram-generator': 'sys-block/zram-init',
		'libfido2': 'dev-libs/libfido2',
		'pam-u2f': 'sys-auth/pam_u2f',
	}

	def __init__(
		self,
		target: Path,
		disk_config: Any,
		base_packages: list[str] = [],
		kernels: list[str] | None = None,
		silent: bool = False,
		gentoo_config: GentooConfiguration | None = None,
	):
		base = base_packages or ['app-admin/sudo', 'sys-kernel/linux-firmware']
		kernel_selection = kernels or ['gentoo-kernel-bin']
		super().__init__(target, disk_config, base, kernel_selection, silent)
		self._runtime_mounts: list[Path] = []
		self._gentoo = gentoo_config or GentooConfiguration()

	def __exit__(
		self,
		exc_type: type[BaseException] | None,
		exc_value: BaseException | None,
		traceback: TracebackType | None,
	) -> bool | None:
		self._teardown_runtime_mounts()
		return super().__exit__(exc_type, exc_value, traceback)

	def sanity_check(
		self,
		offline: bool = False,
		skip_ntp: bool = False,
		skip_wkd: bool = False,
	) -> None:
		# Gentoo live media does not provide reflector/wkd services.
		# Keep this soft check so minimal live images are not blocked.
		if skip_ntp:
			return

		try:
			result = SysCommand('timedatectl show --property=NTPSynchronized --value').decode().strip()
			if result != 'yes':
				warn('NTP is not synchronized yet. Continuing anyway.')
		except SysCallError:
			warn('Could not verify NTP (timedatectl unavailable or no systemd). Continuing.')

	def run_command(self, cmd: str, peek_output: bool = False) -> SysCommand:
		chroot_cmd = f'chroot {shlex.quote(str(self.target))} /bin/bash -lc {shlex.quote(cmd)}'
		return SysCommand(chroot_cmd, peek_output=peek_output)

	def drop_to_shell(self) -> None:
		subprocess.check_call(f'chroot {shlex.quote(str(self.target))} /bin/bash', shell=True)

	def set_mirrors(
		self,
		mirror_list_handler: MirrorListHandler,
		mirror_config: MirrorConfiguration,
		on_target: bool = False,
	) -> None:
		del mirror_list_handler
		root = self.target if on_target else Path('/')
		make_conf = root / 'etc/portage/make.conf'
		make_conf.parent.mkdir(parents=True, exist_ok=True)

		if not make_conf.exists():
			make_conf.write_text('CFLAGS="-O2 -pipe"\nCXXFLAGS="${CFLAGS}"\n')

		servers: list[str] = []
		for server in mirror_config.custom_server_urls:
			clean = server.replace('$repo/os/$arch', '').rstrip('/')
			if clean:
				servers.append(clean)

		for region in mirror_config.mirror_regions:
			for url in region.urls:
				clean = url.replace('$repo/os/$arch', '').rstrip('/')
				if clean:
					servers.append(clean)

		if not servers:
			return

		unique_servers = list(dict.fromkeys(servers))
		self._upsert_kv(make_conf, 'GENTOO_MIRRORS', f'"{" ".join(unique_servers)}"')
		info(f'Configured GENTOO_MIRRORS in {make_conf}')

	def minimal_installation(
		self,
		optional_repositories: list[Repository] = [],
		generate_initramfs: bool | None = None,
		hostname: str | None = None,
		locale_config: LocaleConfiguration | None = LocaleConfiguration.default(),
		**legacy_kwargs: Any,
	) -> None:
		del optional_repositories, generate_initramfs, legacy_kwargs

		self._bootstrap_stage3()
		self._setup_runtime_mounts()
		self._apply_make_conf_settings()
		self._sync_portage()
		self._set_selected_profile()

		if locale_config:
			self.set_vconsole(locale_config)

		self._emerge_packages(self._base_packages, strict=True)
		self._helper_flags['base-strapped'] = True

		if hostname:
			self.set_hostname(hostname)

		if locale_config:
			self.set_locale(locale_config)
			self.set_keyboard_language(locale_config.kb_layout)

		self._helper_flags['base'] = True

		for function in self.post_base_install:
			info(f'Running post-installation hook: {function}')
			function(self)

	def genfstab(self, flags: str = '-U') -> None:
		del flags
		fstab_path = self.target / 'etc' / 'fstab'
		info(f'Updating {fstab_path}')

		cmds = [
			['genfstab', '-U', str(self.target)],
			['genfstab', '-U', '-p', str(self.target)],
			['genfstab', '-pU', '-f', str(self.target), str(self.target)],
		]

		output: bytes | None = None
		last_error: Exception | None = None
		for cmd in cmds:
			try:
				output = run(cmd).stdout
				break
			except (CalledProcessError, FileNotFoundError, RequirementError, SysCallError) as err:
				last_error = err

		if output is None:
			raise RequirementError(f'Could not generate fstab using any supported genfstab syntax: {last_error}')

		fstab_path.parent.mkdir(parents=True, exist_ok=True)
		with open(fstab_path, 'ab') as fp:
			fp.write(output)

		with open(fstab_path, 'a') as fp:
			for entry in self._fstab_entries:
				fp.write(f'{entry}\n')

	def add_additional_packages(self, packages: str | list[str]) -> None:
		self._emerge_packages(packages, strict=False, oneshot=True)

	def setup_swap(self, kind: str = 'zram', algo: Any = None) -> None:
		del algo
		if kind != 'zram':
			raise ValueError('GentooInstaller only supports automatic swap-on-zram setup')

		self.add_additional_packages('sys-block/zram-init')
		warn('zram-init was installed. Adjust /etc/conf.d/zram-init to your preferred RAM ratio.')

	def setup_btrfs_snapshot(
		self,
		snapshot_type: SnapshotType,
		bootloader: Bootloader | None = None,
	) -> None:
		del snapshot_type, bootloader
		warn('Automatic Btrfs snapshot configuration is not implemented yet for GentooInstaller.')

	def activate_time_synchronization(self) -> None:
		if self._gentoo.init_system == GentooInitSystem.OPENRC:
			info('Activating OpenRC time synchronization (chronyd)')
			self.add_additional_packages('net-misc/chrony')
			self.enable_service('chronyd')
			return

		info('Activating systemd-timesyncd for time synchronization')
		self.enable_service('systemd-timesyncd')

	def enable_service(self, services: str | list[str]) -> None:
		if self._gentoo.init_system == GentooInitSystem.SYSTEMD:
			super().enable_service(services)
			return

		if isinstance(services, str):
			services = [services]

		for service in services:
			normalized = self._normalize_service_name(service)
			if normalized in {'systemd-networkd', 'systemd-resolved', 'systemd-timesyncd'}:
				warn(f'Skipping systemd-only service "{service}" on OpenRC stage3')
				continue

			try:
				self.run_in_chroot(f'rc-update add {shlex.quote(normalized)} default', peek_output=True)
			except SysCallError as err:
				warn(f'Could not enable OpenRC service "{normalized}": {err}')

	def disable_service(self, services_disable: str | list[str]) -> None:
		if self._gentoo.init_system == GentooInitSystem.SYSTEMD:
			super().disable_service(services_disable)
			return

		if isinstance(services_disable, str):
			services_disable = [services_disable]

		for service in services_disable:
			normalized = self._normalize_service_name(service)
			try:
				self.run_in_chroot(f'rc-update del {shlex.quote(normalized)} default', peek_output=True)
			except SysCallError as err:
				debug(f'Could not disable OpenRC service "{normalized}": {err}')

	@staticmethod
	def _normalize_service_name(service: str) -> str:
		name = service.strip()
		for suffix in ('.service', '.target', '.timer'):
			if name.endswith(suffix):
				return name[: -len(suffix)]
		return name

	def set_keyboard_language(self, language: str) -> bool:
		if not language.strip():
			return True

		vconsole_path = self.target / 'etc' / 'vconsole.conf'
		vconsole_path.parent.mkdir(parents=True, exist_ok=True)

		lines = []
		if vconsole_path.exists():
			lines = vconsole_path.read_text().splitlines()

		updated = False
		for idx, line in enumerate(lines):
			if line.startswith('KEYMAP='):
				lines[idx] = f'KEYMAP={language}'
				updated = True
				break

		if not updated:
			lines.append(f'KEYMAP={language}')

		vconsole_path.write_text('\n'.join(lines) + '\n')
		return True

	def set_x11_keyboard_language(self, language: str) -> bool:
		# For Gentoo, X11 keyboard configuration is usually handled by the selected profile/DE.
		return bool(language is not None)

	def set_user_password(self, user: User) -> bool:
		info(f'Setting password for {user.username}')
		enc_password = user.password.enc_password

		if not enc_password:
			debug('User password is empty')
			return False

		input_data = f'{user.username}:{enc_password}'.encode()
		cmd = ['chroot', str(self.target), 'chpasswd', '--encrypted']

		try:
			run(cmd, input_data=input_data)
			return True
		except CalledProcessError as err:
			debug(f'Error setting user password: {err}')
			return False

	def configure_nic(self, nic: Nic) -> None:
		if self._gentoo.init_system == GentooInitSystem.SYSTEMD:
			super().configure_nic(nic)
			return

		if not nic.iface:
			raise ValueError('Manual network configuration requires a NIC interface name')

		conf_path = self.target / 'etc/conf.d/net'
		conf_path.parent.mkdir(parents=True, exist_ok=True)
		if not conf_path.exists():
			conf_path.write_text('')

		if nic.dhcp:
			self._upsert_shell_assignment(conf_path, f'config_{nic.iface}', 'dhcp')
		else:
			if nic.ip:
				self._upsert_shell_assignment(conf_path, f'config_{nic.iface}', nic.ip)
			if nic.gateway:
				self._upsert_shell_assignment(conf_path, f'routes_{nic.iface}', f'default via {nic.gateway}')
			if nic.dns:
				self._upsert_shell_assignment(conf_path, f'dns_servers_{nic.iface}', ' '.join(nic.dns))

		net_lo = self.target / 'etc/init.d/net.lo'
		net_iface = self.target / f'etc/init.d/net.{nic.iface}'
		if net_lo.exists() and not net_iface.exists():
			net_iface.symlink_to('net.lo')

		self.enable_service(f'net.{nic.iface}')

	def copy_iso_network_config(self, enable_services: bool = False) -> bool:
		if os.path.isdir('/var/lib/iwd/'):
			if psk_files := glob.glob('/var/lib/iwd/*.psk'):
				iwd_dir = self.target / 'var/lib/iwd'
				iwd_dir.mkdir(parents=True, exist_ok=True)

				for psk in psk_files:
					shutil.copy2(psk, iwd_dir / os.path.basename(psk))

				if enable_services:
					self.add_additional_packages('iwd')
					self.enable_service('iwd')

		resolv_target = self.target / 'etc/resolv.conf'
		resolv_target.parent.mkdir(parents=True, exist_ok=True)
		if Path('/etc/resolv.conf').exists():
			shutil.copy2('/etc/resolv.conf', resolv_target)

		if net_files := glob.glob('/etc/systemd/network/*'):
			if self._gentoo.init_system == GentooInitSystem.OPENRC:
				warn('Ignoring /etc/systemd/network/* from ISO because selected Gentoo stage3 uses OpenRC')
				return True

			target_dir = self.target / 'etc/systemd/network'
			target_dir.mkdir(parents=True, exist_ok=True)

			for netconf_file in net_files:
				shutil.copy2(netconf_file, target_dir / os.path.basename(netconf_file))

			if enable_services:
				self.enable_service(['systemd-networkd', 'systemd-resolved'])

		return True

	def add_bootloader(
		self,
		bootloader: Bootloader,
		uki_enabled: bool = False,
		bootloader_removable: bool = False,
	) -> None:
		if bootloader == Bootloader.NO_BOOTLOADER:
			return

		info(f'Adding bootloader {bootloader.value}')

		if uki_enabled:
			warn('UKI automation is not implemented yet for GentooInstaller; proceeding with regular kernel/initramfs.')

		if bootloader_removable:
			if not SysInfo.has_uefi():
				warn('Removable bootloader installation requested on non-UEFI system; disabling removable mode.')
				bootloader_removable = False
			elif not bootloader.has_removable_support():
				warn(f'Bootloader {bootloader.value} does not support removable mode; disabling.')
				bootloader_removable = False

		match bootloader:
			case Bootloader.Grub:
				self._install_grub(bootloader_removable)
			case Bootloader.Systemd:
				self._install_systemd_boot()
			case Bootloader.Efistub:
				self._install_efistub()
			case Bootloader.Refind:
				self._install_refind()
			case Bootloader.Limine:
				self._install_limine(bootloader_removable)

	def _install_grub(self, bootloader_removable: bool) -> None:
		boot_partition = self._get_boot_partition()
		if boot_partition is None:
			raise ValueError(f'Could not detect boot at mountpoint {self.target}')

		boot_mountpoint = boot_partition.mountpoint or Path('/boot')
		self.add_additional_packages('grub')
		command = ['grub-install', '--recheck']

		if SysInfo.has_uefi():
			efi_partition = self._require_efi_partition()
			if not efi_partition or not efi_partition.mountpoint:
				raise ValueError('Could not detect EFI system partition')

			self.add_additional_packages('efibootmgr')
			command.extend(
				[
					f'--target={self._grub_efi_target()}',
					f'--efi-directory={efi_partition.mountpoint}',
					'--bootloader-id=Gentoo',
				]
			)

			if boot_mountpoint != Path('/boot'):
				command.append(f'--boot-directory={boot_mountpoint}')

			if bootloader_removable:
				command.append('--removable')
		else:
			if bootloader_removable:
				warn('Ignoring removable mode for BIOS/legacy GRUB installation.')

			parent_dev_path = get_parent_device_path(boot_partition.safe_dev_path)
			command.extend(
				[
					f'--target={self._grub_bios_target()}',
					str(parent_dev_path),
				]
			)

		try:
			self.run_in_chroot(' '.join(shlex.quote(arg) for arg in command), peek_output=True)
		except SysCallError as err:
			raise RequirementError(f'Could not install GRUB bootloader: {err}')

		grub_cfg = f'{boot_mountpoint}/grub/grub.cfg'
		try:
			self.run_in_chroot(f'grub-mkconfig -o {shlex.quote(grub_cfg)}', peek_output=True)
		except SysCallError as err:
			raise RequirementError(f'Could not generate GRUB config: {err}')

		self._helper_flags['bootloader'] = 'grub'

	def _install_systemd_boot(self) -> None:
		if not SysInfo.has_uefi():
			raise RequirementError('Systemd-boot requires UEFI firmware.')

		boot_partition = self._get_boot_partition()
		if boot_partition is None or boot_partition.mountpoint is None:
			raise ValueError(f'Could not detect mounted /boot partition at {self.target}')

		efi_partition = self._require_efi_partition()
		self.add_additional_packages('efibootmgr')

		try:
			self.run_in_chroot('command -v bootctl >/dev/null 2>&1', peek_output=True)
		except SysCallError as err:
			raise RequirementError('systemd-boot requires bootctl (sys-apps/systemd) in the target system.') from err

		bootctl_cmd = ['bootctl']
		if boot_partition.mountpoint != efi_partition.mountpoint:
			bootctl_cmd.append(f'--esp-path={efi_partition.mountpoint}')
			bootctl_cmd.append(f'--boot-path={boot_partition.mountpoint}')
		bootctl_cmd.append('install')
		self.run_in_chroot(' '.join(shlex.quote(arg) for arg in bootctl_cmd), peek_output=True)

		kernel_path, initrd_path, boot_root = self._find_boot_artifacts()
		kernel_rel = self._boot_relative_path(kernel_path, boot_root)
		initrd_rel = self._boot_relative_path(initrd_path, boot_root) if initrd_path else None
		cmdline = self._kernel_cmdline()

		entries_dir = self._target_mount_path(boot_partition.mountpoint) / 'loader/entries'
		entries_dir.mkdir(parents=True, exist_ok=True)
		entry_file = entries_dir / 'gentoo.conf'

		entry_lines = [
			'title Gentoo Linux',
			f'linux {kernel_rel}',
		]
		if initrd_rel:
			entry_lines.append(f'initrd {initrd_rel}')
		if cmdline:
			entry_lines.append(f'options {cmdline}')
		entry_file.write_text('\n'.join(entry_lines) + '\n')

		loader_conf = self._target_mount_path(efi_partition.mountpoint) / 'loader/loader.conf'
		loader_conf.parent.mkdir(parents=True, exist_ok=True)
		self._upsert_space_kv(loader_conf, 'default', 'gentoo.conf')
		self._upsert_space_kv(loader_conf, 'timeout', '5')

		self._helper_flags['bootloader'] = 'systemd'

	def _install_efistub(self) -> None:
		if not SysInfo.has_uefi():
			raise RequirementError('Efistub boot entry requires UEFI firmware.')

		efi_partition = self._require_efi_partition()
		self.add_additional_packages('efibootmgr')

		kernel_path, initrd_path, _ = self._find_boot_artifacts()
		root = self._get_root()
		if root is None:
			raise ValueError(f'Could not detect root partition at mountpoint {self.target}')

		efi_dir = self._target_mount_path(efi_partition.mountpoint) / 'EFI/Gentoo'
		efi_dir.mkdir(parents=True, exist_ok=True)
		shutil.copy2(kernel_path, efi_dir / kernel_path.name)
		if initrd_path:
			shutil.copy2(initrd_path, efi_dir / initrd_path.name)

		parent_dev_path = get_parent_device_path(efi_partition.safe_dev_path)
		cmdline_parts = self._get_kernel_params(root)
		if initrd_path:
			cmdline_parts.append(f'initrd=\\EFI\\Gentoo\\{initrd_path.name}')

		command = [
			'efibootmgr',
			'--create',
			'--disk',
			str(parent_dev_path),
			'--part',
			str(efi_partition.partn),
			'--label',
			'Gentoo Linux',
			'--loader',
			f'\\EFI\\Gentoo\\{kernel_path.name}',
			'--unicode',
			' '.join(cmdline_parts),
			'--verbose',
		]
		SysCommand(' '.join(shlex.quote(arg) for arg in command), peek_output=True)

		self._helper_flags['bootloader'] = 'efistub'

	def _install_refind(self) -> None:
		if not SysInfo.has_uefi():
			raise RequirementError('rEFInd requires UEFI firmware.')

		self._require_efi_partition()
		self.add_additional_packages(['refind', 'efibootmgr'])

		try:
			self.run_in_chroot('refind-install', peek_output=True)
		except SysCallError as err:
			raise RequirementError(f'Could not install rEFInd: {err}')

		kernel_path, initrd_path, _ = self._find_boot_artifacts()
		cmdline = self._kernel_cmdline()
		config_path = kernel_path.parent / 'refind_linux.conf'

		lines: list[str] = []
		if initrd_path:
			lines.append(f'"Gentoo Linux" "{cmdline} initrd=\\{initrd_path.name}"')
			lines.append(f'"Gentoo Linux (alt)" "{cmdline} initrd=\\boot\\{initrd_path.name}"')
		else:
			lines.append(f'"Gentoo Linux" "{cmdline}"')

		config_path.write_text('\n'.join(lines) + '\n')
		self._helper_flags['bootloader'] = 'refind'

	def _install_limine(self, bootloader_removable: bool) -> None:
		boot_partition = self._get_boot_partition()
		if boot_partition is None or boot_partition.mountpoint is None:
			raise ValueError(f'Could not detect mounted /boot partition at {self.target}')

		self.add_additional_packages('limine')
		kernel_path, initrd_path, boot_root = self._find_boot_artifacts()
		cmdline = self._kernel_cmdline()

		if SysInfo.has_uefi():
			efi_partition = self._require_efi_partition()
			self.add_additional_packages('efibootmgr')

			limine_share = self.target / 'usr/share/limine'
			if not limine_share.exists():
				raise RequirementError('Limine package installed but /usr/share/limine is missing in target.')

			arch = self._target_architecture()
			loader_candidates = {
				'amd64': ['BOOTX64.EFI'],
				'x86': ['BOOTIA32.EFI', 'BOOTX64.EFI'],
				'arm64': ['BOOTAA64.EFI'],
				'riscv': ['BOOTRISCV64.EFI'],
				'loong': ['BOOTLOONGARCH64.EFI'],
			}.get(arch, ['BOOTX64.EFI', 'BOOTIA32.EFI'])

			install_subdir = 'BOOT' if bootloader_removable else 'gentoo-limine'
			efi_dir = self._target_mount_path(efi_partition.mountpoint) / 'EFI' / install_subdir
			efi_dir.mkdir(parents=True, exist_ok=True)

			loader_name: str | None = None
			for loader in loader_candidates:
				loader_src = limine_share / loader
				if loader_src.exists():
					shutil.copy2(loader_src, efi_dir / loader)
					if loader_name is None:
						loader_name = loader

			if loader_name is None:
				for loader_src in sorted(limine_share.glob('BOOT*.EFI')):
					shutil.copy2(loader_src, efi_dir / loader_src.name)
					if loader_name is None:
						loader_name = loader_src.name

			if loader_name is None:
				raise RequirementError('No Limine EFI loader binary found for this architecture.')

			if bootloader_removable:
				config_path = self._target_mount_path(boot_partition.mountpoint) / 'limine/limine.conf'
			else:
				config_path = efi_dir / 'limine.conf'

			path_root = 'boot()'
			if efi_partition != boot_partition and boot_partition.partuuid:
				path_root = f'uuid({boot_partition.partuuid})'

			self._write_limine_config(config_path, path_root, kernel_path, initrd_path, boot_root, cmdline)

			if not bootloader_removable:
				parent_dev_path = get_parent_device_path(efi_partition.safe_dev_path)
				loader_path = f'\\EFI\\gentoo-limine\\{loader_name}'
				command = [
					'efibootmgr',
					'--create',
					'--disk',
					str(parent_dev_path),
					'--part',
					str(efi_partition.partn),
					'--label',
					'Gentoo Limine',
					'--loader',
					loader_path,
					'--verbose',
				]
				SysCommand(' '.join(shlex.quote(arg) for arg in command), peek_output=True)
		else:
			if self._target_architecture() not in {'amd64', 'x86'}:
				raise RequirementError('Limine BIOS installation is only automated for x86/amd64 platforms.')

			limine_share = self.target / 'usr/share/limine'
			limine_bios = limine_share / 'limine-bios.sys'
			if not limine_bios.exists():
				raise RequirementError('limine-bios.sys not found in target system.')

			boot_limine_dir = self._target_mount_path(boot_partition.mountpoint) / 'limine'
			boot_limine_dir.mkdir(parents=True, exist_ok=True)
			shutil.copy2(limine_bios, boot_limine_dir / 'limine-bios.sys')

			parent_dev_path = get_parent_device_path(boot_partition.safe_dev_path)
			self.run_in_chroot(f'limine bios-install {shlex.quote(str(parent_dev_path))}', peek_output=True)

			path_root = f'uuid({boot_partition.partuuid})' if boot_partition.partuuid else 'boot()'
			config_path = boot_limine_dir / 'limine.conf'
			self._write_limine_config(config_path, path_root, kernel_path, initrd_path, boot_root, cmdline)

		self._helper_flags['bootloader'] = 'limine'

	def _write_limine_config(
		self,
		config_path: Path,
		path_root: str,
		kernel_path: Path,
		initrd_path: Path | None,
		boot_root: Path,
		cmdline: str,
	) -> None:
		kernel_rel = self._boot_relative_path(kernel_path, boot_root)
		initrd_rel = self._boot_relative_path(initrd_path, boot_root) if initrd_path else None

		lines = [
			'timeout: 5',
			'',
			'/Gentoo Linux',
			'    protocol: linux',
			f'    path: {path_root}:{kernel_rel}',
		]

		if initrd_rel:
			lines.append(f'    module_path: {path_root}:{initrd_rel}')
		if cmdline:
			lines.append(f'    cmdline: {cmdline}')

		config_path.parent.mkdir(parents=True, exist_ok=True)
		config_path.write_text('\n'.join(lines) + '\n')

	def _require_efi_partition(self) -> PartitionModification:
		efi_partition = self._get_efi_partition()
		if not efi_partition or not efi_partition.mountpoint:
			raise ValueError('Could not detect EFI system partition')
		return efi_partition

	def _target_mount_path(self, mountpoint: Path) -> Path:
		return self.target / mountpoint.relative_to('/')

	def _find_boot_artifacts(self) -> tuple[Path, Path | None, Path]:
		boot_partition = self._get_boot_partition()
		efi_partition = self._get_efi_partition()

		search_roots: list[Path] = []
		if boot_partition and boot_partition.mountpoint:
			search_roots.append(self._target_mount_path(boot_partition.mountpoint))

		search_roots.append(self.target / 'boot')

		if efi_partition and efi_partition.mountpoint:
			search_roots.append(self._target_mount_path(efi_partition.mountpoint))

		unique_roots: list[Path] = []
		seen_roots: set[str] = set()
		for root in search_roots:
			key = str(root)
			if key in seen_roots:
				continue
			seen_roots.add(key)
			unique_roots.append(root)

		for root in unique_roots:
			kernel = self._latest_from_patterns(
				root,
				['vmlinuz*', 'bzImage*', 'kernel-*', 'linux-*', 'gentoo*.efi', 'linux*.efi'],
				exclude_contains=['initramfs', 'initrd', 'system.map', 'config', '.old'],
			)
			if not kernel:
				continue

			initrd = self._latest_from_patterns(
				root,
				['initramfs*', 'initrd*'],
				exclude_contains=['fallback', '.old'],
			)
			return kernel, initrd, root

		raise RequirementError('Could not find kernel image in target boot paths. Install a kernel before adding a bootloader.')

	def _latest_from_patterns(
		self,
		base: Path,
		patterns: list[str],
		exclude_contains: list[str] | None = None,
	) -> Path | None:
		if not base.exists():
			return None

		candidates: list[Path] = []
		seen: set[str] = set()
		for pattern in patterns:
			for path in base.glob(pattern):
				if not path.is_file():
					continue
				key = str(path)
				if key in seen:
					continue
				seen.add(key)
				candidates.append(path)

		if not candidates:
			for pattern in patterns:
				for path in base.rglob(pattern):
					if not path.is_file():
						continue
					key = str(path)
					if key in seen:
						continue
					seen.add(key)
					candidates.append(path)

		if exclude_contains:
			filters = [token.lower() for token in exclude_contains]
			candidates = [path for path in candidates if not any(token in path.name.lower() for token in filters)]

		if not candidates:
			return None

		candidates.sort(key=lambda candidate: candidate.stat().st_mtime, reverse=True)
		return candidates[0]

	def _boot_relative_path(self, artifact: Path | None, boot_root: Path) -> str:
		if artifact is None:
			raise ValueError('Boot artifact path is required')

		try:
			rel_path = artifact.relative_to(boot_root)
			return '/' + str(rel_path).replace(os.sep, '/')
		except ValueError:
			return '/' + artifact.name

	def _kernel_cmdline(self) -> str:
		root = self._get_root()
		if root is None:
			raise ValueError(f'Could not detect root partition at mountpoint {self.target}')
		return ' '.join(self._get_kernel_params(root))

	def _upsert_space_kv(self, file_path: Path, key: str, value: str) -> None:
		lines: list[str] = []
		if file_path.exists():
			lines = file_path.read_text().splitlines()

		updated = False
		for idx, line in enumerate(lines):
			if line.strip().startswith(f'{key} '):
				lines[idx] = f'{key} {value}'
				updated = True
				break

		if not updated:
			lines.append(f'{key} {value}')

		file_path.write_text('\n'.join(lines) + '\n')

	def _emerge_packages(
		self,
		packages: str | list[str],
		strict: bool = False,
		oneshot: bool = False,
	) -> None:
		if isinstance(packages, str):
			packages = [packages]

		mapped = [self._map_package(pkg) for pkg in packages]
		atoms = [pkg for pkg in mapped if pkg]
		atoms = list(dict.fromkeys(atoms))

		if not atoms:
			return

		info(f'Installing packages (Portage): {atoms}')

		cmd = ['emerge', '--noreplace']
		if oneshot:
			cmd.append('--oneshot')
		cmd.extend(atoms)

		try:
			self.run_in_chroot(' '.join(shlex.quote(arg) for arg in cmd), peek_output=True)
		except SysCallError as err:
			if strict:
				raise RequirementError(f'Failed to install required Gentoo packages: {err}')

			warn(f'Bulk emerge failed, trying packages one-by-one: {err}')
			for atom in atoms:
				try:
					self.run_in_chroot(f'emerge --oneshot {shlex.quote(atom)}', peek_output=True)
				except SysCallError:
					warn(f'Skipping unavailable package: {atom}')

	def _map_package(self, package: str) -> str | None:
		if not package:
			return None
		if package.startswith('@') or '/' in package:
			return package
		return self._PACKAGE_MAP.get(package, package)

	def _resolve_stage3_url(self) -> str:
		if env_url := os.environ.get('GENTOO_STAGE3_URL'):
			return env_url

		if self._gentoo.stage3_url:
			return self._gentoo.stage3_url

		try:
			source = resolve_stage3_source(
				architecture=self._gentoo.architecture,
				init_system=self._gentoo.init_system.value,
				flavor=self._gentoo.stage3_flavor,
			)
			info(f'Resolved stage3 list: {source.list_url}')
			return source.tarball_url
		except Exception as err:
			if self._gentoo.init_system == GentooInitSystem.SYSTEMD:
				warn(f'No systemd stage3 resolved for selected architecture ({err}). Trying OpenRC stage3.')
				try:
					source = resolve_stage3_source(
						architecture=self._gentoo.architecture,
						init_system=GentooInitSystem.OPENRC.value,
						flavor=self._gentoo.stage3_flavor,
					)
					self._gentoo.init_system = GentooInitSystem.OPENRC
					info(f'Resolved OpenRC stage3 list: {source.list_url}')
					return source.tarball_url
				except Exception as openrc_err:
					warn(f'Automatic OpenRC stage3 discovery also failed: {openrc_err}')

			warn(f'Automatic stage3 discovery failed: {err}. Falling back to default amd64 stage3 list.')

		req = Request(_DEFAULT_STAGE3_SOURCE, headers={'User-Agent': 'gentooinstall'})
		with urlopen(req, timeout=20) as resp:
			data = resp.read().decode('utf-8', errors='replace')

		for line in data.splitlines():
			line = line.strip()
			if not line or line.startswith('#'):
				continue
			artifact = line.split()[0]
			if artifact.endswith(('.tar.xz', '.tar.gz', '.tar.bz2', '.tar.zst')):
				return urljoin(_DEFAULT_STAGE3_SOURCE, artifact)

		raise RequirementError(f'Unable to parse stage3 list from {_DEFAULT_STAGE3_SOURCE}')

	def _bootstrap_stage3(self) -> None:
		if (self.target / 'etc/gentoo-release').exists():
			return

		self.target.mkdir(parents=True, exist_ok=True)

		stage3_url = self._resolve_stage3_url()
		stage3_name = Path(stage3_url.split('?', 1)[0]).name
		stage3_tar = Path('/tmp') / stage3_name

		info(f'Downloading Gentoo stage3 from: {stage3_url}')
		if self._gentoo.use_wgetload:
			try:
				download_file(stage3_url, stage3_tar, retries=3)
			except Exception as err:
				raise RequirementError(f'Could not download stage3 tarball via wgetload helper: {err}')
		else:
			SysCommand(
				f'curl -L --fail --retry 3 -o {shlex.quote(str(stage3_tar))} {shlex.quote(stage3_url)}',
				peek_output=True,
			)

		info(f'Extracting stage3 into {self.target}')
		SysCommand(
			f'tar xpf {shlex.quote(str(stage3_tar))} --xattrs-include="*.*" --numeric-owner -C {shlex.quote(str(self.target))}',
			peek_output=True,
		)

		if Path('/etc/resolv.conf').exists():
			target_resolv = self.target / 'etc/resolv.conf'
			target_resolv.parent.mkdir(parents=True, exist_ok=True)
			shutil.copy2('/etc/resolv.conf', target_resolv)

		self._ensure_portage_setup()

	def _ensure_portage_setup(self) -> None:
		repos_conf_dir = self.target / 'etc/portage/repos.conf'
		repos_conf_dir.mkdir(parents=True, exist_ok=True)

		repos_conf = repos_conf_dir / 'gentoo.conf'
		if not repos_conf.exists():
			sample = self.target / 'usr/share/portage/config/repos.conf'
			if sample.exists():
				shutil.copy2(sample, repos_conf)
			else:
				repos_conf.write_text(
					'[gentoo]\n'
					'location = /var/db/repos/gentoo\n'
					'sync-type = rsync\n'
					'sync-uri = rsync://rsync.gentoo.org/gentoo-portage\n'
					'auto-sync = yes\n'
				)

		make_conf = self.target / 'etc/portage/make.conf'
		make_conf.parent.mkdir(parents=True, exist_ok=True)
		if not make_conf.exists():
			make_conf.write_text('')

	def _apply_make_conf_settings(self) -> None:
		make_conf = self.target / 'etc/portage/make.conf'
		make_conf.parent.mkdir(parents=True, exist_ok=True)
		if not make_conf.exists():
			make_conf.write_text('')

		cpu_count = max(os.cpu_count() or 1, 1)
		makeopts = self._gentoo.make_conf.makeopts or f'-j{cpu_count}'
		emerge_opts = self._gentoo.make_conf.emerge_default_opts or f'--jobs {cpu_count} --load-average {cpu_count}'

		entries: dict[str, str] = {
			'COMMON_FLAGS': self._gentoo.make_conf.common_flags,
			'CFLAGS': self._gentoo.make_conf.cflags,
			'CXXFLAGS': self._gentoo.make_conf.cxxflags,
			'FCFLAGS': self._gentoo.make_conf.fcflags,
			'FFLAGS': self._gentoo.make_conf.fflags,
			'MAKEOPTS': makeopts,
			'EMERGE_DEFAULT_OPTS': emerge_opts,
		}

		if self._gentoo.make_conf.chost:
			entries['CHOST'] = self._gentoo.make_conf.chost
		if self._gentoo.make_conf.rustflags:
			entries['RUSTFLAGS'] = self._gentoo.make_conf.rustflags
		if self._gentoo.make_conf.use:
			entries['USE'] = ' '.join(self._gentoo.make_conf.use)
		if self._gentoo.make_conf.features:
			entries['FEATURES'] = ' '.join(self._gentoo.make_conf.features)
		if self._gentoo.make_conf.accept_license:
			entries['ACCEPT_LICENSE'] = ' '.join(self._gentoo.make_conf.accept_license)
		if self._gentoo.make_conf.video_cards:
			entries['VIDEO_CARDS'] = ' '.join(self._gentoo.make_conf.video_cards)
		if self._gentoo.make_conf.grub_platforms:
			entries['GRUB_PLATFORMS'] = ' '.join(self._gentoo.make_conf.grub_platforms)

		entries.update(self._gentoo.make_conf.extra)

		for key, value in entries.items():
			self._upsert_kv(make_conf, key, self._quote_make_conf_value(value))

	def _set_selected_profile(self) -> None:
		if not self._gentoo.profile:
			return

		info(f'Setting Gentoo profile: {self._gentoo.profile}')
		self.run_in_chroot(f'eselect profile set {shlex.quote(self._gentoo.profile)}', peek_output=True)

	def _sync_portage(self) -> None:
		if self._gentoo.sync_mode == PortageSyncMode.NONE:
			info('Skipping Portage sync by configuration.')
			return

		if self._gentoo.sync_mode == PortageSyncMode.WEBRSYNC:
			try:
				self.run_in_chroot('emerge-webrsync', peek_output=True)
				return
			except SysCallError as err:
				warn(f'Portage webrsync failed, falling back to emerge --sync: {err}')

		try:
			self.run_in_chroot('emerge --sync', peek_output=True)
		except SysCallError as err:
			warn(f'Portage sync failed, continuing with bundled snapshot: {err}')

	def _setup_runtime_mounts(self) -> None:
		mounts = {
			Path('/proc'): self.target / 'proc',
			Path('/sys'): self.target / 'sys',
			Path('/dev'): self.target / 'dev',
			Path('/run'): self.target / 'run',
		}

		for source, target in mounts.items():
			target.mkdir(parents=True, exist_ok=True)
			if os.path.ismount(target):
				continue
			SysCommand(
				f'mount --rbind {shlex.quote(str(source))} {shlex.quote(str(target))}',
				peek_output=False,
			)
			SysCommand(
				f'mount --make-rslave {shlex.quote(str(target))}',
				peek_output=False,
			)
			self._runtime_mounts.append(target)

	def _teardown_runtime_mounts(self) -> None:
		for mountpoint in reversed(self._runtime_mounts):
			try:
				SysCommand(f'umount -R {shlex.quote(str(mountpoint))}')
			except SysCallError as err:
				debug(f'Could not unmount runtime mountpoint {mountpoint}: {err}')
		self._runtime_mounts = []

	def _target_architecture(self) -> str:
		return canonical_architecture(self._gentoo.architecture, machine=platform.machine())

	def _grub_efi_target(self) -> str:
		arch = self._target_architecture()
		mapping = {
			'amd64': 'x86_64-efi',
			'x86': 'i386-efi',
			'arm64': 'arm64-efi',
			'arm': 'arm-efi',
			'riscv': 'riscv64-efi',
			'loong': 'loongarch64-efi',
		}
		if arch in mapping:
			return mapping[arch]

		machine = platform.machine().lower()
		if machine in {'x86_64', 'amd64'}:
			return 'x86_64-efi'
		if machine in {'i386', 'i486', 'i586', 'i686', 'x86'}:
			return 'i386-efi'
		if machine in {'aarch64', 'arm64'}:
			return 'arm64-efi'
		if machine in {'armv7l', 'armv7', 'armv6l', 'arm'}:
			return 'arm-efi'
		if machine in {'riscv64'}:
			return 'riscv64-efi'
		if machine in {'loongarch64'}:
			return 'loongarch64-efi'

		raise RequirementError(f'No known GRUB UEFI target for architecture "{arch}" ({machine}).')

	def _grub_bios_target(self) -> str:
		arch = self._target_architecture()
		if arch in {'amd64', 'x86'}:
			return 'i386-pc'
		if arch in {'ppc', 'ppc64'}:
			return 'powerpc-ieee1275'

		machine = platform.machine().lower()
		if machine in {'x86_64', 'amd64', 'i386', 'i486', 'i586', 'i686', 'x86'}:
			return 'i386-pc'
		if machine.startswith(('ppc', 'powerpc')):
			return 'powerpc-ieee1275'

		raise RequirementError(f'No known legacy GRUB target for architecture "{arch}" ({machine}).')

	@staticmethod
	def _quote_make_conf_value(value: str) -> str:
		if value.startswith('"') and value.endswith('"'):
			return value
		return f'"{value}"'

	def _upsert_shell_assignment(self, file_path: Path, key: str, value: str) -> None:
		self._upsert_kv(file_path, key, self._quote_make_conf_value(value))

	def _upsert_kv(self, file_path: Path, key: str, value: str) -> None:
		lines: list[str] = []
		if file_path.exists():
			lines = file_path.read_text().splitlines()

		updated = False
		for idx, line in enumerate(lines):
			if line.strip().startswith(f'{key}='):
				lines[idx] = f'{key}={value}'
				updated = True
				break

		if not updated:
			lines.append(f'{key}={value}')

		file_path.write_text('\n'.join(lines) + '\n')

	def _verify_boot_part(self) -> None:
		# Gentoo has no strict minimum here, but we keep a warning-level size check for bootloader safety.
		boot_partition: PartitionModification | None = self._get_boot_partition()
		if not boot_partition or boot_partition.length is None:
			return
		min_size = Size(200, Unit.MiB, boot_partition.length.sector_size)
		if boot_partition.length < min_size:
			error(tr('Boot partition appears smaller than 200MiB. Bootloader installation may fail.'))
