from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NotRequired, Self, TypedDict


class GentooInitSystem(Enum):
	SYSTEMD = 'systemd'
	OPENRC = 'openrc'

	@classmethod
	def from_arg(cls, value: str | None) -> Self:
		if not value:
			return cls.SYSTEMD
		normalized = value.strip().lower()
		for option in cls:
			if option.value == normalized:
				return option
		raise ValueError(f'Invalid Gentoo init system "{value}"')


class PortageSyncMode(Enum):
	SYNC = 'sync'
	WEBRSYNC = 'webrsync'
	NONE = 'none'

	@classmethod
	def from_arg(cls, value: str | None) -> Self:
		if not value:
			return cls.SYNC
		normalized = value.strip().lower()
		for option in cls:
			if option.value == normalized:
				return option
		raise ValueError(f'Invalid Gentoo sync mode "{value}"')


class _GentooMakeConfSerialization(TypedDict):
	common_flags: NotRequired[str]
	cflags: NotRequired[str]
	cxxflags: NotRequired[str]
	fcflags: NotRequired[str]
	fflags: NotRequired[str]
	rustflags: NotRequired[str]
	chost: NotRequired[str]
	makeopts: NotRequired[str]
	emerge_default_opts: NotRequired[str]
	use: NotRequired[list[str]]
	features: NotRequired[list[str]]
	accept_license: NotRequired[list[str]]
	video_cards: NotRequired[list[str]]
	grub_platforms: NotRequired[list[str]]
	extra: NotRequired[dict[str, str]]


@dataclass
class GentooMakeConf:
	common_flags: str = '-O2 -pipe'
	cflags: str = '${COMMON_FLAGS}'
	cxxflags: str = '${COMMON_FLAGS}'
	fcflags: str = '${COMMON_FLAGS}'
	fflags: str = '${COMMON_FLAGS}'
	rustflags: str | None = None
	chost: str | None = None
	makeopts: str | None = None
	emerge_default_opts: str | None = None
	use: list[str] = field(default_factory=list)
	features: list[str] = field(default_factory=list)
	accept_license: list[str] = field(default_factory=list)
	video_cards: list[str] = field(default_factory=list)
	grub_platforms: list[str] = field(default_factory=list)
	extra: dict[str, str] = field(default_factory=dict)

	def json(self) -> _GentooMakeConfSerialization:
		data: _GentooMakeConfSerialization = {
			'common_flags': self.common_flags,
			'cflags': self.cflags,
			'cxxflags': self.cxxflags,
			'fcflags': self.fcflags,
			'fflags': self.fflags,
		}

		if self.rustflags:
			data['rustflags'] = self.rustflags
		if self.chost:
			data['chost'] = self.chost
		if self.makeopts:
			data['makeopts'] = self.makeopts
		if self.emerge_default_opts:
			data['emerge_default_opts'] = self.emerge_default_opts
		if self.use:
			data['use'] = self.use
		if self.features:
			data['features'] = self.features
		if self.accept_license:
			data['accept_license'] = self.accept_license
		if self.video_cards:
			data['video_cards'] = self.video_cards
		if self.grub_platforms:
			data['grub_platforms'] = self.grub_platforms
		if self.extra:
			data['extra'] = self.extra

		return data

	@classmethod
	def parse_arg(cls, config: dict[str, Any] | None) -> Self:
		if not config:
			return cls()

		def _to_list(value: Any) -> list[str]:
			if isinstance(value, list):
				return [str(v) for v in value if str(v).strip()]
			if isinstance(value, str):
				return [v for v in value.split() if v.strip()]
			return []

		extra: dict[str, str] = {}
		if isinstance(config.get('extra'), dict):
			extra = {str(k): str(v) for k, v in config['extra'].items()}

		return cls(
			common_flags=str(config.get('common_flags', '-O2 -pipe')),
			cflags=str(config.get('cflags', '${COMMON_FLAGS}')),
			cxxflags=str(config.get('cxxflags', '${COMMON_FLAGS}')),
			fcflags=str(config.get('fcflags', '${COMMON_FLAGS}')),
			fflags=str(config.get('fflags', '${COMMON_FLAGS}')),
			rustflags=str(config['rustflags']) if config.get('rustflags') else None,
			chost=str(config['chost']) if config.get('chost') else None,
			makeopts=str(config['makeopts']) if config.get('makeopts') else None,
			emerge_default_opts=str(config['emerge_default_opts']) if config.get('emerge_default_opts') else None,
			use=_to_list(config.get('use')),
			features=_to_list(config.get('features')),
			accept_license=_to_list(config.get('accept_license')),
			video_cards=_to_list(config.get('video_cards')),
			grub_platforms=_to_list(config.get('grub_platforms')),
			extra=extra,
		)


class _GentooConfigurationSerialization(TypedDict):
	architecture: NotRequired[str]
	init_system: NotRequired[str]
	stage3_url: NotRequired[str]
	stage3_flavor: NotRequired[str]
	profile: NotRequired[str]
	sync_mode: NotRequired[str]
	use_wgetload: NotRequired[bool]
	make_conf: NotRequired[_GentooMakeConfSerialization]


@dataclass
class GentooConfiguration:
	architecture: str = 'auto'
	init_system: GentooInitSystem = GentooInitSystem.SYSTEMD
	stage3_url: str | None = None
	stage3_flavor: str | None = None
	profile: str | None = None
	sync_mode: PortageSyncMode = PortageSyncMode.SYNC
	use_wgetload: bool = True
	make_conf: GentooMakeConf = field(default_factory=GentooMakeConf)

	def json(self) -> _GentooConfigurationSerialization:
		data: _GentooConfigurationSerialization = {
			'architecture': self.architecture,
			'init_system': self.init_system.value,
			'sync_mode': self.sync_mode.value,
			'use_wgetload': self.use_wgetload,
			'make_conf': self.make_conf.json(),
		}

		if self.stage3_url:
			data['stage3_url'] = self.stage3_url
		if self.stage3_flavor:
			data['stage3_flavor'] = self.stage3_flavor
		if self.profile:
			data['profile'] = self.profile

		return data

	@classmethod
	def parse_arg(cls, config: dict[str, Any] | None) -> Self:
		if not config:
			return cls()

		return cls(
			architecture=str(config.get('architecture', 'auto')),
			init_system=GentooInitSystem.from_arg(config.get('init_system')),
			stage3_url=str(config['stage3_url']) if config.get('stage3_url') else None,
			stage3_flavor=str(config['stage3_flavor']) if config.get('stage3_flavor') else None,
			profile=str(config['profile']) if config.get('profile') else None,
			sync_mode=PortageSyncMode.from_arg(config.get('sync_mode')),
			use_wgetload=bool(config.get('use_wgetload', True)),
			make_conf=GentooMakeConf.parse_arg(config.get('make_conf')),
		)
