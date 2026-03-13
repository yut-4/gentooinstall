from functools import lru_cache

from gentooinstall.lib.output import debug


@lru_cache(maxsize=128)
def check_version_upgrade() -> str | None:
	debug('Skipping package-manager specific version check')
	return None
