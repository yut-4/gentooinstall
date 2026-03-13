"""Gentoo installer - guided, templates etc."""

import importlib
import os
import sys
import textwrap
import time
import traceback
from pathlib import Path

from gentooinstall.lib.args import InstallerConfigHandler
from gentooinstall.lib.command import SysCommand
from gentooinstall.lib.disk.utils import disk_layouts
from gentooinstall.lib.hardware import SysInfo
from gentooinstall.lib.network.wifi_handler import WifiHandler
from gentooinstall.lib.networking import ping
from gentooinstall.lib.output import debug, error, info, warn
from gentooinstall.lib.packages.util import check_version_upgrade
from gentooinstall.lib.translationhandler import tr
from gentooinstall.lib.utils.util import running_from_iso


def _log_sys_info() -> None:
	# Log various information about hardware before starting the installation. This might assist in troubleshooting
	debug(f'Hardware model detected: {SysInfo.sys_vendor()} {SysInfo.product_name()}; UEFI mode: {SysInfo.has_uefi()}')
	debug(f'Processor model detected: {SysInfo.cpu_model()}')
	debug(f'Memory statistics: {SysInfo.mem_available()} available out of {SysInfo.mem_total()} total installed')
	debug(f'Virtualization detected: {SysInfo.virtualization()}; is VM: {SysInfo.is_vm()}')
	debug(f'Graphics devices detected: {SysInfo._graphics_devices().keys()}')

	# For support reasons, we'll log the disk layout pre installation to match against post-installation layout
	debug(f'Disk states before installing:\n{disk_layouts()}')


def _check_online(wifi_handler: WifiHandler | None = None) -> bool:
	try:
		ping('1.1.1.1')
	except OSError as ex:
		if 'Network is unreachable' in str(ex):
			if wifi_handler is not None:
				success = wifi_handler.setup()
				if not success:
					return False

	return True


def _sync_portage_tree() -> bool:
	info('Syncing Gentoo Portage tree...')
	try:
		SysCommand('emerge --sync')
	except Exception as e:
		if 'Binary emerge does not exist' in str(e):
			warn('emerge command not found, skipping pre-flight Portage sync.')
			return True

		error('Failed to sync Gentoo Portage tree.')
		if 'could not resolve host' in str(e).lower():
			error('Most likely due to a missing network connection or DNS issue.')

		error('Run gentooinstall --debug and check /var/log/gentooinstall/install.log for details.')

		debug(f'Failed to sync Gentoo Portage tree: {e}')
		return False

	return True


def _list_scripts() -> str:
	lines = ['The following are viable --script options:']

	for file in (Path(__file__).parent / 'scripts').glob('*.py'):
		if file.stem != '__init__':
			lines.append(f'    {file.stem}')

	return '\n'.join(lines)


def run() -> int:
	"""
	This can either be run as the compiled and installed application: python setup.py install
	OR straight as a module: python -m gentooinstall
	In any case we will be attempting to load the provided script to be run from the scripts/ folder
	"""
	installer_config_handler = InstallerConfigHandler()

	if '--help' in sys.argv or '-h' in sys.argv:
		installer_config_handler.print_help()
		return 0

	script = installer_config_handler.get_script()

	if script == 'list':
		print(_list_scripts())
		return 0

	if os.getuid() != 0:
		print(tr('The installer requires root privileges to run. See --help for more.'))
		return 1

	_log_sys_info()

	if not installer_config_handler.args.offline:
		if not installer_config_handler.args.skip_wifi_check:
			wifi_handler = WifiHandler()
		else:
			wifi_handler = None

		if not _check_online(wifi_handler):
			return 0

		if not _sync_portage_tree():
			return 1

		if not installer_config_handler.args.skip_version_check:
			upgrade = check_version_upgrade()

			if upgrade:
				text = tr('New version available') + f': {upgrade}'
				info(text)
				time.sleep(3)

	if running_from_iso():
		debug('Running from ISO (Live Mode)...')
	else:
		debug('Running from Host (H2T Mode)...')

	mod_name = f'gentooinstall.scripts.{script}'
	# by loading the module we'll automatically run the script
	module = importlib.import_module(mod_name)
	module.main(installer_config_handler)

	return 0


def _error_message(exc: Exception) -> None:
	err = ''.join(traceback.format_exception(exc))
	error(err)

	text = textwrap.dedent(
		"""\
		The installer experienced the above error. If you think this is a bug, report it and include
		the log file "/var/log/gentooinstall/install.log".

		Hint: To extract the log from a live ISO
		curl -F 'file=@/var/log/gentooinstall/install.log' https://0x0.st
		"""
	)
	warn(text)


def main() -> int:
	rc = 0
	exc = None

	try:
		rc = run()
	except Exception as e:
		exc = e
	finally:
		if exc:
			_error_message(exc)
			rc = 1

	return rc


if __name__ == '__main__':
	sys.exit(main())
