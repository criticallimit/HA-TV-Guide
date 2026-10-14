"""Run inherited provider regressions against the native-owned reference engine."""
import atexit
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'tv_guide'
PACKAGE = '_tvguide_inherited_regressions'
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE] = package
if os.environ.get('TVG_TEST_TMP'):
    tempfile.tempdir = os.environ['TVG_TEST_TMP']
spec = importlib.util.spec_from_file_location(PACKAGE + '.original_runtime', ROOT / 'original_runtime.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
folder = tempfile.TemporaryDirectory()
backend = module.OriginalRuntime(Path(folder.name)/'reference', {'country':'de'}, {'language':'de'}, lambda:None)
app = backend.runtime
atexit.register(folder.cleanup)
atexit.register(backend.close)
