from importlib.metadata import version


def get_version() -> str:
	try:
		return version('gentooinstall')
	except Exception:
		return 'gentooinstall version not found'
