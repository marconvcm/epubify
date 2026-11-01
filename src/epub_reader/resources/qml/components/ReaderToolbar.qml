import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: bar
    readonly property bool compact: width < 900 || ApplicationWindow.window.compactLayout
    function closePanels() {
        if (appearance.visible) { appearance.close(); return true }
        if (notes.visible) { notes.close(); return true }
        if (readerSettings.visible) { readerSettings.close(); return true }
        if (more.visible) { more.close(); return true }
        return false
    }
    signal contentsRequested()
    color: Theme.surface
    implicitHeight: 68
    RowLayout {
        anchors { fill: parent; leftMargin: bar.compact ? 12 : 20; rightMargin: bar.compact ? 12 : 20 }
        spacing: bar.compact ? 8 : 10
        AnimatedButton {
            glyph: "../../icons/arrow-left.svg"
            Accessible.name: qsTranslate("Epubify", "Return to library")
            ToolTip.text: qsTranslate("Epubify", "Return to library · Escape")
            onClicked: reader.close()
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: 2
            Label {
                Layout.fillWidth: true
                text: reader.title
                textFormat: Text.PlainText
                color: Theme.text
                elide: Text.ElideRight
                font { pixelSize: 14; weight: Font.DemiBold }
            }
            Label { Layout.fillWidth: true; text: reader.author; elide: Text.ElideRight; textFormat: Text.PlainText; color: Theme.secondary; font.pixelSize: 11 }
        }
        AnimatedButton {
            objectName: "readerContentsButton"
            glyph: "../../icons/contents.svg"
            Accessible.name: qsTranslate("Epubify", "Table of contents")
            ToolTip.text: qsTranslate("Epubify", "Table of contents · Ctrl+T")
            onClicked: bar.contentsRequested()
        }
        AnimatedButton {
            visible: !bar.compact
            text: "A−"
            enabled: preferences.fontSize > 14
            Accessible.name: qsTranslate("Epubify", "Decrease font size")
            onClicked: preferences.setFontSize(preferences.fontSize - 1)
        }
        Label { visible: !bar.compact; text: preferences.fontSize; color: Theme.secondary; font { family: Theme.mono; pixelSize: 12 } }
        AnimatedButton {
            visible: !bar.compact
            text: "A+"
            enabled: preferences.fontSize < 32
            Accessible.name: qsTranslate("Epubify", "Increase font size")
            onClicked: preferences.setFontSize(preferences.fontSize + 1)
        }
        AnimatedButton {
            id: appearanceButton
            visible: !bar.compact
            objectName: "appearanceButton"
            glyph: "../../icons/paper.svg"
            Accessible.name: qsTranslate("Epubify", "Reading surface and texture")
            ToolTip.text: qsTranslate("Epubify", "Reading surface and texture")
            onClicked: appearance.opened ? appearance.close() : appearance.open()
            ReadingAppearance {
                id: appearance
            }
        }
        AnimatedButton {
            visible: !bar.compact
            objectName: "notesButton"
            glyph: "../../icons/note.svg"
            Accessible.name: qsTranslate("Epubify", "Notes")
            onClicked: notes.open()
            NotesPanel { id: notes }
        }
        AnimatedButton {
            visible: !bar.compact
            glyph: "../../icons/settings.svg"
            Accessible.name: qsTranslate("Epubify", "Settings")
            onClicked: readerSettings.opened ? readerSettings.close() : readerSettings.open()
            SettingsPanel {
                id: readerSettings
                objectName: "readerSettings"
            }
        }
        AnimatedButton {
            visible: !bar.compact
            glyph: preferences.dark ? "../../icons/sun.svg" : "../../icons/moon.svg"
            Accessible.name: qsTranslate("Epubify", "Switch reading theme")
            ToolTip.text: qsTranslate("Epubify", "Switch reading theme")
            onClicked: preferences.toggleTheme()
        }
        AnimatedButton {
            visible: !bar.compact
            glyph: "../../icons/focus.svg"
            Accessible.name: qsTranslate("Epubify", "Focus reading mode")
            ToolTip.text: qsTranslate("Epubify", "Focus reading mode · F11")
            onClicked: reader.toggleImmersive()
        }
        AnimatedButton {
            id: moreButton
            objectName: "readerMoreButton"
            visible: bar.compact
            glyph: "../../icons/settings.svg"
            Accessible.name: qsTranslate("Epubify", "Settings")
            onClicked: more.open()
            Menu {
                id: more
                objectName: "readerMoreMenu"
                width: Math.min(280, bar.width - 24)
                x: moreButton.width - width
                y: moreButton.height + 4
                MenuItem { text: qsTranslate("Epubify", "Appearance"); implicitHeight: Theme.touchTarget; onTriggered: appearance.open() }
                MenuItem { text: qsTranslate("Epubify", "Notes"); implicitHeight: Theme.touchTarget; onTriggered: notes.open() }
                MenuItem { text: qsTranslate("Epubify", "Switch reading theme"); implicitHeight: Theme.touchTarget; onTriggered: preferences.toggleTheme() }
                MenuItem { text: qsTranslate("Epubify", "Focus reading mode"); implicitHeight: Theme.touchTarget; onTriggered: reader.toggleImmersive() }
                MenuItem { text: qsTranslate("Epubify", "Settings"); implicitHeight: Theme.touchTarget; onTriggered: readerSettings.open() }
            }
        }
    }
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
}
