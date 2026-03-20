import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Self
from urllib.request import Request, urlopen

from pydantic.dataclasses import dataclass as p_dataclass

from gentooinstall.lib.crypt import decrypt
from gentooinstall.lib.menu.util import get_password
from gentooinstall.lib.models.application import ApplicationConfiguration, ZramConfiguration
from gentooinstall.lib.models.authentication import AuthenticationConfiguration
from gentooinstall.lib.models.bootloader import Bootloader, BootloaderConfiguration
from gentooinstall.lib.models.device import DiskEncryption, DiskLayoutConfiguration
from gentooinstall.lib.models.gentoo import GentooConfiguration
from gentooinstall.lib.models.locale import LocaleConfiguration
from gentooinstall.lib.models.mirrors import MirrorConfiguration
from gentooinstall.lib.models.network import NetworkConfiguration
from gentooinstall.lib.models.packages import Repository
from gentooinstall.lib.models.profile import ProfileConfiguration
from gentooinstall.lib.models.users import Password, User, UserSerialization
from gentooinstall.lib.output import debug, error, logger, warn
from gentooinstall.lib.plugins import load_plugin
from gentooinstall.lib.translationhandler import Language, tr, translation_handler
from gentooinstall.lib.version import get_version


@p_dataclass
class Arguments:
	config: Path | None = None
	config_url: str | None = None
	creds: Path | None = None
	creds_url: str | None = None
	creds_decryption_key: str | None = None
	silent: bool = False
	dry_run: bool = False
	script: str | None = None
	mountpoint: Path = Path('/mnt')
	skip_ntp: bool = False
	skip_wkd: bool = False
	skip_boot: bool = False
	debug: bool = False
	offline: bool = False
	no_pkg_lookups: bool = False
	plugin: str | None = None
	skip_version_check: bool = False
	skip_wifi_check: bool = False
	advanced: bool = False
	verbose: bool = False


@dataclass
class InstallerConfig:
	_AUTO_DEVICE_VALUES: ClassVar[set[str]] = {'auto', '/dev/auto'}
	_PREFERRED_DEVICE_PATHS: ClassVar[tuple[str, ...]] = (
		'/dev/vda',
		'/dev/sda',
		'/dev/nvme0n1',
		'/dev/xvda',
		'/dev/hda',
		'/dev/mmcblk0',
	)

	version: str | None = None
	script: str | None = None
	locale_config: LocaleConfiguration | None = None
	installer_language: Language = field(default_factory=lambda: translation_handler.get_language_by_abbr('en'))
	disk_config: DiskLayoutConfiguration | None = None
	profile_config: ProfileConfiguration | None = None
	mirror_config: MirrorConfiguration | None = None
	network_config: NetworkConfiguration | None = None
	bootloader_config: BootloaderConfiguration | None = None
	app_config: ApplicationConfiguration | None = None
	auth_config: AuthenticationConfiguration | None = None
	swap: ZramConfiguration | None = None
	hostname: str = 'gentoo'
	kernels: list[str] = field(default_factory=lambda: ['gentoo-kernel-bin'])
	ntp: bool = True
	packages: list[str] = field(default_factory=list)
	parallel_downloads: int = 0
	timezone: str = 'UTC'
	services: list[str] = field(default_factory=list)
	custom_commands: list[str] = field(default_factory=list)
	gentoo: GentooConfiguration = field(default_factory=GentooConfiguration)

	@classmethod
	def _pick_auto_device(cls, devices: list[Any]) -> str | None:
		if not devices:
			return None

		if len(devices) == 1:
			return str(devices[0].device_info.path)

		available_by_path = {
			str(device.device_info.path): device
			for device in devices
		}

		for preferred_path in cls._PREFERRED_DEVICE_PATHS:
			if preferred_path in available_by_path:
				return preferred_path

		largest_device = max(devices, key=lambda device: device.device_info.total_size)
		return str(largest_device.device_info.path)

	@classmethod
	def _resolve_disk_config_devices(cls, disk_config: dict[str, Any]) -> None:
		from gentooinstall.lib.disk.device_handler import device_handler

		device_mods = disk_config.get('device_modifications', [])

		if not isinstance(device_mods, list):
			return

		candidate_devices = [
			device
			for device in device_handler.devices
			if not device.device_info.read_only and device.device_info.type != 'loop'
		]

		available_paths = {
			str(device.device_info.path)
			for device in candidate_devices
		}

		for mod in device_mods:
			if not isinstance(mod, dict):
				continue

			raw_device = str(mod.get('device', '')).strip()
			if not raw_device:
				continue

			is_explicit_auto = raw_device.lower() in cls._AUTO_DEVICE_VALUES
			configured_exists = raw_device in available_paths
			is_legacy_missing_sda = raw_device == '/dev/sda' and not configured_exists

			if configured_exists and not is_explicit_auto:
				continue

			if not is_explicit_auto and not is_legacy_missing_sda:
				continue

			resolved_device = cls._pick_auto_device(candidate_devices)
			if not resolved_device:
				warn(f'Disk auto-resolution failed for "{raw_device}" (no writable block devices found)')
				continue

			if resolved_device != raw_device:
				warn(f'Resolved install disk "{raw_device}" -> "{resolved_device}"')
				mod['device'] = resolved_device

	def unsafe_config(self) -> dict[str, Any]:
		config: dict[str, list[UserSerialization] | str | None] = {}

		if self.auth_config:
			if self.auth_config.users:
				config['users'] = [user.json() for user in self.auth_config.users]

			if self.auth_config.root_enc_password:
				config['root_enc_password'] = self.auth_config.root_enc_password.enc_password

		if self.disk_config:
			disk_encryption = self.disk_config.disk_encryption
			if disk_encryption and disk_encryption.encryption_password:
				config['encryption_password'] = disk_encryption.encryption_password.plaintext

		return config

	def safe_config(self) -> dict[str, Any]:
		config: Any = {
			'version': self.version,
			'script': self.script,
			'gentooinstall-language': self.installer_language.json(),
			'hostname': self.hostname,
			'kernels': self.kernels,
			'ntp': self.ntp,
			'packages': self.packages,
			'parallel_downloads': self.parallel_downloads,
			'swap': self.swap,
			'timezone': self.timezone,
			'services': self.services,
			'custom_commands': self.custom_commands,
			'gentoo': self.gentoo.json(),
			'bootloader_config': self.bootloader_config.json() if self.bootloader_config else None,
			'app_config': self.app_config.json() if self.app_config else None,
			'auth_config': self.auth_config.json() if self.auth_config else None,
		}

		if self.locale_config:
			config['locale_config'] = self.locale_config.json()

		if self.disk_config:
			config['disk_config'] = self.disk_config.json()

		if self.profile_config:
			config['profile_config'] = self.profile_config.json()

		if self.mirror_config:
			config['mirror_config'] = self.mirror_config.json()

		if self.network_config:
			config['network_config'] = self.network_config.json()

		return config

	@classmethod
	def from_config(cls, args_config: dict[str, Any], args: Arguments) -> Self:
		installer_config = cls()

		installer_config.locale_config = LocaleConfiguration.parse_arg(args_config)

		if script := args_config.get('script', None):
			installer_config.script = script

		if installer_lang := args_config.get('gentooinstall-language', None):
			installer_config.installer_language = translation_handler.get_language_by_name(installer_lang)

		if disk_config := args_config.get('disk_config', {}):
			cls._resolve_disk_config_devices(disk_config)

			enc_password = args_config.get('encryption_password', '')
			password = Password(plaintext=enc_password) if enc_password else None
			installer_config.disk_config = DiskLayoutConfiguration.parse_arg(disk_config, password)

			# DEPRECATED
			# backwards compatibility for main level disk_encryption entry
			disk_encryption: DiskEncryption | None = None

			if args_config.get('disk_encryption', None) is not None and installer_config.disk_config is not None:
				disk_encryption = DiskEncryption.parse_arg(
					installer_config.disk_config,
					args_config['disk_encryption'],
					Password(plaintext=args_config.get('encryption_password', '')),
				)

				if disk_encryption:
					installer_config.disk_config.disk_encryption = disk_encryption

		if profile_config := args_config.get('profile_config', None):
			installer_config.profile_config = ProfileConfiguration.parse_arg(profile_config)

		if mirror_config := args_config.get('mirror_config', None):
			backwards_compatible_repo = []
			if additional_repositories := args_config.get('additional-repositories', []):
				backwards_compatible_repo = [Repository(r) for r in additional_repositories]

			installer_config.mirror_config = MirrorConfiguration.parse_args(
				mirror_config,
				backwards_compatible_repo,
			)

		if net_config := args_config.get('network_config', None):
			installer_config.network_config = NetworkConfiguration.parse_arg(net_config)

		if bootloader_config_dict := args_config.get('bootloader_config', None):
			installer_config.bootloader_config = BootloaderConfiguration.parse_arg(bootloader_config_dict, args.skip_boot)
		# DEPRECATED: separate bootloader and uki fields (backward compatibility)
		elif bootloader_str := args_config.get('bootloader', None):
			bootloader = Bootloader.from_arg(bootloader_str, args.skip_boot)
			uki = args_config.get('uki', False)
			if uki and not bootloader.has_uki_support():
				uki = False
			installer_config.bootloader_config = BootloaderConfiguration(bootloader=bootloader, uki=uki, removable=True)

		# deprecated: backwards compatibility
		audio_config_args = args_config.get('audio_config', None)
		app_config_args = args_config.get('app_config', None)

		if audio_config_args is not None or app_config_args is not None:
			installer_config.app_config = ApplicationConfiguration.parse_arg(app_config_args, audio_config_args)

		if auth_config_args := args_config.get('auth_config', None):
			installer_config.auth_config = AuthenticationConfiguration.parse_arg(auth_config_args)

		if hostname := args_config.get('hostname', ''):
			installer_config.hostname = hostname

		if kernels := args_config.get('kernels', []):
			installer_config.kernels = kernels

		installer_config.ntp = args_config.get('ntp', True)

		if packages := args_config.get('packages', []):
			installer_config.packages = packages

		if parallel_downloads := args_config.get('parallel_downloads', 0):
			installer_config.parallel_downloads = parallel_downloads

		swap_arg = args_config.get('swap')
		if swap_arg is not None:
			installer_config.swap = ZramConfiguration.parse_arg(swap_arg)

		if timezone := args_config.get('timezone', 'UTC'):
			installer_config.timezone = timezone

		if services := args_config.get('services', []):
			installer_config.services = services

		if gentoo_config := args_config.get('gentoo', None):
			installer_config.gentoo = GentooConfiguration.parse_arg(gentoo_config)

		# DEPRECATED: backwards compatibility
		root_password = None
		if root_password := args_config.get('!root-password', None):
			root_password = Password(plaintext=root_password)

		if enc_password := args_config.get('root_enc_password', None):
			root_password = Password(enc_password=enc_password)

		if root_password is not None:
			if installer_config.auth_config is None:
				installer_config.auth_config = AuthenticationConfiguration()
			installer_config.auth_config.root_enc_password = root_password

		# DEPRECATED: backwards compatibility
		users: list[User] = []
		if args_users := args_config.get('!users', None):
			users = User.parse_arguments(args_users)

		if args_users := args_config.get('users', None):
			users = User.parse_arguments(args_users)

		if users:
			if installer_config.auth_config is None:
				installer_config.auth_config = AuthenticationConfiguration()
			installer_config.auth_config.users = users

		if custom_commands := args_config.get('custom_commands', []):
			installer_config.custom_commands = custom_commands

		return installer_config


class InstallerConfigHandler:
	def __init__(self) -> None:
		self._parser: ArgumentParser = self._define_arguments()
		args: Arguments = self._parse_args()
		self._args = args

		config = self._parse_config()

		try:
			self._config = InstallerConfig.from_config(config, args)
			self._config.version = get_version()
		except ValueError as err:
			warn(str(err))
			sys.exit(1)

	@property
	def config(self) -> InstallerConfig:
		return self._config

	@property
	def args(self) -> Arguments:
		return self._args

	def get_script(self) -> str:
		if script := self.args.script:
			return script

		if script := self.config.script:
			return script

		return 'guided'

	def print_help(self) -> None:
		self._parser.print_help()

	def _define_arguments(self) -> ArgumentParser:
		parser = ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
		parser.add_argument(
			'-v',
			'--version',
			action='version',
			default=False,
			version='%(prog)s ' + get_version(),
		)
		parser.add_argument(
			'--config',
			type=Path,
			nargs='?',
			default=None,
			help='JSON configuration file',
		)
		parser.add_argument(
			'--config-url',
			type=str,
			nargs='?',
			default=None,
			help='Url to a JSON configuration file',
		)
		parser.add_argument(
			'--creds',
			type=Path,
			nargs='?',
			default=None,
			help='JSON credentials configuration file',
		)
		parser.add_argument(
			'--creds-url',
			type=str,
			nargs='?',
			default=None,
			help='Url to a JSON credentials configuration file',
		)
		parser.add_argument(
			'--creds-decryption-key',
			type=str,
			nargs='?',
			default=None,
			help='Decryption key for credentials file',
		)
		parser.add_argument(
			'--silent',
			action='store_true',
			default=False,
			help='WARNING: Disables all prompts for input and confirmation. If no configuration is provided, this is ignored',
		)
		parser.add_argument(
			'--dry-run',
			'--dry_run',
			action='store_true',
			default=False,
			help='Generates a configuration file and then exits instead of performing an installation',
		)
		parser.add_argument(
			'--script',
			nargs='?',
			help='Script to run for installation',
			type=str,
		)
		parser.add_argument(
			'--mountpoint',
			type=Path,
			nargs='?',
			default=Path('/mnt'),
			help='Define an alternate mount point for installation',
		)
		parser.add_argument(
			'--skip-ntp',
			action='store_true',
			help='Disables NTP checks during installation',
			default=False,
		)
		parser.add_argument(
			'--skip-wkd',
			action='store_true',
			help='Disables distribution keyring synchronization checks.',
			default=False,
		)
		parser.add_argument(
			'--skip-boot',
			action='store_true',
			help='Disables installation of a boot loader (note: only use this when problems arise with the boot loader step).',
			default=False,
		)
		parser.add_argument(
			'--debug',
			action='store_true',
			default=False,
			help='Adds debug info into the log',
		)
		parser.add_argument(
			'--offline',
			action='store_true',
			default=False,
			help='Disabled online upstream services such as package search and key-ring auto update.',
		)
		parser.add_argument(
			'--no-pkg-lookups',
			action='store_true',
			default=False,
			help='Disabled package validation specifically prior to starting installation.',
		)
		parser.add_argument(
			'--plugin',
			nargs='?',
			type=str,
			default=None,
			help='File path to a plugin to load',
		)
		parser.add_argument(
			'--skip-version-check',
			action='store_true',
			default=False,
			help='Skip package version checks before running the installer',
		)
		parser.add_argument(
			'--skip-wifi-check',
			action='store_true',
			default=False,
			help='Skip wifi check when running gentooinstall',
		)
		parser.add_argument(
			'--advanced',
			action='store_true',
			default=False,
			help='Enabled advanced options',
		)
		parser.add_argument(
			'--verbose',
			action='store_true',
			default=False,
			help='Enabled verbose options',
		)

		return parser

	def _parse_args(self) -> Arguments:
		argparse_args = vars(self._parser.parse_args())
		args: Arguments = Arguments(**argparse_args)

		# amend the parameters (check internal consistency)
		# Installation can't be silent if config is not passed
		if args.config is None and args.config_url is None:
			args.silent = False

		if args.debug:
			warn(f'Warning: --debug mode will write certain credentials to {logger.path}!')

		if args.plugin:
			plugin_path = Path(args.plugin)
			load_plugin(plugin_path)

		if args.creds_decryption_key is None:
			if os.environ.get('GENTOOINSTALL_CREDS_DECRYPTION_KEY'):
				args.creds_decryption_key = os.environ.get('GENTOOINSTALL_CREDS_DECRYPTION_KEY')

		return args

	def _parse_config(self) -> dict[str, Any]:
		config: dict[str, Any] = {}
		config_data: str | None = None
		creds_data: str | None = None

		if self._args.config is not None:
			config_data = self._read_file(self._args.config)
		elif self._args.config_url is not None:
			config_data = self._fetch_from_url(self._args.config_url)

		if config_data is not None:
			config.update(json.loads(config_data))

		if self._args.creds is not None:
			creds_data = self._read_file(self._args.creds)
		elif self._args.creds_url is not None:
			creds_data = self._fetch_from_url(self._args.creds_url)

		if creds_data is not None:
			json_data = self._process_creds_data(creds_data)
			if json_data is not None:
				config.update(json_data)

		config = self._cleanup_config(config)

		return config

	def _process_creds_data(self, creds_data: str) -> dict[str, Any] | None:
		if creds_data.startswith('$'):  # encrypted data
			if self._args.creds_decryption_key is not None:
				try:
					creds_data = decrypt(creds_data, self._args.creds_decryption_key)
					return json.loads(creds_data)
				except ValueError as err:
					if 'Invalid password' in str(err):
						error(tr('Incorrect credentials file decryption password'))
						sys.exit(1)
					else:
						debug(f'Error decrypting credentials file: {err}')
						raise err from err
			else:
				incorrect_password = False
				header = tr('Enter credentials file decryption password')

				while True:
					prompt = f'{header}\n\n' + tr('Incorrect password') if incorrect_password else ''

					decryption_pwd = get_password(
						header=prompt,
						allow_skip=False,
						skip_confirmation=True,
					)

					if not decryption_pwd:
						return None

					try:
						creds_data = decrypt(creds_data, decryption_pwd.plaintext)
						break
					except ValueError as err:
						if 'Invalid password' in str(err):
							debug('Incorrect credentials file decryption password')
							incorrect_password = True
						else:
							debug(f'Error decrypting credentials file: {err}')
							raise err from err

		return json.loads(creds_data)

	def _fetch_from_url(self, url: str) -> str:
		if urllib.parse.urlparse(url).scheme:
			try:
				req = Request(url, headers={'User-Agent': 'gentooinstall'})
				with urlopen(req) as resp:
					return resp.read().decode('utf-8')
			except urllib.error.HTTPError as err:
				error(f'Could not fetch JSON from {url}: {err}')
		else:
			error('Not a valid url')

		sys.exit(1)

	def _read_file(self, path: Path) -> str:
		if not path.exists():
			error(f'Could not find file {path}')
			sys.exit(1)

		return path.read_text()

	def _cleanup_config(self, config: Namespace | dict[str, Any]) -> dict[str, Any]:
		clean_args = {}
		for key, val in config.items():
			if isinstance(val, dict):
				val = self._cleanup_config(val)

			if val is not None:
				clean_args[key] = val

		return clean_args
