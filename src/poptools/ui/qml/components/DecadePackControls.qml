import QtQuick
import "../theme"

Column {
    required property var controller
    required property var cardList
    id: root
    width: 30
    spacing: 6
    PrimaryButton {
        id: pinKey
        objectName: Theme.decadeMode ? "floatingPinButton" : "decadeHiddenPin"
        width: 30; height: 30
        compact: true; iconName: "push_pin"
        showHoverTips: false
        text: root.controller.pinned ? "取消置顶" : "置顶卡包"
        color: "transparent"; border.width: 0; radius: 1
        foregroundColor: root.controller.pinned || hovered ? Theme.primaryText : "#A9B0BA"
        glyphSize: 16
        DecadePackControlFace {
            anchors.fill: parent; z: -1
            selected: root.controller.pinned
            hovered: pinKey.hovered; pressed: pinKey.pressed
        }
        Accessible.role: Accessible.CheckBox
        Accessible.name: text
        Accessible.checked: root.controller.pinned
        Accessible.onPressAction: root.controller.togglePinned()
        onClicked: root.controller.togglePinned()
    }
    PrimaryButton {
        id: recallKey
        objectName: Theme.decadeMode ? "floatingRecallAllButton" : "decadeHiddenRecall"
        width: 30; height: 30
        compact: true; iconName: "layers_clear"; text: "收回卡牌"
        showHoverTips: false
        enabled: root.controller.openCardCount > 0 || root.cardList.pendingLaunchCount > 0
        color: "transparent"; border.width: 0; radius: 1
        foregroundColor: hovered ? Theme.primaryText : "#A9B0BA"
        glyphSize: 16; disabledOpacity: 0.4
        DecadePackControlFace {
            anchors.fill: parent; z: -1
            hovered: recallKey.hovered; pressed: recallKey.pressed
        }
        function recall() {
            root.cardList.cancelPendingLaunches()
            root.controller.recallAllCards()
        }
        Accessible.role: Accessible.Button
        Accessible.name: text
        Accessible.onPressAction: recall()
        onClicked: recall()
    }
    PrimaryButton {
        id: collapseKey
        objectName: Theme.decadeMode ? "floatingCollapseButton" : "decadeHiddenCollapse"
        width: 30; height: 30
        compact: true; iconName: "remove"; text: "收起卡册"
        showHoverTips: false
        color: "transparent"; border.width: 0; radius: 1
        foregroundColor: hovered ? Theme.primaryText : "#A9B0BA"
        glyphSize: 16
        DecadePackControlFace {
            anchors.fill: parent; z: -1
            hovered: collapseKey.hovered; pressed: collapseKey.pressed
        }
        Accessible.role: Accessible.Button
        Accessible.name: text
        Accessible.onPressAction: root.controller.collapse()
        onClicked: root.controller.collapse()
    }
}
