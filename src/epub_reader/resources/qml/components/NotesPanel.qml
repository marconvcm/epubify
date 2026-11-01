import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Popup {
    id: panel
    objectName: "notesPanel"
    property string editingId: ""
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(560, parent.width - 24)
    height: Math.min(600, parent.height - 32)
    padding: 20
    focus: true
    modal: true
    background: Rectangle { color: Theme.surface; radius: Theme.largeRadius; border.color: Theme.border }
    contentItem: ColumnLayout {
        spacing: 12
        Label { text: qsTranslate("Epubify", "Notes"); color: Theme.text; font { family: Theme.sans; pixelSize: 20; weight: Font.DemiBold } }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: 100
            TextArea {
                id: note
                objectName: "noteEditor"
                placeholderText: qsTranslate("Epubify", "Write a note…")
                placeholderTextColor: Theme.secondary
                color: Theme.text
                wrapMode: Text.Wrap
                selectByMouse: true
            }
        }
        AnimatedButton { text: panel.editingId ? qsTranslate("Epubify", "Save note") : qsTranslate("Epubify", "Add note"); enabled: note.text.trim().length > 0 && note.text.length <= 16000; primary: true; onClicked: { if (panel.editingId) reader.updateNote(panel.editingId, note.text); else reader.addNote(note.text); panel.editingId = ""; note.clear() } }
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: reader.notes
            spacing: 10
            ScrollBar.vertical: ScrollBar { }
            delegate: ColumnLayout {
                required property var modelData
                width: ListView.view.width
                Label { Layout.fillWidth: true; text: modelData.text; textFormat: Text.PlainText; color: Theme.text; wrapMode: Text.Wrap }
                GridLayout {
                    Layout.fillWidth: true
                    columns: panel.width < 440 ? 2 : 3
                    AnimatedButton { text: qsTranslate("Epubify", "Edit note"); onClicked: { panel.editingId = modelData.id; note.text = modelData.text; note.forceActiveFocus() } }
                    AnimatedButton { text: qsTranslate("Epubify", "Go to note"); onClicked: { reader.navigateNote(modelData.location); panel.close() } }
                    AnimatedButton { text: qsTranslate("Epubify", "Delete note"); onClicked: reader.removeNote(modelData.id) }
                }
            }
        }
        AnimatedButton { text: qsTranslate("Epubify", "Done"); onClicked: panel.close() }
    }
}
