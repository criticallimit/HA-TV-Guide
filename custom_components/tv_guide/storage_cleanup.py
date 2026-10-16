"""Remove obsolete, entry-owned copies without touching user selections."""
import logging
import shutil

_LOGGER = logging.getLogger(__name__)


def remove_legacy_storage(storage, *, native_settings):
    obsolete = [storage / 'reference']
    if native_settings:
        obsolete.append(storage / 'options.json')
    for path in obsolete:
        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
        except OSError:
            # Read-only leftovers must not prevent loading the current runtime.
            _LOGGER.warning('Could not remove obsolete TV Guide storage %s', path, exc_info=True)
