import ctypes
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtGui import QWindow

from poptools.infrastructure.desktop_backdrop import (
    DWMSBT_NONE,
    DWMSBT_TRANSIENTWINDOW,
    DWMWA_SYSTEMBACKDROP_TYPE,
    SystemBackdropController,
    WindowsBackdrop,
    _Margins,
)


class NativeFunction:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


def fake_dwm(monkeypatch, *, attribute_error=0, extension_error=0):
    attributes, margins = [], []

    def attribute(hwnd, name, pointer, size):
        value = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_int)).contents.value
        attributes.append((name, value))
        return attribute_error if name == DWMWA_SYSTEMBACKDROP_TYPE else 0

    def extend(hwnd, pointer):
        value = ctypes.cast(pointer, ctypes.POINTER(_Margins)).contents
        margins.append((value.left, value.right, value.top, value.bottom))
        return extension_error

    dll = SimpleNamespace(DwmSetWindowAttribute=NativeFunction(attribute),
                          DwmExtendFrameIntoClientArea=NativeFunction(extend))
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: dll, raising=False)
    return WindowsBackdrop(), attributes, margins


def test_public_desktop_acrylic_api_and_opaque_restore(monkeypatch):
    api, attributes, margins = fake_dwm(monkeypatch)
    assert api.apply(123, True, True, True) == ""
    assert (DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW) in attributes
    assert margins == [(-1, -1, -1, -1)]
    assert api.apply(123, False, False, True) == ""
    assert attributes[-1] == (DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
    assert margins[-1] == (1, 1, 1, 1)
    assert api.apply(123, False, False, False) == ""
    assert margins[-1] == (0, 0, 0, 0)


def test_native_api_failure_is_reported_without_a_fake_backdrop(monkeypatch):
    api, _, margins = fake_dwm(monkeypatch, attribute_error=-2147024809)
    assert "80070057" in api.apply(123, True, False, False)
    assert not margins
    api, attributes, _ = fake_dwm(monkeypatch, extension_error=-2147467259)
    assert "80004005" in api.apply(123, True, False, False)
    assert attributes[-1] == (DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)


@pytest.mark.gui
def test_window_movement_needs_no_capture_or_refresh_work(qapp, monkeypatch):
    monkeypatch.setenv("QSG_RHI_BACKEND", "d3d11")
    monkeypatch.delenv("QT_QUICK_BACKEND", raising=False)
    calls = []
    controller = SystemBackdropController()
    controller._supported = True
    controller._native = SimpleNamespace(apply=lambda *args: calls.append(args) or "")
    window = QWindow()
    window.setProperty("customTitleBar", True)
    try:
        assert controller.configure(window, True, True) == ""
        qapp.processEvents()
        initial = len(calls)
        for x, y in ((40, 170), (40, 20), (-50, -40)):
            window.setPosition(x, y)
            qapp.processEvents()
        assert len(calls) == initial  # DWM handles position; Python does nothing.
        assert not controller.findChildren(QTimer)
        assert not hasattr(controller, "images")
        assert not hasattr(controller, "_captures")
        assert controller.configure(window, True, False) == ""
        assert calls[-1][1:3] == (True, False)
        assert controller.configure(window, False, False) == ""
        assert not controller._targets
        assert calls[-1][1] is False
        assert controller.configure(window, True, True) == ""
        assert len(controller._observed) == 1
        controller.release(window)
        assert not controller._targets
    finally:
        controller.shutdown()
        window.destroy()


@pytest.mark.gui
def test_unsupported_and_software_modes_report_solid_fallback(qapp, monkeypatch):
    controller = SystemBackdropController()
    window = QWindow()
    try:
        controller._supported = False
        assert "Windows 11" in controller.configure(window, True, False)
        assert not controller._targets
        controller._supported = True
        controller._native = SimpleNamespace(apply=lambda *args: "")
        monkeypatch.setenv("QT_QUICK_BACKEND", "software")
        assert "Direct3D" in controller.configure(window, True, False)
        assert not controller._targets
        assert controller.configure(window, False, False) == ""
    finally:
        controller.shutdown()
        window.destroy()
