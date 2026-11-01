import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    id: footer
    readonly property bool compact: width < 500
    objectName: "libraryFooter"
    signal detailsRequested()
    implicitHeight: library.busy ? 58 : 44
    Rectangle {
        objectName: "libraryFooterFade"
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        height: footer.height + 44
        enabled: false
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0; color: Qt.rgba(Theme.background.r, Theme.background.g, Theme.background.b, 0) }
            GradientStop { position: 0.7; color: Theme.background }
            GradientStop { position: 1; color: Theme.background }
        }
    }
    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.AllButtons
        onWheel: function(wheel) { wheel.accepted = false }
    }
    ProgressBar {
        anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: 4 }
        visible: library.busy
        from: 0
        to: Math.max(1, library.importTotal)
        value: library.importCompleted
        Accessible.name: qsTranslate("Epubify", "EPUB import progress")
    }
    RowLayout {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        spacing: 16
        Label {
            visible: library.message.length > 0
            Layout.fillWidth: true
            text: library.message
            textFormat: Text.PlainText
            color: Theme.secondary
            elide: Text.ElideRight
            font.pixelSize: 12
            Accessible.role: Accessible.StaticText
        }
        AnimatedButton {
            objectName: "importResultsButton"
            visible: library.importResults.length > 0
            text: qsTranslate("Epubify", "Import details")
            onClicked: footer.detailsRequested()
        }
        ColumnLayout {
            visible: !footer.compact || (!library.message && !library.busy)
            Layout.fillWidth: footer.compact
            Layout.preferredWidth: footer.compact ? footer.width : 220
            spacing: 2
            Label {
                Layout.fillWidth: true
                text: qsTranslate("Epubify", "EPUB 2 & 3  ·  Local by design")
                horizontalAlignment: Text.AlignHCenter
                color: Theme.secondary
                font { pixelSize: 10; letterSpacing: 0.3 }
            }
            Label {
                objectName: "libraryFooterQuote"
                Layout.fillWidth: true
                text: qsTranslate("Epubify", "A little room for a good book.")
                horizontalAlignment: Text.AlignHCenter
                color: Theme.secondary
                font { family: Theme.serif; pixelSize: 12; italic: true }
                Accessible.name: text
            }
        }
    }
}
