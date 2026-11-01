import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Dialog {
    id: report
    parent: Overlay.overlay
    objectName: "importReport"
    anchors.centerIn: parent
    width: Math.min(580, parent.width - 40)
    height: Math.min(implicitHeight, parent.height - 32)
    modal: true
    padding: 20
    header: Item {
        implicitHeight: 64
        Label {
            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: 20 }
            text: library.busy ? qsTranslate("Epubify", "Importing books…") : qsTranslate("Epubify", "Import results")
            color: Theme.text
            font { family: Theme.sans; pixelSize: 20; weight: Font.DemiBold }
        }
    }
    footer: Item {
        implicitHeight: 64
        AnimatedButton {
            anchors { right: parent.right; verticalCenter: parent.verticalCenter; rightMargin: 20 }
            text: qsTranslate("Epubify", "Done")
            onClicked: report.close()
        }
    }
    background: Rectangle { color: Theme.surface; radius: Theme.largeRadius; border.color: Theme.border }
    contentItem: ListView {
        implicitHeight: Math.min(380, Math.max(100, contentHeight))
        clip: true
        spacing: 8
        model: library.importResults
        ScrollBar.vertical: ScrollBar { }
        delegate: Rectangle {
            required property var modelData
            width: ListView.view.width
            implicitHeight: details.implicitHeight + 24
            color: modelData.status === "failed" ? Theme.errorSurface : Theme.background
            radius: Theme.radius
            ColumnLayout {
                id: details
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: 12 }
                spacing: 4
                Label {
                    Layout.fillWidth: true
                    text: modelData.source
                    textFormat: Text.PlainText
                    color: Theme.text
                    font { family: Theme.sans; pixelSize: 13; weight: Font.DemiBold }
                    wrapMode: Text.WrapAnywhere
                }
                Label {
                    Layout.fillWidth: true
                    text: modelData.status === "added" ? qsTranslate("Epubify", "Added to your library")
                          : modelData.status === "existing" ? qsTranslate("Epubify", "Already in your library") : qsTranslate("Epubify", "Could not import")
                    color: modelData.status === "failed" ? Theme.error : Theme.accent
                    font.pixelSize: 12
                }
                Label {
                    Layout.fillWidth: true
                    text: modelData.status === "failed" ? qsTranslate("Epubify", modelData.detail) : modelData.detail
                    textFormat: Text.PlainText
                    color: modelData.status === "failed" ? Theme.error : Theme.secondary
                    wrapMode: Text.Wrap
                    font.pixelSize: 12
                }
            }
        }
    }
}
