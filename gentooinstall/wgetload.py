from __future__ import annotations

import argparse
import os
import platform
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

DISTFILES_RELEASES = 'https://distfiles.gentoo.org/releases'

_ARCH_ALIASES: dict[str, set[str]] = {
	'amd64': {'amd64', 'x86_64'},
	'arm64': {'arm64', 'aarch64'},
	'arm': {'arm', 'armv5tel', 'armv6l', 'armv7a', 'armv7l', 'armhf'},
	'x86': {'x86', 'i386', 'i486', 'i586', 'i686'},
	'ppc': {'ppc', 'powerpc'},
	'ppc64': {'ppc64', 'ppc64le', 'powerpc64', 'powerpc64le'},
	'hppa': {'hppa', 'parisc'},
	'mips': {'mips', 'mips64', 'mipsel', 'mips64el'},
	'riscv': {'riscv', 'riscv64'},
	's390': {'s390', 's390x'},
	'sparc': {'sparc', 'sparc64'},
	'alpha': {'alpha'},
	'loong': {'loong', 'loongarch64'},
}

_ARCH_RELEASE_ROOTS: dict[str, list[str]] = {
	'amd64': ['amd64'],
	'arm64': ['arm64'],
	'arm': ['arm'],
	'x86': ['x86'],
	'ppc': ['ppc'],
	'ppc64': ['ppc'],
	'hppa': ['hppa'],
	'mips': ['mips'],
	'riscv': ['riscv'],
	's390': ['s390'],
	'sparc': ['sparc'],
	'alpha': ['alpha'],
	'loong': ['loong'],
}

_ARCH_STAGE3_TOKENS: dict[str, list[str]] = {
	'amd64': ['amd64'],
	'arm64': ['arm64'],
	'arm': ['armv7a_hardfp', 'armv7a', 'arm'],
	'x86': ['i686', 'x86'],
	'ppc': ['ppc'],
	'ppc64': ['ppc64le', 'ppc64'],
	'hppa': ['hppa'],
	'mips': ['mips', 'mipsel', 'mips64'],
	'riscv': ['riscv64', 'riscv'],
	's390': ['s390x', 's390'],
	'sparc': ['sparc64', 'sparc'],
	'alpha': ['alpha'],
	'loong': ['loong', 'loongarch64'],
}

_ARCH_ARTIFACT_PREFERENCES: dict[str, list[str]] = {
	'amd64': ['amd64'],
	'arm64': ['arm64', 'aarch64'],
	'arm': ['armv7a_hardfp', 'armv7a', 'arm'],
	'x86': ['i686', 'x86'],
	'ppc': ['ppc'],
	'ppc64': ['ppc64le', 'ppc64'],
	'hppa': ['hppa'],
	'mips': ['mips64', 'mipsel', 'mips'],
	'riscv': ['rv64', 'riscv64', 'lp64'],
	's390': ['s390x'],
	'sparc': ['sparc64', 'sparc'],
	'alpha': ['alpha'],
	'loong': ['loong', 'loongarch64'],
}


@dataclass
class Stage3Source:
	architecture: str
	init_system: str
	list_url: str
	tarball_url: str
	flavor: str | None = None


def canonical_architecture(
	requested_arch: str | None = None,
	machine: str | None = None,
) -> str:
	if not requested_arch or requested_arch.lower() == 'auto':
		requested_arch = machine or platform.machine()

	normalized = requested_arch.strip().lower()
	for canonical, aliases in _ARCH_ALIASES.items():
		if normalized in aliases:
			return canonical

	return normalized


def _read_url(url: str, timeout: int = 20) -> str:
	req = Request(url, headers={'User-Agent': 'gentooinstall-wgetload'})
	with urlopen(req, timeout=timeout) as resp:
		return resp.read().decode('utf-8', errors='replace')


def _extract_stage3_tarball_url(
	list_url: str,
	content: str,
	architecture: str,
	init_system: str,
	flavor: str | None = None,
) -> str:
	candidates: list[str] = []
	for raw in content.splitlines():
		line = raw.strip()
		if not line or line.startswith('#'):
			continue

		artifact = line.split()[0]
		if artifact.endswith(('.tar.xz', '.tar.gz', '.tar.bz2', '.tar.zst')):
			if artifact.startswith(('http://', 'https://')):
				candidates.append(artifact)
			else:
				candidates.append(urljoin(list_url, artifact))

	if not candidates:
		raise RuntimeError(f'No stage3 archive entry found in {list_url}')

	preferences = _ARCH_ARTIFACT_PREFERENCES.get(architecture, [architecture])
	scored = []
	for candidate in candidates:
		lower = candidate.lower()
		score = 0

		if flavor and flavor.lower() in lower:
			score += 1000

		if f'-{init_system.lower()}-' in lower:
			score += 100

		for idx, pref in enumerate(preferences):
			if pref.lower() in lower:
				# earlier preferences are stronger
				score += 50 - idx
				break

		scored.append((score, candidate))

	scored.sort(reverse=True)
	return scored[0][1]


def _candidate_latest_files(
	architecture: str,
	init_system: str,
	flavor: str | None = None,
) -> list[str]:
	release_roots = _ARCH_RELEASE_ROOTS.get(architecture, [architecture])
	tokens = [flavor] if flavor else _ARCH_STAGE3_TOKENS.get(architecture, [architecture])

	candidates: list[str] = []
	for release_root in release_roots:
		base = f'{DISTFILES_RELEASES}/{release_root}/autobuilds/'
		for token in tokens:
			candidates.extend(
				[
					f'{base}latest-stage3-{token}-{init_system}.txt',
					f'{base}current-stage3-{token}-{init_system}/latest-stage3-{token}-{init_system}.txt',
					f'{base}latest-stage3-{token}.txt',
					f'{base}current-stage3-{token}/latest-stage3-{token}.txt',
				]
			)
	return list(dict.fromkeys(candidates))


def _scrape_latest_files(
	architecture: str,
	init_system: str,
	flavor: str | None = None,
	timeout: int = 20,
) -> list[str]:
	release_roots = _ARCH_RELEASE_ROOTS.get(architecture, [architecture])
	token_hints = [flavor] if flavor else _ARCH_STAGE3_TOKENS.get(architecture, [architecture])

	latest_files: list[str] = []
	for release_root in release_roots:
		base = f'{DISTFILES_RELEASES}/{release_root}/autobuilds/'
		try:
			index = _read_url(base, timeout=timeout)
		except Exception:
			continue

		matches = re.findall(r'href="([^"]*latest-stage3[^"]*\.txt)"', index)
		for rel in matches:
			abs_url = urljoin(base, rel)
			lower_url = abs_url.lower()

			if init_system.lower() not in lower_url:
				continue
			if not any(token.lower() in lower_url for token in token_hints):
				continue

			latest_files.append(abs_url)

		# Some release indexes only expose current-stage3-* dirs, not latest files.
		dir_matches = re.findall(r'href="(current-stage3[^"/]*/)"', index)
		for rel_dir in dir_matches:
			dir_url = urljoin(base, rel_dir)
			lower_dir = dir_url.lower()

			if init_system.lower() not in lower_dir:
				continue
			if not any(token.lower() in lower_dir for token in token_hints):
				continue

			try:
				dir_index = _read_url(dir_url, timeout=timeout)
			except Exception:
				continue

			dir_latest = re.findall(r'href="([^"]*latest-stage3[^"]*\.txt)"', dir_index)
			for latest in dir_latest:
				latest_files.append(urljoin(dir_url, latest))

	return list(dict.fromkeys(latest_files))


def resolve_stage3_source(
	architecture: str = 'auto',
	init_system: str = 'systemd',
	flavor: str | None = None,
	stage3_url: str | None = None,
	timeout: int = 20,
) -> Stage3Source:
	canonical_arch = canonical_architecture(architecture)
	normalized_init = init_system.strip().lower()

	if stage3_url:
		return Stage3Source(
			architecture=canonical_arch,
			init_system=normalized_init,
			list_url=stage3_url,
			tarball_url=stage3_url,
			flavor=flavor,
		)

	candidate_files = _candidate_latest_files(canonical_arch, normalized_init, flavor)
	candidate_files.extend(_scrape_latest_files(canonical_arch, normalized_init, flavor, timeout=timeout))

	errors: list[str] = []
	for latest_file in candidate_files:
		try:
			content = _read_url(latest_file, timeout=timeout)
			tarball = _extract_stage3_tarball_url(
				latest_file,
				content,
				architecture=canonical_arch,
				init_system=normalized_init,
				flavor=flavor,
			)
			return Stage3Source(
				architecture=canonical_arch,
				init_system=normalized_init,
				list_url=latest_file,
				tarball_url=tarball,
				flavor=flavor,
			)
		except Exception as err:
			errors.append(f'{latest_file}: {err}')
			continue

	raise RuntimeError(
		'Could not resolve a Gentoo stage3 tarball URL. '
		f'Architecture={canonical_arch}, init={normalized_init}, flavor={flavor}. '
		f'Tried {len(candidate_files)} sources.'
	)


def download_file(
	url: str,
	destination: Path,
	retries: int = 3,
) -> Path:
	destination.parent.mkdir(parents=True, exist_ok=True)

	if shutil.which('wget'):
		cmd = [
			'wget',
			'--tries',
			str(max(1, retries)),
			'--continue',
			'--output-document',
			str(destination),
			url,
		]
		subprocess.run(cmd, check=True)
		return destination

	if shutil.which('curl'):
		cmd = [
			'curl',
			'-L',
			'--fail',
			'--retry',
			str(max(1, retries)),
			'-o',
			str(destination),
			url,
		]
		subprocess.run(cmd, check=True)
		return destination

	req = Request(url, headers={'User-Agent': 'gentooinstall-wgetload'})
	with urlopen(req, timeout=60) as resp:
		destination.write_bytes(resp.read())

	return destination


def install_shell_alias(
	alias_name: str = 'gentooinstall',
	command: str = 'python3 -m gentooinstall',
	shell_rc: Path | None = None,
) -> bool:
	if shell_rc is None:
		shell_rc = Path.home() / '.zshrc'

	shell_rc.parent.mkdir(parents=True, exist_ok=True)
	if not shell_rc.exists():
		shell_rc.write_text('')

	alias_line = f'alias {alias_name}={shlex.quote(command)}'
	content = shell_rc.read_text()

	if alias_line in content:
		return False

	with shell_rc.open('a') as f:
		f.write(f'\n# gentooinstall helper alias\n{alias_line}\n')

	return True


def _cli() -> int:
	parser = argparse.ArgumentParser(description='Utilities to resolve/download Gentoo stage3 artifacts')
	sub = parser.add_subparsers(dest='cmd', required=True)

	resolve = sub.add_parser('resolve-stage3', help='Resolve stage3 tarball URL')
	resolve.add_argument('--arch', default='auto')
	resolve.add_argument('--init-system', default='systemd', choices=['systemd', 'openrc'])
	resolve.add_argument('--flavor', default=None)
	resolve.add_argument('--stage3-url', default=None)

	download = sub.add_parser('download', help='Download a URL using wget/curl fallback')
	download.add_argument('url')
	download.add_argument('destination')
	download.add_argument('--retries', type=int, default=3)

	alias = sub.add_parser('install-alias', help='Install shell alias for gentooinstall')
	alias.add_argument('--name', default='gentooinstall')
	alias.add_argument('--command', default='python3 -m gentooinstall')
	alias.add_argument('--shell-rc', default=str(Path.home() / '.zshrc'))

	args = parser.parse_args()

	if args.cmd == 'resolve-stage3':
		result = resolve_stage3_source(
			architecture=args.arch,
			init_system=args.init_system,
			flavor=args.flavor,
			stage3_url=args.stage3_url,
		)
		print(result.tarball_url)
		return 0

	if args.cmd == 'download':
		download_file(args.url, Path(args.destination), retries=args.retries)
		print(args.destination)
		return 0

	if args.cmd == 'install-alias':
		created = install_shell_alias(
			alias_name=args.name,
			command=args.command,
			shell_rc=Path(os.path.expanduser(args.shell_rc)),
		)
		print('Alias installed.' if created else 'Alias already present.')
		return 0

	return 1


if __name__ == '__main__':
	raise SystemExit(_cli())
