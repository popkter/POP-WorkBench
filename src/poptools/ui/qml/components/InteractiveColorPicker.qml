import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

DesktopScrollView {
    id: picker
    clip: true
    padding: Theme.detailPanelPadding
    background: Rectangle {
        radius: Theme.radiusMedium
        color: Theme.surfaceContainerLow
    }

    required property var utilities
    property real selectedHue: 0.67
    property real selectedSaturation: 0.66
    property real selectedValue: 0.78
    property int selectedAlpha: 255
    property bool syncingColor: false
    property bool screenPicking: false

    function hexByte(value) {
        let hex = Math.round(Math.max(0, Math.min(255, value))).toString(16)
        return (hex.length === 1 ? "0" + hex : hex).toUpperCase()
    }

    function hueColor() {
        return Qt.hsva(selectedHue, 1, 1, 1)
    }

    function opaqueColor() {
        return Qt.hsva(selectedHue, selectedSaturation, selectedValue, 1)
    }

    function updateColorText() {
        const picked = opaqueColor()
        const rgb = hexByte(picked.r * 255) + hexByte(picked.g * 255)
                    + hexByte(picked.b * 255)
        syncingColor = true
        colorInput.text = selectedAlpha < 255 ? "#" + hexByte(selectedAlpha) + rgb
                                              : "#" + rgb
        syncingColor = false
    }

    function syncPickerFromText() {
        if (syncingColor || !colorInput.acceptableInput)
            return

        const value = colorInput.text
        const hasAlpha = value.length === 9
        const offset = hasAlpha ? 3 : 1
        const alpha = hasAlpha ? parseInt(value.slice(1, 3), 16) : 255
        const red = parseInt(value.slice(offset, offset + 2), 16) / 255
        const green = parseInt(value.slice(offset + 2, offset + 4), 16) / 255
        const blue = parseInt(value.slice(offset + 4, offset + 6), 16) / 255
        const maximum = Math.max(red, green, blue)
        const minimum = Math.min(red, green, blue)
        const delta = maximum - minimum
        let hue = selectedHue

        if (delta > 0) {
            if (maximum === red)
                hue = ((green - blue) / delta) % 6
            else if (maximum === green)
                hue = (blue - red) / delta + 2
            else
                hue = (red - green) / delta + 4
            hue = ((hue / 6) + 1) % 1
        }

        selectedHue = hue
        selectedSaturation = maximum === 0 ? 0 : delta / maximum
        selectedValue = maximum
        selectedAlpha = alpha
        alphaSlider.value = alpha
    }

    ColumnLayout {
        width: picker.availableWidth
        spacing: Theme.sectionSpacing

        Item { Layout.preferredHeight: 2 }

        Text {
            text: "颜色值"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontComponentTitle
            font.weight: Font.DemiBold
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Rectangle {
                Layout.preferredWidth: 48
                Layout.preferredHeight: 48
                radius: Theme.radiusSmall
                color: Theme.surface
                border.color: Theme.outline

                Canvas {
                    id: colorPreviewCanvas
                    anchors.fill: parent
                    anchors.margins: Theme.space4
                    onPaint: {
                        const ctx = getContext("2d")
                        const cornerRadius = Math.min(
                            Theme.radiusSmall,
                            width / 2,
                            height / 2
                        )
                        const tile = 7
                        ctx.clearRect(0, 0, width, height)

                        ctx.save()
                        ctx.beginPath()
                        ctx.moveTo(cornerRadius, 0)
                        ctx.lineTo(width - cornerRadius, 0)
                        ctx.quadraticCurveTo(width, 0, width, cornerRadius)
                        ctx.lineTo(width, height - cornerRadius)
                        ctx.quadraticCurveTo(width, height, width - cornerRadius, height)
                        ctx.lineTo(cornerRadius, height)
                        ctx.quadraticCurveTo(0, height, 0, height - cornerRadius)
                        ctx.lineTo(0, cornerRadius)
                        ctx.quadraticCurveTo(0, 0, cornerRadius, 0)
                        ctx.closePath()
                        ctx.clip()

                        for (let y = 0; y < height; y += tile) {
                            for (let x = 0; x < width; x += tile) {
                                const even = (Math.floor(x / tile) + Math.floor(y / tile)) % 2 === 0
                                ctx.fillStyle = even ? "#FFFFFF" : "#D7D3DC"
                                ctx.fillRect(x, y, tile, tile)
                            }
                        }

                        if (colorInput.acceptableInput) {
                            ctx.fillStyle = colorInput.text
                            ctx.fillRect(0, 0, width, height)
                        }
                        ctx.restore()
                    }
                }
            }

            AppTextField {
                id: colorInput
                objectName: "colorValueInput"
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                text: "#4543C7"
                font.pixelSize: Theme.fontComponentTitle
                validator: RegularExpressionValidator {
                    regularExpression: /#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})/
                }
                onTextChanged: {
                    picker.syncPickerFromText()
                    colorPreviewCanvas.requestPaint()
                }
                background: Rectangle {
                    radius: Theme.radiusMedium
                    color: Theme.surface
                    border.color: Theme.outline
                }
            }

            PrimaryButton {
                objectName: "systemColorPickerButton"
                implicitWidth: 130
                implicitHeight: 48
                text: picker.screenPicking ? "点击屏幕取色" : "系统取色"
                iconName: "colorize"
                tonal: true
                onClicked: {
                    picker.screenPicking = picker.utilities.startScreenColorPicking(
                        picker.Window.window)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 190
            radius: Theme.radiusSmall
            color: "transparent"

            Canvas {
                id: saturationValueCanvas
                anchors.fill: parent
                onPaint: {
                    const ctx = getContext("2d")
                    const cornerRadius = Math.min(
                        Theme.radiusSmall,
                        width / 2,
                        height / 2
                    )
                    ctx.clearRect(0, 0, width, height)

                    ctx.save()
                    ctx.beginPath()
                    ctx.moveTo(cornerRadius, 0)
                    ctx.lineTo(width - cornerRadius, 0)
                    ctx.quadraticCurveTo(width, 0, width, cornerRadius)
                    ctx.lineTo(width, height - cornerRadius)
                    ctx.quadraticCurveTo(
                        width,
                        height,
                        width - cornerRadius,
                        height
                    )
                    ctx.lineTo(cornerRadius, height)
                    ctx.quadraticCurveTo(0, height, 0, height - cornerRadius)
                    ctx.lineTo(0, cornerRadius)
                    ctx.quadraticCurveTo(0, 0, cornerRadius, 0)
                    ctx.closePath()
                    ctx.clip()

                    ctx.fillStyle = picker.hueColor()
                    ctx.fillRect(0, 0, width, height)

                    const white = ctx.createLinearGradient(0, 0, width, 0)
                    white.addColorStop(0, "#FFFFFF")
                    white.addColorStop(1, "rgba(255, 255, 255, 0)")
                    ctx.fillStyle = white
                    ctx.fillRect(0, 0, width, height)

                    const black = ctx.createLinearGradient(0, 0, 0, height)
                    black.addColorStop(0, "rgba(0, 0, 0, 0)")
                    black.addColorStop(1, "#000000")
                    ctx.fillStyle = black
                    ctx.fillRect(0, 0, width, height)
                    ctx.restore()
                }

                Connections {
                    target: picker
                    function onSelectedHueChanged() {
                        saturationValueCanvas.requestPaint()
                    }
                }
            }

            Rectangle {
                width: 18
                height: 18
                radius: Theme.radiusTiny
                x: picker.selectedSaturation * (parent.width - width)
                y: (1 - picker.selectedValue) * (parent.height - height)
                color: "transparent"
                border.width: 2
                border.color: "white"

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: Theme.space4
                    radius: width / 2
                    color: "transparent"
                    border.color: "#66000000"
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.CrossCursor

                function selectAt(mouse) {
                    picker.selectedSaturation = Math.max(0, Math.min(1, mouse.x / width))
                    picker.selectedValue = 1 - Math.max(0, Math.min(1, mouse.y / height))
                    picker.updateColorText()
                }

                onPressed: function(mouse) { selectAt(mouse) }
                onPositionChanged: function(mouse) {
                    if (pressed)
                        selectAt(mouse)
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 18
            radius: Theme.radiusTiny
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "#FF0000" }
                GradientStop { position: 0.1667; color: "#FFFF00" }
                GradientStop { position: 0.3333; color: "#00FF00" }
                GradientStop { position: 0.5; color: "#00FFFF" }
                GradientStop { position: 0.6667; color: "#0000FF" }
                GradientStop { position: 0.8333; color: "#FF00FF" }
                GradientStop { position: 1.0; color: "#FF0000" }
            }

            Rectangle {
                width: 14
                height: 26
                radius: Theme.radiusTiny
                x: picker.selectedHue * (parent.width - width)
                anchors.verticalCenter: parent.verticalCenter
                color: picker.hueColor()
                border.width: 2
                border.color: "white"
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor

                function selectAt(mouse) {
                    picker.selectedHue = Math.max(0, Math.min(1, mouse.x / width))
                    picker.updateColorText()
                }

                onPressed: function(mouse) { selectAt(mouse) }
                onPositionChanged: function(mouse) {
                    if (pressed)
                        selectAt(mouse)
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                text: "透明度"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontBody
            }

            AppSlider {
                id: alphaSlider
                Layout.fillWidth: true
                from: 0
                to: 255
                stepSize: 1
                value: 255
                onMoved: {
                    picker.selectedAlpha = Math.round(value)
                    picker.updateColorText()
                }
            }

            Text {
                Layout.preferredWidth: 34
                horizontalAlignment: Text.AlignRight
                text: picker.selectedAlpha
                color: Theme.textSecondary
                font.pixelSize: Theme.fontBody
            }
        }

        Text {
            text: colorInput.acceptableInput
                  ? "RGB " + Math.round(picker.opaqueColor().r * 255)
                    + ", " + Math.round(picker.opaqueColor().g * 255)
                    + ", " + Math.round(picker.opaqueColor().b * 255)
                  : "请输入 #RRGGBB 或 #AARRGGBB"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontBody
        }

        Item { Layout.preferredHeight: 2 }
    }

    Connections {
        target: picker.utilities

        function onScreenColorPicked(color) {
            if (!picker.screenPicking)
                return
            picker.screenPicking = false
            colorInput.text = color
            picker.syncPickerFromText()
            picker.updateColorText()
        }

        function onScreenColorPickingCancelled() {
            picker.screenPicking = false
        }
    }

    Connections {
        target: Theme

        function onRadiusSmallChanged() {
            colorPreviewCanvas.requestPaint()
            saturationValueCanvas.requestPaint()
        }
    }

    Component.onCompleted: syncPickerFromText()
}
