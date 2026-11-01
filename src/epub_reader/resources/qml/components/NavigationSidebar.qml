import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: panel
    objectName: "navigationSidebar"
    signal closeRequested()
    signal entryActivated()
    color: Theme.surface
    clip: true
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
    ColumnLayout {
        anchors { fill: parent; margins: 16 }
        spacing: 14
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: qsTranslate("Epubify", "BOOK NAVIGATION")
                color: Theme.secondary
                font { pixelSize: 10; letterSpacing: 1.6; weight: Font.DemiBold }
                Layout.fillWidth: true
            }
            ToolButton {
                text: "×"
                font.pixelSize: 22
                palette.buttonText: Theme.secondary
                implicitWidth: Theme.touchTarget
                implicitHeight: Theme.touchTarget
                Accessible.name: qsTranslate("Epubify", "Close book navigation")
                onClicked: panel.closeRequested()
                background: Rectangle { radius: 6; color: parent.hovered ? Theme.elevated : "transparent" }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: 4
            Repeater {
                model: ["contents", "figures"]
                delegate: Button {
                    required property string modelData
                    objectName: modelData + "Tab"
                    Layout.fillWidth: true
                    implicitHeight: Theme.touchTarget
                    checked: reader.navigationSection === modelData
                    text: modelData === "contents" ? qsTranslate("Epubify", "Contents · %1").arg(reader.contentsCount)
                          : reader.figuresLoading ? qsTranslate("Epubify", "Figures…") : qsTranslate("Epubify", "Figures · %1").arg(reader.figureCount)
                    font { pixelSize: 12; weight: checked ? Font.DemiBold : Font.Normal }
                    palette.buttonText: checked ? Theme.accent : Theme.secondary
                    Accessible.name: modelData === "contents" ? qsTranslate("Epubify", "Table of contents") : qsTranslate("Epubify", "List of figures")
                    onClicked: reader.setNavigationSection(modelData)
                    background: Rectangle {
                        radius: 8
                        color: parent.checked ? Theme.elevated : "transparent"
                        border.color: parent.activeFocus ? Theme.accent : "transparent"
                    }
                }
            }
        }
        TextField {
            id: search
            objectName: "navigationSearch"
            Layout.fillWidth: true
            implicitHeight: Theme.touchTarget
            text: reader.navigationQuery
            onTextEdited: reader.setNavigationQuery(text)
            placeholderText: reader.navigationSection === "contents" ? qsTranslate("Epubify", "Find a chapter or section…") : qsTranslate("Epubify", "Find a figure…")
            placeholderTextColor: Theme.secondary
            color: Theme.text
            font.pixelSize: 12
            selectByMouse: true
            Accessible.name: qsTranslate("Epubify", "Filter book navigation")
            leftPadding: 12
            background: Rectangle {
                radius: 8
                color: Theme.background
                border.color: search.activeFocus ? Theme.accent : Theme.border
            }
        }
        ListView {
            id: outline
            signal entryActivated()
            onEntryActivated: panel.entryActivated()
            objectName: "navigationList"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: reader.navigationRows
            spacing: 3
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            delegate: ItemDelegate {
                id: node
                required property var modelData
                objectName: "navigation-entry-" + modelData.nodeId
                width: ListView.view.width
                leftPadding: 6 + Math.min(modelData.depth, 7) * 18
                rightPadding: 8
                topPadding: 10
                bottomPadding: 10
                onClicked: {
                    if (modelData.href) {
                        // Navigating resets the model and can destroy this delegate.
                        const view = node.ListView.view
                        reader.navigate(modelData.href)
                        view.entryActivated()
                    }
                    else reader.toggleOutline(modelData.nodeId)
                }
                Accessible.name: modelData.label
                contentItem: RowLayout {
                    spacing: 6
                    ToolButton {
                        objectName: "navigation-toggle-" + node.modelData.nodeId
                        visible: node.modelData.hasChildren
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 44
                        icon.source: "../../icons/chevron-right.svg"
                        icon.width: 12
                        icon.height: 12
                        icon.color: node.modelData.inActivePath ? Theme.accent : Theme.secondary
                        rotation: node.modelData.expanded ? 90 : 0
                        Behavior on rotation { NumberAnimation { duration: Theme.fast } }
                        Accessible.name: (node.modelData.expanded ? qsTranslate("Epubify", "Collapse %1") : qsTranslate("Epubify", "Expand %1")).arg(node.modelData.label)
                        onClicked: reader.toggleOutline(node.modelData.nodeId)
                        background: Rectangle { radius: 5; color: parent.hovered ? Theme.border : "transparent" }
                    }
                    Item {
                        visible: !node.modelData.hasChildren
                        Layout.preferredWidth: 22
                        Layout.preferredHeight: 22
                        Label {
                            anchors.centerIn: parent
                            text: reader.navigationSection === "figures" ? "◇" : "·"
                            color: node.modelData.active ? Theme.accent : Theme.secondary
                            font.pixelSize: 16
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: node.modelData.label
                        textFormat: Text.PlainText
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        color: node.modelData.active ? Theme.accent : Theme.text
                        font {
                            pixelSize: 13
                            weight: node.modelData.depth === 0 || node.modelData.inActivePath ? Font.DemiBold : Font.Normal
                            underline: node.hovered && !!node.modelData.href
                        }
                    }
                }
                background: Rectangle {
                    radius: 8
                    color: node.modelData.active ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.12)
                           : node.hovered ? Theme.elevated : "transparent"
                    border.color: node.activeFocus ? Theme.accent : "transparent"
                    Rectangle {
                        x: 0; y: 10; width: 2; height: parent.height - 20; radius: 1
                        color: Theme.accent
                        visible: node.modelData.active
                    }
                }
                ToolTip.visible: hovered
                ToolTip.delay: 1200
                ToolTip.text: modelData.label
            }
            Label {
                anchors { centerIn: parent; margins: 14 }
                width: parent.width - 24
                visible: outline.count === 0
                text: reader.navigationSection === "figures" && reader.figuresLoading
                      ? qsTranslate("Epubify", "Looking for illustrations…")
                      : reader.navigationQuery ? qsTranslate("Epubify", "No matching entries")
                      : reader.navigationSection === "figures" ? qsTranslate("Epubify", "No figures detected in this book") : qsTranslate("Epubify", "No contents available")
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                color: Theme.secondary
                font.pixelSize: 12
            }
        }
        Label {
            Layout.fillWidth: true
            text: reader.navigationSection === "figures" ? qsTranslate("Epubify", "Select a figure to jump to its page.")
                  : qsTranslate("Epubify", "Select a title to jump to that section.")
            color: Theme.secondary
            wrapMode: Text.Wrap
            font.pixelSize: 11
        }
    }
}
