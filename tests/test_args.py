import os
from importlib.metadata import version
from pathlib import Path

from pytest import MonkeyPatch

from gentooinstall.default_profiles.profile import GreeterType
from gentooinstall.lib.args import InstallerConfig, InstallerConfigHandler, Arguments
from gentooinstall.lib.hardware import GfxDriver
from gentooinstall.lib.models.application import (
	ApplicationConfiguration,
	Audio,
	AudioConfiguration,
	BluetoothConfiguration,
	PrintServiceConfiguration,
	ZramConfiguration,
)
from gentooinstall.lib.models.authentication import AuthenticationConfiguration, U2FLoginConfiguration, U2FLoginMethod
from gentooinstall.lib.models.bootloader import Bootloader, BootloaderConfiguration
from gentooinstall.lib.models.device import DiskLayoutConfiguration, DiskLayoutType
from gentooinstall.lib.models.locale import LocaleConfiguration
from gentooinstall.lib.models.mirrors import CustomRepository, CustomServer, MirrorConfiguration, MirrorRegion, SignCheck, SignOption
from gentooinstall.lib.models.network import NetworkConfiguration, Nic, NicType
from gentooinstall.lib.models.packages import Repository
from gentooinstall.lib.models.profile import ProfileConfiguration
from gentooinstall.lib.models.users import Password, User
from gentooinstall.lib.profile.profiles_handler import profile_handler
from gentooinstall.lib.translationhandler import translation_handler


def test_default_args(monkeypatch: MonkeyPatch) -> None:
	monkeypatch.setattr('sys.argv', ['gentooinstall'])
	handler = InstallerConfigHandler()
	args = handler.args
	assert args == Arguments(
		config=None,
		config_url=None,
		creds=None,
		creds_url=None,
		creds_decryption_key=None,
		silent=False,
		dry_run=False,
		script=None,
		mountpoint=Path('/mnt'),
		skip_ntp=False,
		skip_wkd=False,
		skip_boot=False,
		debug=False,
		offline=False,
		no_pkg_lookups=False,
		plugin=None,
		skip_version_check=False,
		advanced=False,
	)


def test_correct_parsing_args(
	monkeypatch: MonkeyPatch,
	config_fixture: Path,
	creds_fixture: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--config',
			str(config_fixture),
			'--config-url',
			'https://example.com',
			'--creds',
			str(creds_fixture),
			'--script',
			'execution_script',
			'--mountpoint',
			'/tmp',
			'--skip-ntp',
			'--skip-wkd',
			'--skip-boot',
			'--debug',
			'--offline',
			'--no-pkg-lookups',
			'--plugin',
			'pytest_plugin.py',
			'--skip-version-check',
			'--advanced',
			'--dry-run',
			'--silent',
		],
	)

	handler = InstallerConfigHandler()
	args = handler.args

	assert args == Arguments(
		config=config_fixture,
		config_url='https://example.com',
		creds=creds_fixture,
		silent=True,
		dry_run=True,
		script='execution_script',
		mountpoint=Path('/tmp'),
		skip_ntp=True,
		skip_wkd=True,
		skip_boot=True,
		debug=True,
		offline=True,
		no_pkg_lookups=True,
		plugin='pytest_plugin.py',
		skip_version_check=True,
		advanced=True,
	)


def test_config_file_parsing(
	monkeypatch: MonkeyPatch,
	config_fixture: Path,
	creds_fixture: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--config',
			str(config_fixture),
			'--creds',
			str(creds_fixture),
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	# TODO: Use the real values from the test fixture instead of clearing out the entries
	installer_config.disk_config.device_modifications = []  # type: ignore[union-attr]

	assert installer_config == InstallerConfig(
		version=version('gentooinstall'),
		script='test_script',
		app_config=ApplicationConfiguration(
			bluetooth_config=BluetoothConfiguration(enabled=True),
			audio_config=AudioConfiguration(audio=Audio.PIPEWIRE),
			print_service_config=PrintServiceConfiguration(enabled=True),
		),
		auth_config=AuthenticationConfiguration(
			root_enc_password=Password(enc_password='password_hash'),
			users=[
				User(
					username='user_name',
					password=Password(enc_password='password_hash'),
					sudo=True,
					groups=['wheel'],
				),
			],
			u2f_config=U2FLoginConfiguration(
				u2f_login_method=U2FLoginMethod.Passwordless,
				passwordless_sudo=True,
			),
		),
		locale_config=LocaleConfiguration(
			kb_layout='us',
			sys_lang='en_US',
			sys_enc='UTF-8',
		),
		installer_language=translation_handler.get_language_by_abbr('en'),
		disk_config=DiskLayoutConfiguration(
			config_type=DiskLayoutType.Default,
			device_modifications=[],
			lvm_config=None,
			mountpoint=None,
		),
		profile_config=ProfileConfiguration(
			profile=profile_handler.parse_profile_config(
				{
					'custom_settings': {
						'Hyprland': {
							'seat_access': 'polkit',
						},
						'Sway': {
							'seat_access': 'seatd',
						},
					},
					'details': [
						'Sway',
						'Hyprland',
					],
					'main': 'Desktop',
				}
			),
			gfx_driver=GfxDriver.AllOpenSource,
			greeter=GreeterType.Lightdm,
		),
		mirror_config=MirrorConfiguration(
			mirror_regions=[
				MirrorRegion(
					name='Australia',
					urls=['https://distfiles.gentoo.org/'],
				),
			],
			custom_servers=[CustomServer('https://mirror.example.org/')],
			optional_repositories=[Repository.Testing],
			custom_repositories=[
				CustomRepository(
					name='myrepo',
					url='https://myrepo.example.org/',
					sign_check=SignCheck.Required,
					sign_option=SignOption.TrustAll,
				),
			],
		),
		network_config=NetworkConfiguration(
			type=NicType.MANUAL,
			nics=[
				Nic(
					iface='eno1',
					ip='192.168.1.15/24',
					dhcp=True,
					gateway='192.168.1.1',
					dns=[
						'192.168.1.1',
						'9.9.9.9',
					],
				),
			],
		),
		bootloader_config=BootloaderConfiguration(
			bootloader=Bootloader.Systemd,
			uki=False,
			removable=False,
		),
		hostname='gentoo',
		kernels=['linux-zen'],
		ntp=True,
		packages=['firefox'],
		parallel_downloads=66,
		swap=ZramConfiguration(enabled=False),
		timezone='UTC',
		services=['service_1', 'service_2'],
		custom_commands=["echo 'Hello, World!'"],
	)


def test_deprecated_mirror_config_parsing(
	monkeypatch: MonkeyPatch,
	deprecated_mirror_config: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--config',
			str(deprecated_mirror_config),
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	assert installer_config.mirror_config == MirrorConfiguration(
		mirror_regions=[
			MirrorRegion(
				name='Australia',
				urls=['https://distfiles.gentoo.org/'],
			),
		],
		custom_servers=[],
		optional_repositories=[Repository.Testing],
		custom_repositories=[
			CustomRepository(
				name='my_mirror',
				url='example.com',
				sign_check=SignCheck.Optional,
				sign_option=SignOption.TrustedOnly,
			),
		],
	)


def test_deprecated_creds_config_parsing(
	monkeypatch: MonkeyPatch,
	deprecated_creds_config: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--creds',
			str(deprecated_creds_config),
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	assert installer_config.auth_config is not None
	assert installer_config.auth_config.root_enc_password == Password(plaintext='rootPwd')

	assert installer_config.auth_config.users == [
		User(
			username='user_name',
			password=Password(plaintext='userPwd'),
			sudo=True,
			groups=['wheel'],
		),
	]


def test_deprecated_audio_config_parsing(
	monkeypatch: MonkeyPatch,
	deprecated_audio_config: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--config',
			str(deprecated_audio_config),
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	assert installer_config.app_config == ApplicationConfiguration(
		audio_config=AudioConfiguration(audio=Audio.PIPEWIRE),
	)


def test_encrypted_creds_with_arg(
	monkeypatch: MonkeyPatch,
	encrypted_creds_fixture: Path,
) -> None:
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--creds',
			str(encrypted_creds_fixture),
			'--creds-decryption-key',
			'master',
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	assert installer_config.auth_config is not None
	assert installer_config.auth_config.root_enc_password == Password(enc_password='$y$j9T$FWCInXmSsS.8KV4i7O50H.$Hb6/g.Sw1ry888iXgkVgc93YNuVk/Rw94knDKdPVQw7')
	assert installer_config.auth_config.users == [
		User(
			username='t',
			password=Password(enc_password='$y$j9T$3KxMigAEnjtzbjalhLewE.$gmuoQtc9RNY/PmO/GxHHYvkZNO86Eeftg1Oc7L.QSO/'),
			sudo=True,
			groups=[],
		),
	]


def test_encrypted_creds_with_env_var(
	monkeypatch: MonkeyPatch,
	encrypted_creds_fixture: Path,
) -> None:
	os.environ['GENTOOINSTALL_CREDS_DECRYPTION_KEY'] = 'master'
	monkeypatch.setattr(
		'sys.argv',
		[
			'gentooinstall',
			'--creds',
			str(encrypted_creds_fixture),
		],
	)

	handler = InstallerConfigHandler()
	installer_config = handler.config

	assert installer_config.auth_config is not None
	assert installer_config.auth_config.root_enc_password == Password(enc_password='$y$j9T$FWCInXmSsS.8KV4i7O50H.$Hb6/g.Sw1ry888iXgkVgc93YNuVk/Rw94knDKdPVQw7')
	assert installer_config.auth_config.users == [
		User(
			username='t',
			password=Password(enc_password='$y$j9T$3KxMigAEnjtzbjalhLewE.$gmuoQtc9RNY/PmO/GxHHYvkZNO86Eeftg1Oc7L.QSO/'),
			sudo=True,
			groups=[],
		),
	]
