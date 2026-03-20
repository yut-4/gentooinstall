from gentooinstall.lib.args import InstallerConfigHandler
from gentooinstall.lib.configuration import ConfigurationOutput
from gentooinstall.lib.disk.filesystem import FilesystemHandler
from gentooinstall.lib.gentoo_installer import GentooInstaller
from gentooinstall.lib.global_menu import GlobalMenu
from gentooinstall.lib.models.device import DiskLayoutType
from gentooinstall.lib.output import debug, error, info


def show_menu(installer_config_handler: InstallerConfigHandler) -> None:
	global_menu = GlobalMenu(installer_config_handler.config)
	global_menu.disable_all()

	global_menu.set_enabled('installer_language', True)
	global_menu.set_enabled('disk_config', True)
	global_menu.set_enabled('__config__', True)

	global_menu.run()


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
		if disk_config.config_type != DiskLayoutType.Pre_mount:
			installation.mount_ordered_layout()

		installation.sanity_check(
			installer_config_handler.args.offline,
			installer_config_handler.args.skip_ntp,
			installer_config_handler.args.skip_wkd,
		)
		installation.prepare_handbook_chroot()
		installation.genfstab()

		info('Gentoo handbook chroot environment is ready.')
		info('Type "exit" to return to the installer shell when done.')
		installation.drop_to_handbook_shell()

	debug('Returned from handbook chroot shell')


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

	perform_installation(installer_config_handler)


if __name__ == '__main__':
	main()
