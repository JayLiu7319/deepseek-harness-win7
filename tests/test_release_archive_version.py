"""Release qualification selects the archive produced by the canonical builder."""
from scripts.build_portable import VERSION, ZIP_OUTPUT
from scripts.verify_release import PORTABLE_ARCHIVE, ROOT


def test_release_gate_selects_the_current_builder_archive():
    assert (ROOT / PORTABLE_ARCHIVE).resolve() == (ROOT / ZIP_OUTPUT).resolve()
    assert (ROOT / PORTABLE_ARCHIVE).name == 'dsh-win7-portable-v' + VERSION + '.zip'
