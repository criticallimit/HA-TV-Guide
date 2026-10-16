"""Import pure native components without loading Home Assistant's integration entry."""
import importlib
from pathlib import Path
import sys
import types

PACKAGE = '_tvguide_native_components'
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(Path(__file__).resolve().parents[1]/'custom_components/tv_guide')]
    sys.modules[PACKAGE] = package


def module(name):
    return importlib.import_module(PACKAGE+'.'+name)
