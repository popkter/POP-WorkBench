"""Run through the actual frozen main/bootstrap/Main.qml in an isolated session.

Invoke with the release EXE --worker this_file --video clip.mp4 --output report.json.
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import sys
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

# The frozen entry script is not necessarily a second importable module.
# Reuse its actual globals from the --worker call, without loading repo source.
entry = next(frame.frame.f_globals for frame in inspect.stack()
             if frame.function == '_run_worker' and 'build_components' in frame.frame.f_globals)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--video', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
os.environ['POPTOOLS_DATA_DIR'] = str(args.output.parent / (args.output.stem + '-session'))
sys.argv = [sys.executable]
original_build = entry["build_components"]
state = {'frozen': bool(getattr(sys, 'frozen', False)), 'passed': False}


def build(*a, **kw):
    components = original_build(*a, **kw)
    components.settings_controller.markUserGuideSeen()
    backend = components.video_preview_controller
    timer = QTimer(QApplication.instance())
    started = time.monotonic()
    phase = [0]

    def tick():
        try:
            if time.monotonic() - started > 25:
                raise TimeoutError('Main window preview did not become ready')
            if backend.message:
                raise RuntimeError(backend.message)
            if phase[0] == 0:
                components.app_controller.navigate('preset')
                components.app_controller.selectTool('preset.video_preview')
                backend.addFiles([str(args.video.resolve())])
                phase[0] = 1
            elif phase[0] == 1 and backend.loaded and not backend.busy:
                backend.beginScrub()
                backend.scrub(backend.duration * .4)
                backend.endScrub(backend.duration * .6)
                phase[0] = 2
            elif phase[0] == 2 and not backend.busy:
                window = next(w for w in QGuiApplication.topLevelWindows()
                              if w.findChild(QObject, 'videoTimeline'))
                picture = window.findChild(QObject, 'videoPicture')
                if (picture is None or picture.property('progress') != 1
                        or not picture.property('visible') or not window.property('videoSelected')
                        or window.property('applicationOverlayVisible')):
                    return
                snapshot = args.output.with_suffix('.png')
                if not window.grabWindow().save(str(snapshot)):
                    raise RuntimeError('Main window screenshot failed')
                state.update(passed=True, position=backend.position,
                             duration=backend.duration, frame_size=[backend.images._live.width(),
                                                                    backend.images._live.height()],
                             controller_module=sys.modules[type(backend).__module__].__file__,
                             screenshot=str(snapshot.resolve()))
                timer.stop()
                QApplication.instance().quit()
        except Exception as error:
            state['error'] = str(error)
            timer.stop()
            QApplication.instance().exit(1)

    timer.timeout.connect(tick)
    timer.start(50)
    return components


entry["build_components"] = build
try:
    state['exit_code'] = entry['main']()
except Exception:
    state['error'] = traceback.format_exc()
finally:
    args.output.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
raise SystemExit(0 if state['passed'] else 1)
