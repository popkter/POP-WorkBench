import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtQml import QQmlEngine, QQmlExpression
from PySide6.QtTest import QTest

from test_floating_launcher import create_tool
from test_floating_launcher import launcher as launcher
from test_zio_theme import settled, visible_cards
from test_zio_theme import zio_app as zio_app


@pytest.mark.gui
@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("phase", ["entry", "settled", "return"])
@pytest.mark.parametrize("settings_visible", [False, True])
def test_zio_card_can_close_after_switching_to_decade(
    zio_app, qapp, qtbot, bulk, phase, settings_visible,
):
    window, controller, backend, settings, dock, warnings = zio_app
    tool = create_tool(backend, "Theme return", command="print('${message:Draft}')")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)

    def items(item):
        yield item
        for child in item.childItems():
            yield from items(child)

    def slot():
        return next((item for item in items(dock.contentItem())
                     if item.objectName() == "zioSlot_" + tool.id), None)

    qtbot.waitUntil(lambda: slot() is not None)
    row = slot()
    point = row.mapToItem(dock.contentItem(), row.boundingRect().center()).toPoint()
    QTest.mouseClick(dock, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    card = visible_cards(qapp)[tool.id]
    session = card.property("toolController")
    card.setProperty("parameterValues", {"message": "Unsaved draft"})
    backend.append_tool_console(tool.id, "Keep this output\n")
    if phase != "entry":
        qtbot.waitUntil(lambda: settled(card), timeout=7000)
    if phase == "return":
        QMetaObject.invokeMethod(card, "closeCardAnimated")
        qtbot.waitUntil(lambda: card.property("recycleAnimationRunning"))
    if settings_visible:
        window.setProperty("settingsSelected", True)
        window.show()
        controller.reconcile()
    settings.saveThemeMode("decade")
    qtbot.wait(100)
    if tool.id in visible_cards(qapp):
        assert card.property("toolController") is session
        assert card.property("parameterValues") == {"message": "Unsaved draft"}
        assert session.consoleText == "Keep this output\n"
    if bulk:
        controller.recallAllCards()
    elif tool.id in visible_cards(qapp):
        QMetaObject.invokeMethod(card, "closeCardAnimated")
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=7000)
    assert controller.openCardCount == 0
    assert not controller.returningCardIds
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("bulk", [False, True])
@pytest.mark.parametrize("interruption", ["destination", "animation"])
def test_interrupted_return_after_theme_switch_still_closes(
    zio_app, qapp, qtbot, bulk, interruption,
):
    _, controller, backend, settings, _, warnings = zio_app
    tool = create_tool(backend, "Interrupted return")
    backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    card = visible_cards(qapp)[tool.id]
    qtbot.waitUntil(lambda: settled(card), timeout=7000)
    if bulk:
        second_tool = create_tool(backend, "Next return")
        backend.recentToolDialogRequested.emit(second_tool.id)
        qtbot.waitUntil(lambda: second_tool.id in visible_cards(qapp), timeout=7000)
        qtbot.waitUntil(lambda: settled(visible_cards(qapp)[second_tool.id]), timeout=7000)
    settings.saveThemeMode("decade")
    qtbot.wait(100)
    if interruption == "destination":
        # Model a presentation callback that never arrives after its view retires.
        expression = QQmlExpression(QQmlEngine.contextForObject(card), card,
                                   "prepareReturn = function(id, callback) { return true }")
        expression.evaluate()
        assert not expression.hasError(), expression.error().toString()
    QMetaObject.invokeMethod(card, "closeCardAnimated")
    if interruption == "animation":
        qtbot.waitUntil(lambda: card.property("recycleAnimationRunning"))
        animation = card.findChild(QObject, "mechanicalCardRecycleAnimation")
        assert QMetaObject.invokeMethod(animation, "pause")
    else:
        assert card.property("returnPending")
    deadline = card.findChild(QObject, "cardCloseDeadline")
    assert deadline.property("running")
    qtbot.wait(2000)
    if bulk:
        controller.recallAllCards()
    else:
        QMetaObject.invokeMethod(card, "closeCardAnimated")
    # Repeated requests share the original close deadline, even in the recall queue.
    qtbot.waitUntil(lambda: tool.id not in visible_cards(qapp), timeout=3000)
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=3000)
    assert controller.openCardCount == 0
    assert not controller.returningCardIds
    assert not warnings, warnings
