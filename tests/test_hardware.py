from pytest import MonkeyPatch

from gentooinstall.lib.exceptions import RequirementError
from gentooinstall.lib.hardware import SysInfo


def test_virtualization_unknown_when_binary_is_missing(monkeypatch: MonkeyPatch) -> None:
	monkeypatch.setattr('gentooinstall.lib.hardware.which', lambda _binary: None)

	assert SysInfo.virtualization() == 'unknown'
	assert SysInfo.is_vm() is False


def test_virtualization_unknown_when_command_raises_requirement_error(monkeypatch: MonkeyPatch) -> None:
	monkeypatch.setattr('gentooinstall.lib.hardware.which', lambda _binary: '/usr/bin/systemd-detect-virt')

	def _raise_requirement_error(_command: str) -> None:
		raise RequirementError('Binary systemd-detect-virt does not exist.')

	monkeypatch.setattr('gentooinstall.lib.hardware.SysCommand', _raise_requirement_error)

	assert SysInfo.virtualization() == 'unknown'
	assert SysInfo.is_vm() is False


def test_is_vm_true_when_virtualization_is_detected(monkeypatch: MonkeyPatch) -> None:
	monkeypatch.setattr('gentooinstall.lib.hardware.which', lambda _binary: '/usr/bin/systemd-detect-virt')

	class _CommandResult:
		def __str__(self) -> str:
			return 'kvm\n'

	monkeypatch.setattr('gentooinstall.lib.hardware.SysCommand', lambda _command: _CommandResult())

	assert SysInfo.virtualization() == 'kvm'
	assert SysInfo.is_vm() is True
