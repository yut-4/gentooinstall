from gentooinstall.default_profiles.minimal import MinimalProfile
from gentooinstall.lib.args import InstallerConfigHandler
from gentooinstall.lib.configuration import ConfigurationOutput
from gentooinstall.lib.disk.disk_menu import DiskLayoutConfigurationMenu
from gentooinstall.lib.disk.filesystem import FilesystemHandler
from gentooinstall.lib.gentoo_installer import GentooInstaller
from gentooinstall.lib.models import Bootloader
from gentooinstall.lib.models.profile import ProfileConfiguration
from gentooinstall.lib.models.users import Password, User
from gentooinstall.lib.network.network_handler import NetworkHandler
from gentooinstall.lib.output import debug, error, info
from gentooinstall.lib.profile.profiles_handler import profile_handler


def perform_installation(installer_config_handler: InstallerConfigHandler) -> None:
	mountpoint = installer_config_handler.args.mountpoint
	config = installer_config_handler.config

	if not config.disk_config:
		error('No disk configuration provided')
		return

	disk_config = config.disk_config
	mountpoint = disk_config.mountpoint if disk_config.mountpoint else mountpoint

	with GentooInstaller(
		mountpoint,
		disk_config,
		kernels=config.kernels,
		silent=installer_config_handler.args.silent,
		gentoo_config=config.gentoo,
	) as installation:
		# Bootstrap base system, add a bootloader and configure
		# some other minor details as specified by this profile and user.
		installation.mount_ordered_layout()
		installation.minimal_installation()
		installation.set_hostname('minimal-gentoo')
		installation.add_bootloader(Bootloader.Grub)

		if config.network_config:
			NetworkHandler().install_network_config(
				config.network_config,
				installation,
				config.profile_config,
			)

		installation.add_additional_packages(['nano', 'wget', 'git'])

		profile_config = ProfileConfiguration(MinimalProfile())
		profile_handler.install_profile_config(installation, profile_config)

		user = User('devel', Password(plaintext='devel'), False)
		installation.create_users(user)

	# Once this is done, we output some useful information to the user.
	info('There is a new account in your installation after reboot:')
	info(' * devel (password: devel)')
	info('Set the root password manually from chroot if needed.')


def main(installer_config_handler: InstallerConfigHandler | None = None) -> None:
	if installer_config_handler is None:
		installer_config_handler = InstallerConfigHandler()

	disk_config = DiskLayoutConfigurationMenu(disk_layout_config=None).run()
	installer_config_handler.config.disk_config = disk_config

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

	perform_installation(installer_config_handler)


if __name__ == '__main__':
	main()
