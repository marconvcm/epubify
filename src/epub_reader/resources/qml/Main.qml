import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import "screens"
import "components"
import "theme"

ApplicationWindow {
    id: window
    objectName: "mainWindow"
    property bool mobilePreview: false
    readonly property bool touchInterface: mobilePreview || Qt.platform.os === "android" || Qt.platform.os === "ios"
    readonly property bool compactLayout: width < Theme.compactBreakpoint || (touchInterface && height < 600)
    width: 1180
    height: 800
    minimumWidth: 320
    minimumHeight: 320
    visible: true
    title: reader.active ? reader.title + qsTranslate("Epubify", " — Epubify") : "Epubify"
    color: Theme.background
    font.family: Theme.sans
    palette.window: Theme.background
    palette.windowText: Theme.text
    palette.text: Theme.text
    palette.base: Theme.surface
    palette.button: Theme.elevated
    palette.buttonText: Theme.text
    palette.highlight: Theme.accent
    palette.highlightedText: Theme.accentText
    property bool readerCreated: false
    Behavior on color { ColorAnimation { duration: Theme.normal } }
    LibraryScreen {
        id: libraryScreen
        anchors.fill: parent
        opacity: reader.active ? 0 : 1
        visible: opacity > 0
        enabled: !reader.active
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        onImportRequested: importDialog.open()
    }
    Loader {
        id: readerLoader
        objectName: "readerLoader"
        anchors.fill: parent
        active: window.readerCreated && readerEnabled
        source: "screens/ReaderScreen.qml"
        opacity: reader.active ? 1 : 0
        visible: opacity > 0
        enabled: reader.active
        transform: Translate {
            x: reader.active ? 0 : 16
            Behavior on x { NumberAnimation { duration: Theme.normal; easing.type: Theme.easing } }
        }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
    }
    Connections {
        target: reader
        function onChanged() { if (reader.active) window.readerCreated = true }
        function onErrorChanged() { if (reader.error) errorDialog.open() }
    }
    FileDialog {
        id: importDialog
        objectName: "epubImportDialog"
        title: qsTranslate("Epubify", "Add books to your library")
        nameFilters: [qsTranslate("Epubify", "EPUB books (*.epub)")]
        fileMode: FileDialog.OpenFiles
        onAccepted: library.importFiles(selectedFiles)
    }
    Dialog {
        id: errorDialog
        anchors.centerIn: parent
        width: Math.min(window.width - 80, 480)
        title: qsTranslate("Epubify", "Unable to complete the action")
        modal: true
        standardButtons: Dialog.Ok
        contentItem: Label { text: reader.error; textFormat: Text.PlainText; wrapMode: Text.Wrap; color: Theme.text }
        background: Rectangle { radius: Theme.largeRadius; color: Theme.errorSurface; border.color: Theme.error }
    }
    Shortcut { sequence: "Ctrl+O"; enabled: !library.busy; onActivated: importDialog.open() }
    Shortcut { sequence: "Ctrl+L"; enabled: !reader.active; onActivated: libraryScreen.focusSearch() }
    Shortcut { sequence: "Left"; enabled: reader.active; onActivated: reader.previous() }
    Shortcut { sequence: "Right"; enabled: reader.active; onActivated: reader.next() }
    Shortcut { sequence: "PgUp"; enabled: reader.active; onActivated: reader.previous() }
    Shortcut { sequence: "PgDown"; enabled: reader.active; onActivated: reader.next() }
    Shortcut { sequence: "F11"; enabled: reader.active; onActivated: reader.toggleImmersive() }
    // Popups/drawers handle Escape first. Back goes through the same reader action.
    Shortcut { sequences: ["Escape", "Back"]; enabled: reader.active; onActivated: readerLoader.item.goBack() }
    onClosing: reader.flush()
}
