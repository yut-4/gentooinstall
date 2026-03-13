import os
import time

from gentooinstall.lib.applications.application_handler import ApplicationHandler
from gentooinstall.lib.args import InstallerConfigHandler
from gentooinstall.lib.authentication.authentication_handler import AuthenticationHandler
from gentooinstall.lib.configuration import ConfigurationOutput
from gentooinstall.lib.disk.filesystem import FilesystemHandler
from gentooinstall.lib.disk.utils import disk_layouts
from gentooinstall.lib.gentoo_installer import GentooInstaller
from gentooinstall.lib.global_menu import GlobalMenu
from gentooinstall.lib.installer import accessibility_tools_in_use, run_custom_user_commands
from gentooinstall.lib.interactions.general_conf import PostInstallationAction, select_post_installation
from gentooinstall.lib.models import Bootloader
from gentooinstall.lib.models.device import DiskLayoutType, EncryptionType
from gentooinstall.lib.models.users import User
from gentooinstall.lib.network.network_handler import NetworkHandler
from gentooinstall.lib.output import debug, error, info
from gentooinstall.lib.packages.util import check_version_upgrade
from gentooinstall.lib.profile.profiles_handler import profile_handler
from gentooinstall.lib.translationhandler import tr


def show_menu(
	installer_config_handler: InstallerConfigHandler,
) -> None:
	upgrade = check_version_upgrade()
	title_text = 'Gentoo'

	if upgrade:
		text = tr('New version available') + f': {upgrade}'
		title_text += f' ({text})'

	global_menu = GlobalMenu(
		installer_config_handler.config,
		installer_config_handler.args.skip_boot,
		title=title_text,
	)

	if not installer_config_handler.args.advanced:
		global_menu.set_enabled('parallel_downloads', False)

	global_menu.run()


def perform_installation(
	installer_config_handler: InstallerConfigHandler,
	auth_handler: AuthenticationHandler,
	application_handler: ApplicationHandler,
) -> None:
	"""
	Performs the installation steps on a block device.
	Only requirement is that the block devices are
	formatted and setup prior to entering this function.
	"""
	start_time = time.monotonic()
	info('Starting installation...')

	mountpoint = installer_config_handler.args.mountpoint
	config = installer_config_handler.config

	if not config.disk_config:
		error('No disk configuration provided')
		return

	disk_config = config.disk_config
	locale_config = config.locale_config
	mountpoint = disk_config.mountpoint if disk_config.mountpoint else mountpoint

	with GentooInstaller(
		mountpoint,
		disk_config,
		kernels=config.kernels,
		silent=installer_config_handler.args.silent,
		gentoo_config=config.gentoo,
	) as installation:
		# Mount all the drives to the desired mountpoint
		if disk_config.config_type != DiskLayoutType.Pre_mount:
			installation.mount_ordered_layout()

		installation.sanity_check(
			installer_config_handler.args.offline,
			installer_config_handler.args.skip_ntp,
			installer_config_handler.args.skip_wkd,
		)

		if disk_config.config_type != DiskLayoutType.Pre_mount:
			if disk_config.disk_encryption and disk_config.disk_encryption.encryption_type != EncryptionType.NoEncryption:
				# generate encryption key files for the mounted luks devices
				installation.generate_key_files()

		installation.minimal_installation(
			optional_repositories=[],
			hostname=installer_config_handler.config.hostname,
			locale_config=locale_config,
		)

		if config.swap and config.swap.enabled:
			installation.setup_swap('zram', algo=config.swap.algorithm)

		if config.bootloader_config and config.bootloader_config.bootloader != Bootloader.NO_BOOTLOADER:
			installation.add_bootloader(config.bootloader_config.bootloader, config.bootloader_config.uki, config.bootloader_config.removable)

		if config.network_config:
			NetworkHandler().install_network_config(
				config.network_config,
				installation,
				config.profile_config,
			)

		users = None
		if config.auth_config:
			if config.auth_config.users:
				users = config.auth_config.users
				installation.create_users(config.auth_config.users)
				auth_handler.setup_auth(installation, config.auth_config, config.hostname)

		if app_config := config.app_config:
			application_handler.install_applications(installation, app_config)

		if profile_config := config.profile_config:
			profile_handler.install_profile_config(installation, profile_config)

		if config.packages and config.packages[0] != '':
			installation.add_additional_packages(config.packages)

		if timezone := config.timezone:
			installation.set_timezone(timezone)

		if config.ntp:
			installation.activate_time_synchronization()

		if accessibility_tools_in_use():
			installation.enable_espeakup()

		if config.auth_config and config.auth_config.root_enc_password:
			root_user = User('root', config.auth_config.root_enc_password, False)
			installation.set_user_password(root_user)

		if (profile_config := config.profile_config) and profile_config.profile:
			profile_config.profile.post_install(installation)

			if users:
				profile_config.profile.provision(installation, users)

		# If the user provided a list of services to be enabled, pass the list to the enable_service function.
		# Note that while it's called enable_service, it can actually take a list of services and iterate it.
		if services := config.services:
			installation.enable_service(services)

		if disk_config.has_default_btrfs_vols():
			btrfs_options = disk_config.btrfs_options
			snapshot_config = btrfs_options.snapshot_config if btrfs_options else None
			snapshot_type = snapshot_config.snapshot_type if snapshot_config else None
			if snapshot_type:
				bootloader = config.bootloader_config.bootloader if config.bootloader_config else None
				installation.setup_btrfs_snapshot(snapshot_type, bootloader)

		# If the user provided custom commands to be run post-installation, execute them now.
		if cc := config.custom_commands:
			run_custom_user_commands(cc, installation)

		installation.genfstab()

		debug(f'Disk states after installing:\n{disk_layouts()}')

		if not installer_config_handler.args.silent:
			elapsed_time = time.monotonic() - start_time
			action = select_post_installation(elapsed_time)

			match action:
				case PostInstallationAction.EXIT:
					pass
				case PostInstallationAction.REBOOT:
					os.system('reboot')
				case PostInstallationAction.CHROOT:
					try:
						installation.drop_to_shell()
					except Exception:
						pass


def main(installer_config_handler: InstallerConfigHandler | None = None) -> None:
	if installer_config_handler is None:
		installer_config_handler = InstallerConfigHandler()

	if not installer_config_handler.args.silent:
		show_menu(installer_config_handler)

	config = ConfigurationOutput(installer_config_handler.config)
	config.write_debug()
	config.save()

	if installer_config_handler.args.dry_run:
		return

	if not installer_config_handler.args.silent:
		aborted = False
		if not config.confirm_config():
			debug('Installation aborted')
			aborted = True

		if aborted:
			return main(installer_config_handler)

	if installer_config_handler.config.disk_config:
		fs_handler = FilesystemHandler(installer_config_handler.config.disk_config)
		fs_handler.perform_filesystem_operations()

	perform_installation(
		installer_config_handler,
		AuthenticationHandler(),
		ApplicationHandler(),
	)


if __name__ == '__main__':
	main()
