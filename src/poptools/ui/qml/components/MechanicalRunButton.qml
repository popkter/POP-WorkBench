import QtQuick
import QtQuick.Shapes
import "../theme"

// Draw in window pixels, even though the surrounding card uses a 440 x 680
// design space. The entire module is a mouse/keyboard target in both themes.
Item {
    id: root
    property bool running: false
    property string statusText: ""
    property real uiScale: 1
    readonly property real nativeScale: Math.max(0.1, uiScale)
    readonly property bool hovered: pointer.containsMouse
    readonly property bool pressed: pointer.pressed
    readonly property color actionColor: running ? Theme.errorColor : Theme.primary
    readonly property color actionTextColor: running ? Theme.errorColor : Theme.primaryText
    readonly property string text: running ? "停止运行"
        : statusText === "执行成功" || statusText.indexOf("执行失败") === 0 ? "再次运行" : "运行脚本"
    readonly property string stateLabel: running ? "运行中"
        : statusText === "执行成功" ? "已完成"
        : statusText.indexOf("执行失败") === 0 ? "执行失败" : statusText || "就绪"
    signal clicked()
    implicitWidth: 408
    implicitHeight: Theme.mechanicalCardRunHeight / nativeScale
    opacity: enabled ? 1 : 0.45
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.description: stateLabel
    Accessible.onPressAction: if (enabled) clicked()
    Keys.onReturnPressed: function(event) {
        if (enabled && !event.isAutoRepeat) clicked();
    }
    Keys.onEnterPressed: function(event) {
        if (enabled && !event.isAutoRepeat) clicked();
    }
    Keys.onSpacePressed: function(event) {
        if (enabled && !event.isAutoRepeat) clicked();
    }

    Item {
        id: module
        width: root.width * root.nativeScale
        height: root.height * root.nativeScale
        scale: 1 / root.nativeScale
        transformOrigin: Item.TopLeft

        Rectangle {
            visible: Theme.zioMode
            anchors.fill: parent
            radius: 3
            border.width: root.pressed || root.activeFocus ? 2 : 1
            border.color: root.running ? root.actionColor
                : root.hovered || root.activeFocus ? Theme.primaryText : Theme.decadeCardActionBorder
            gradient: Gradient {
                GradientStop {
                    position: 0
                    color: root.running ? Theme.errorContainer
                        : root.hovered ? Theme.primaryContainerHover : Theme.decadeCardActionFill
                }
                GradientStop {
                    position: 1
                    color: root.running ? Theme.errorContainer : Theme.decadeCardSurface
                }
            }
        }
        Repeater {
            model: Theme.zioMode ? 2 : 0
            Item {
                required property int index
                x: index === 0 ? 5 : module.width - width - 5
                y: 5
                width: 14; height: 14
                Rectangle { width: parent.width; height: 2; color: root.actionColor }
                Rectangle {
                    x: parent.index === 0 ? 0 : parent.width - width
                    width: 2; height: parent.height; color: root.actionColor
                }
            }
        }
        Column {
            visible: Theme.zioMode
            x: 12
            width: Math.max(0, module.width / 2 - 55)
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Row {
                width: parent.width
                spacing: 5
                Rectangle {
                    width: 5; height: 5; radius: 2.5
                    anchors.verticalCenter: parent.verticalCenter
                    color: root.actionColor
                }
                Text {
                    width: parent.width - 10
                    text: root.stateLabel
                    color: Theme.textSecondary
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }
            Text {
                width: parent.width
                text: "ZI-O DRIVER"
                color: Theme.decadeCounterLeading
                font.family: "Consolas"
                font.pixelSize: 9
                font.letterSpacing: 0.7
                elide: Text.ElideRight
            }
        }
        Item {
            id: driveCore
            objectName: "zioRunDriveCore"
            visible: Theme.zioMode
            anchors.centerIn: parent
            width: 66; height: 66
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                color: Theme.decadeCardSurface
                border.width: 1
                border.color: Theme.outlineVariant
            }
            Rectangle {
                anchors.centerIn: parent
                width: 58; height: 58; radius: width / 2
                color: Theme.decadeCardSurface
                border.width: 1
                border.color: root.actionColor
                Repeater {
                    model: 30
                    Item {
                        required property int index
                        anchors.fill: parent
                        rotation: index * 12
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: 2
                            width: 1
                            height: parent.index % 5 === 0 ? 6 : 4
                            color: root.actionColor
                            opacity: 0.75
                        }
                    }
                }
            }
            Rectangle {
                anchors.centerIn: parent
                width: 42; height: 42; radius: width / 2
                border.width: root.pressed ? 2 : 1
                border.color: root.running ? Theme.errorColor : Theme.primaryText
                gradient: Gradient {
                    GradientStop {
                        position: 0
                        color: root.running ? Theme.errorContainer : Theme.primaryHover
                    }
                    GradientStop {
                        position: 1
                        color: root.running ? Theme.errorContainer : Theme.primary
                    }
                }
                MaterialIcon {
                    anchors.centerIn: parent
                    icon: root.running ? "stop" : "play_arrow"
                    iconSize: 23
                    color: root.running ? Theme.errorColor : Theme.primaryForeground
                }
            }
        }
        Column {
            visible: Theme.zioMode
            x: module.width / 2 + 43
            width: Math.max(0, module.width - x - 10)
            anchors.verticalCenter: parent.verticalCenter
            spacing: 4
            Text {
                width: parent.width
                text: root.text
                color: root.actionTextColor
                font.pixelSize: 14
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                text: root.running ? "STOP" : "EXECUTE"
                color: Theme.textSecondary
                font.family: "Consolas"
                font.pixelSize: 9
                font.letterSpacing: 0.8
            }
        }

        Shape {
            objectName: "decadeRunReader"
            visible: !Theme.zioMode
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: root.actionColor
                strokeWidth: root.pressed || root.activeFocus ? 2 : 1
                fillColor: root.running ? Theme.errorContainer
                    : root.hovered ? Theme.primaryContainer : Theme.decadeCardActionFill
                startX: 1; startY: 1
                PathLine { x: module.width - 11; y: 1 }
                PathLine { x: module.width - 1; y: 11 }
                PathLine { x: module.width - 1; y: module.height - 1 }
                PathLine { x: 11; y: module.height - 1 }
                PathLine { x: 1; y: module.height - 11 }
                PathLine { x: 1; y: 1 }
            }
        }
        Item {
            visible: !Theme.zioMode
            anchors.fill: parent
            Rectangle {
                x: 6; y: 4; width: parent.width - 18; height: 1
                color: root.actionColor; opacity: 0.55
            }
            Rectangle {
                x: 12; y: parent.height - 5; width: parent.width - 18; height: 1
                color: root.actionColor; opacity: 0.55
            }
            Row {
                x: 11
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Repeater {
                    model: 7
                    Rectangle {
                        required property int index
                        width: index % 3 === 0 ? 2 : 1
                        height: 27
                        color: root.actionColor
                    }
                }
            }
            Row {
                anchors.centerIn: parent
                spacing: 12
                MaterialIcon {
                    anchors.verticalCenter: parent.verticalCenter
                    icon: root.running ? "stop" : "play_arrow"
                    iconSize: 22
                    color: root.actionTextColor
                }
                Text {
                    text: root.text
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                    color: root.actionTextColor
                }
            }
            MaterialIcon {
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.verticalCenter: parent.verticalCenter
                icon: "keyboard_double_arrow_right"
                iconSize: 20
                color: root.actionColor
            }
        }
    }
    MouseArea {
        id: pointer
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
