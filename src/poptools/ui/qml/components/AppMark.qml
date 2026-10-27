import QtQuick

Item {
    implicitWidth: 40
    implicitHeight: 40
    Image {
        anchors.fill: parent
        source: Qt.resolvedUrl("../../../resources/icons/app-icon-ui.png")
        sourceSize: Qt.size(116, 116)
        fillMode: Image.PreserveAspectFit
        smooth: true
        mipmap: true
    }
    Accessible.name: "泡泡的工作台"
}
