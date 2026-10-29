pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "../theme"

// Shared search, filters and sorting. Only this boundary selects a presentation.
Item {
    id: root
    required property var controller
    required property var listModel
    property string searchQuery: ""
    property string kindFilter: "all"
    property bool quickLaunch: false
    property bool showSearchAndFilters: true
    onShowSearchAndFiltersChanged: if (!showSearchAndFilters) kindFilter = "all"
    property alias cardStore: sharedCards
    property bool continuousRecall: false
    property string keyboardToolId: ""
    readonly property bool deckMode: quickLaunch && Theme.decadeMode
    readonly property bool layoutSettling: collectionView ? collectionView.settling : false
    readonly property int pendingLaunchCount: collectionView ? collectionView.pendingLaunchCount : 0
    readonly property ScriptCollectionView collectionView: viewLoader.item as ScriptCollectionView
    readonly property bool menuOpen: sortButton.menuOpen
    readonly property int visibleCount: {
        const count = listModel.count;
        return listModel.countForKind(kindFilter);
    }
    signal searchEdited(string query)
    signal toolActivated(string toolId)
    signal toolActivatedAt(string toolId, rect sourceRect)

    // Keep face ownership outside the replaceable view, including while a card
    // is in a native execution window or the user switches themes.
    ScriptCardStore {
        id: sharedCards
    }
    function takeCardFace(id) {
        return sharedCards.borrow(id);
    }
    function cancelCardLaunch(id) {
        sharedCards.unlend(id);
    }
    function returnCardRect(id) {
        return collectionView ? collectionView.returnCardRect(id) : Qt.rect(0, 0, 0, 0);
    }
    function dockCardFace(id, face) {
        if (!face)
            return;
        sharedCards.accept(id, face);
        controller.setCardOpen(id, false);
        if (collectionView) collectionView.dockCardFace(id, face);
    }
    function activateTool(id, row) {
        collectionView.activateTool(id, row);
    }
    function cancelPendingLaunches() {
        if (collectionView) collectionView.cancelPendingLaunches();
    }
    function closeMenus() {
        sortButton.closeMenu();
    }
    function navigateTo(id) {
        keyboardToolId = id;
        if (quickLaunch)
            listModel.select(id);
        else
            toolActivated(id);
    }
    onKindFilterChanged: keyboardToolId = ""
    onSearchQueryChanged: keyboardToolId = ""
    Connections {
        target: root.listModel
        function onModelReset() {
            root.keyboardToolId = "";
        }
    }
    Component {
        id: standardView
        StandardScriptList {
            controller: root.controller
            listModel: root.listModel
            kindFilter: root.kindFilter
            keyboardToolId: root.keyboardToolId
            quickLaunch: root.quickLaunch
        }
    }
    Component {
        id: decadeView
        DecadeScriptDeck {
            controller: root.controller
            listModel: root.listModel
            kindFilter: root.kindFilter
            keyboardToolId: root.keyboardToolId
            cardStore: sharedCards
            continuousRecall: root.continuousRecall
        }
    }
    Connections {
        target: root.collectionView
        function onToolActivated(id) {
            root.toolActivated(id);
        }
        function onToolActivatedAt(id, rect) {
            root.toolActivatedAt(id, rect);
        }
        function onNavigationRequested(id) {
            root.navigateTo(id);
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space8
        AppTextField {
            id: searchField
            visible: root.showSearchAndFilters
            objectName: "scriptListSearch"
            FilePathDropArea {
                target: searchField
            }
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            leftPadding: 42
            baseRightPadding: 14
            clearButtonEnabled: root.quickLaunch
            placeholderText: "搜索名称、说明或标签..."
            text: root.searchQuery
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSupporting
            onTextChanged: if (root.searchQuery !== text)
                root.searchEdited(text)
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surfaceContainer
                border.color: searchField.activeFocus ? Theme.primary : "transparent"
                border.width: searchField.activeFocus ? 1 : 0
                MaterialIcon {
                    anchors.left: parent.left
                    anchors.leftMargin: 13
                    anchors.verticalCenter: parent.verticalCenter
                    icon: "search"
                    iconSize: 20
                    color: Theme.textSecondary
                }
            }
        }

        Flow {
            visible: root.showSearchAndFilters
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            spacing: 6
            Repeater {
                model: [
                    {
                        label: "全部",
                        value: "all"
                    },
                    {
                        label: "ADB",
                        value: "batch"
                    },
                    {
                        label: "PowerShell",
                        value: "powershell"
                    },
                    {
                        label: "Python",
                        value: "python"
                    },
                ]
                delegate: Rectangle {
                    id: filterChip
                    required property var modelData
                    width: filterChip.modelData.value === "powershell" ? 95 : filterChip.modelData.value === "python" ? 69 : filterChip.modelData.value === "all" ? 52 : 54
                    height: 28
                    radius: Theme.radiusSmall
                    color: root.kindFilter === modelData.value ? Theme.primaryContainer : Theme.surfaceContainerLow
                    border.color: root.kindFilter === modelData.value ? Theme.listSelected : Theme.outline
                    Text {
                        anchors.centerIn: parent
                        text: filterChip.modelData.label
                        color: root.kindFilter === filterChip.modelData.value ? Theme.primary : Theme.textSecondary
                        font.pixelSize: Theme.fontCaption
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.kindFilter = filterChip.modelData.value
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            Layout.topMargin: 3
            Row {
                visible: root.deckMode
                spacing: 2
                Repeater {
                    model: 7
                    Rectangle {
                        required property int index
                        width: index % 3 === 0 ? 3 : 1
                        height: 11
                        color: index % 3 === 0 ? Theme.primary : Theme.primaryText
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: 0
                text: root.collectionView ? root.collectionView.headingText : ""
                color: root.deckMode ? Theme.decadePackText : Theme.textSecondary
                font.pixelSize: Theme.fontCaption
                font.weight: root.deckMode ? Font.DemiBold : Font.Normal
            }
            ToolSortButton {
                id: sortButton
                cycleOnClick: root.quickLaunch
                Layout.preferredWidth: 28
                Layout.preferredHeight: 24
                glyphSize: 20
                controller: root.controller
                objectName: "scriptListSort"
                backgroundColor: "transparent"
                border.width: 0
                radius: root.deckMode ? Theme.radiusTiny : Theme.radiusSmall
            }
        }

        Loader {
            id: viewLoader
            Layout.fillWidth: true
            Layout.fillHeight: true
            sourceComponent: root.deckMode ? decadeView : standardView
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.deckMode ? 24 : footerRow.implicitHeight
            color: "transparent"
            radius: Theme.radiusTiny
            RowLayout {
                id: footerRow
                anchors.fill: parent
                Text {
                    Layout.fillWidth: true
                    text: root.visibleCount + (root.collectionView ? root.collectionView.countSuffix : "")
                    color: root.deckMode ? Theme.decadePackText : Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                }
                MaterialIcon {
                    visible: root.deckMode
                    icon: "north_west"; iconSize: 13; color: Theme.primaryText
                }
                Text {
                    text: root.collectionView ? root.collectionView.actionText : ""
                    color: root.deckMode ? Theme.primaryText : Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                }
            }
        }
    }
}
