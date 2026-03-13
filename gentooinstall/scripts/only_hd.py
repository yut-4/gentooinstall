from pathlib import Path

from gentooinstall.lib.args import InstallerConfigHandler
from gentooinstall.lib.configuration import ConfigurationOutput
from gentooinstall.lib.disk.filesystem import FilesystemHandler
from gentooinstall.lib.disk.utils import disk_layouts
from gentooinstall.lib.gentoo_installer import GentooInstaller
from gentooinstall.lib.global_menu import GlobalMenu
from gentooinstall.lib.output import debug, error


def show_menu(installer_config_handler: InstallerConfigHandler) -> None:
	global_menu = GlobalMenu(installer_config_handler.config)
	global_menu.disable_all()

	global_menu.set_enabled('installer_language', True)
	global_menu.set_enabled('disk_config', True)
	global_menu.set_enabled('swap', True)
	global_menu.set_enabled('__config__', True)

	global_menu.run()


def perform_installation(installer_config_handler: InstallerConfigHandler) -> None:
	"""
	Performs the installation steps on a block device.
	Only requirement is that the block devices are
	formatted and setup prior to entering this function.
	"""
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
		# Mount all the drives to the desired mountpoint
		# This *can* be done outside of the installation, but the installer can deal with it.
		installation.mount_ordered_layout()

		# to generate a fstab directory holder. Avoids an error on exit and at the same time checks the procedure
		target = Path(f'{mountpoint}/etc/fstab')
		if not target.parent.exists():
			target.parent.mkdir(parents=True)

	# For support reasons, we'll log the disk layout post installation (crash or no crash)
	debug(f'Disk states after installing:\n{disk_layouts()}')


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
