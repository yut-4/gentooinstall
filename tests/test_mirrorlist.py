from pathlib import Path

from gentooinstall.lib.mirrors import MirrorListHandler


def test_mirrorlist_no_country(mirrorlist_no_country_fixture: Path) -> None:
	handler = MirrorListHandler(local_mirrorlist=mirrorlist_no_country_fixture)
	handler.load_local_mirrors()

	regions = handler.get_mirror_regions()

	assert len(regions) == 1
	assert regions[0].name == 'Local'
	assert regions[0].urls == [
		'https://distfiles.gentoo.org/',
		'https://mirror.dkm.cz/gentoo/',
	]


def test_mirrorlist_with_country(mirrorlist_with_country_fixture: Path) -> None:
	handler = MirrorListHandler(local_mirrorlist=mirrorlist_with_country_fixture)
	handler.load_local_mirrors()

	regions = handler.get_mirror_regions()

	assert len(regions) == 1
	assert regions[0].name == 'Worldwide'
	assert regions[0].urls == [
		'https://distfiles.gentoo.org/',
		'https://mirror.dkm.cz/gentoo/',
	]


def test_mirrorlist_multiple_countries(mirrorlist_multiple_countries_fixture: Path) -> None:
	handler = MirrorListHandler(local_mirrorlist=mirrorlist_multiple_countries_fixture)
	handler.load_local_mirrors()

	regions = handler.get_mirror_regions()

	assert len(regions) == 2
	assert regions[0].name == 'Worldwide'
	assert regions[0].urls == [
		'https://distfiles.gentoo.org/',
		'https://mirror.dkm.cz/gentoo/',
	]

	assert regions[1].name == 'Europe'
	assert regions[1].urls == [
		'https://mirror.netcologne.de/gentoo/',
	]
