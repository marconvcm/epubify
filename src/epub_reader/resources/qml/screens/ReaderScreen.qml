import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Epubify.Native 1.0
import "../components"
import "../theme"

Item {
    id: screen
    readonly property bool compact: ApplicationWindow.window.compactLayout
    property bool showContents: width >= 1050
    function toggleContents() {
        if (compact) contentsDrawer.opened ? contentsDrawer.close() : contentsDrawer.open()
        else showContents = !showContents
    }
    function goBack() {
        if (contentsDrawer.visible) contentsDrawer.close()
        else if (toolbar.closePanels()) return
        else if (reader.immersive) reader.toggleImmersive()
        else reader.close()
    }
    onCompactChanged: { contentsDrawer.close(); if (compact) showContents = false }
    ColumnLayout {
        anchors.fill: parent
        spacing: 0
        ReaderToolbar {
            id: toolbar
            Layout.fillWidth: true
            Layout.preferredHeight: reader.immersive ? 0 : screen.compact ? 64 : 68
            opacity: reader.immersive ? 0 : 1
            visible: opacity > 0
            clip: true
            Behavior on opacity { NumberAnimation { duration: Theme.normal } }
            Behavior on Layout.preferredHeight { NumberAnimation { duration: Theme.normal; easing.type: Theme.easing } }
            onContentsRequested: screen.toggleContents()
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            NavigationSidebar {
                Layout.fillHeight: true
                Layout.preferredWidth: screen.showContents && !screen.compact ? Math.min(350, screen.width * 0.40) : 0
                visible: Layout.preferredWidth > 0
                Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.normal; easing.type: Theme.easing } }
                onCloseRequested: screen.showContents = false
            }
            BookPage {
                id: page
                objectName: "nativeBookPage"
                Layout.fillWidth: true
                Layout.fillHeight: true
                renderer: reader.renderer
                onLinkActivated: function(href) { reader.navigate(href) }
                onPageTurnRequested: function(direction) { if (direction > 0) reader.next(); else reader.previous() }
                Accessible.role: Accessible.StaticText
                Accessible.name: qsTranslate("Epubify", "Book page %1").arg(reader.pageLabel)
                Accessible.description: reader.pageText
                Connections {
                    target: reader
                    function onPageTurnStarted(direction) {
                        pageTurn.stop()
                        if (Theme.normal > 0) page.prepareTurn(direction)
                    }
                    function onPageTurnFinished(changed) {
                        if (changed && Theme.normal > 0) pageTurn.restart()
                        else page.finishTurn()
                    }
                    function onChanged() { if (!reader.active) { pageTurn.stop(); page.finishTurn() } }
                }
                Connections {
                    target: preferences
                    function onChanged() { pageTurn.stop(); page.finishTurn() }
                }
                NumberAnimation {
                    id: pageTurn
                    target: page
                    property: "slideProgress"
                    from: 0; to: 1
                    duration: Theme.normal
                    easing.type: Theme.easing
                    onStopped: page.finishTurn()
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: reader.immersive ? 0 : screen.compact ? 60 : 48
            visible: Layout.preferredHeight > 0
            color: Theme.background
            clip: true
            Behavior on Layout.preferredHeight { NumberAnimation { duration: Theme.normal } }
            RowLayout {
                anchors { fill: parent; leftMargin: screen.compact ? 12 : 24; rightMargin: screen.compact ? 12 : 24 }
                AnimatedButton { glyph: "../../icons/arrow-left.svg"; Accessible.name: qsTranslate("Epubify", "Previous page"); onClicked: reader.previous() }
                Item { Layout.fillWidth: true }
                Label { text: qsTranslate("Epubify", "%1 · %2% read").arg(reader.pageLabel).arg(Math.round(reader.progress * 100)); color: Theme.secondary; font { family: Theme.mono; pixelSize: 12 } }
                Item { Layout.fillWidth: true }
                AnimatedButton { glyph: "../../icons/arrow-right.svg"; Accessible.name: qsTranslate("Epubify", "Next page"); onClicked: reader.next() }
            }
        }
    }
    Drawer {
        id: contentsDrawer
        objectName: "readerContentsDrawer"
        width: Math.min(360, screen.width - 24)
        y: ApplicationWindow.window.topPadding
        height: screen.height
        interactive: screen.compact
        modal: true
        contentItem: NavigationSidebar {
            onCloseRequested: contentsDrawer.close()
            onEntryActivated: contentsDrawer.close()
        }
    }
    AnimatedButton {
        anchors { top: parent.top; right: parent.right; margins: 12 }
        visible: reader.immersive
        opacity: hovered || activeFocus ? 1 : 0.3
        glyph: "../../icons/focus.svg"
        Accessible.name: qsTranslate("Epubify", "Leave focus mode")
        ToolTip.text: qsTranslate("Epubify", "Leave focus mode · F11")
        onClicked: reader.toggleImmersive()
        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
    }
    Shortcut { sequence: "Ctrl+T"; enabled: reader.active; onActivated: screen.toggleContents() }
}
