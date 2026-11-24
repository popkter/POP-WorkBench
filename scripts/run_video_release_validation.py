"""Run a video benchmark through the release app's --worker entry point.

Only QtTest comes from the matching development installation. All application
modules and QML remain from the frozen release; report their paths as evidence.
Usage: APP.exe --worker scripts/run_video_release_validation.py benchmark VIDEO ...
"""
from __future__ import annotations

import runpy
import sys
import traceback
from pathlib import Path


def main():
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('This qualification runner must execute inside the release application')
    if len(sys.argv) < 2 or sys.argv[1] not in ('benchmark', 'stress'):
        raise ValueError('Expected benchmark or stress followed by its command-line arguments')
    root = Path(__file__).resolve().parents[1]
    driver = root / '.venv/Lib/site-packages/PySide6'
    import PySide6

    if sys.platform == 'win32':
        # Load just the test library. Adding the entire development DLL
        # directory can hide a broken Qt dependency in the actual release.
        import ctypes

        ctypes.WinDLL(str(driver / 'Qt6Test.dll'))
    PySide6.__path__.append(str(driver))
    import PySide6.QtTest

    import poptools.infrastructure.video_media
    import poptools.viewmodels.video_preview_controller

    frozen_root = Path(sys._MEIPASS).resolve()
    for module in (poptools.infrastructure.video_media,
                   poptools.viewmodels.video_preview_controller):
        if not Path(module.__file__).resolve().is_relative_to(frozen_root):
            raise RuntimeError(
                f'Qualification imported application source outside release: {module}')
    mode = sys.argv.pop(1)
    script = root / 'scripts' / f'{mode}_video_preview.py'
    sys.argv[0] = str(script)
    runpy.run_path(str(script), run_name='__main__')


if __name__ == '__main__':
    output = (Path(sys.argv[sys.argv.index('--output') + 1]) if '--output' in sys.argv
              else Path('build/video-release-validation.json'))
    output.parent.mkdir(parents=True, exist_ok=True)
    original_streams = sys.stdout, sys.stderr
    with output.with_suffix('.driver.log').open('w', encoding='utf-8') as log:
        sys.stdout = sys.stderr = log
        try:
            main()
        except Exception:
            traceback.print_exc()
            raise SystemExit(1) from None
        finally:
            sys.stdout, sys.stderr = original_streams
