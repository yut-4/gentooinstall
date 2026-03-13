from __future__ import annotations

from typing import TYPE_CHECKING, override

from gentooinstall.default_profiles.profile import Profile, ProfileType

if TYPE_CHECKING:
	from gentooinstall.lib.installer import Installer


class PostgresqlProfile(Profile):
	def __init__(self) -> None:
		super().__init__(
			'Postgresql',
			ProfileType.ServerType,
		)

	@property
	@override
	def packages(self) -> list[str]:
		return ['postgresql']

	@property
	@override
	def services(self) -> list[str]:
		return ['postgresql']

	@override
	def post_install(self, install_session: Installer) -> None:
		install_session.run_in_chroot('initdb -D /var/lib/postgres/data', run_as='postgres')
