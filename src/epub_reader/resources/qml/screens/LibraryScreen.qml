import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../components"
import "../theme"

Item {
    id: screen
    objectName: "libraryScreen"
    readonly property bool compact: ApplicationWindow.window.compactLayout
    signal importRequested()
    onCompactChanged: if (!compact) navigationDrawer.close()
    function focusSearch() { search.forceActiveFocus(); search.selectAll() }
    RowLayout {
        anchors.fill: parent
        spacing: 0
        Sidebar {
            objectName: "desktopLibrarySidebar"
            visible: !screen.compact
            Layout.fillHeight: true
            Layout.preferredWidth: implicitWidth
            expanded: screen.width > 960
            onImportRequested: screen.importRequested()
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: screen.compact ? 16 : screen.width < 800 ? 24 : 40
            Layout.bottomMargin: screen.compact ? 8 : 16
            spacing: screen.compact ? 16 : 24
            RowLayout {
                Layout.fillWidth: true
                spacing: screen.compact ? 10 : 16
                AnimatedButton {
                    objectName: "libraryMenuButton"
                    visible: screen.compact
                    glyph: "../../icons/sidebar.svg"
                    Accessible.name: qsTranslate("Epubify", "Toggle sidebar")
                    onClicked: navigationDrawer.open()
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 6
                    Label {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                        text: library.favoritesOnly ? qsTranslate("Epubify", "Favorites") : library.activeCategoryName ? qsTranslate("Epubify", library.activeCategoryName) : qsTranslate("Epubify", "Your library")
                        color: Theme.text
                        font { family: Theme.serif; pixelSize: screen.compact ? 25 : Theme.heading; weight: Font.Medium }
                    }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                        text: library.count === 0 ? qsTranslate("Epubify", "Make time for a few more pages.") : (library.categoryCount === 1 ? qsTranslate("Epubify", "%1 book, ready when you are.") : qsTranslate("Epubify", "%1 books, ready when you are.")).arg(library.categoryCount)
                        color: Theme.secondary
                        font.pixelSize: screen.compact ? 12 : Theme.body
                    }
                }
                AnimatedButton {
                    display: screen.compact ? AbstractButton.IconOnly : AbstractButton.TextBesideIcon
                    Layout.preferredWidth: screen.compact ? Theme.touchTarget : implicitWidth
                    text: library.busy ? qsTranslate("Epubify", "Importing %1/%2").arg(library.importCompleted).arg(library.importTotal) : qsTranslate("Epubify", "Import EPUBs")
                    glyph: "../../icons/plus.svg"
                    primary: true
                    objectName: "importEpubButton"
                    Accessible.name: qsTranslate("Epubify", "Import EPUBs")
                    enabled: !library.busy
                    onClicked: screen.importRequested()
                    ToolTip.text: qsTranslate("Epubify", "Import one or more EPUBs · Ctrl+O")
                }
            }
            TextField {
                id: search
                objectName: "librarySearch"
                Layout.fillWidth: true
                implicitHeight: Theme.touchTarget
                placeholderText: qsTranslate("Epubify", "Search title or author…")
                placeholderTextColor: Theme.secondary
                color: Theme.text
                leftPadding: 16
                font.pixelSize: Theme.body
                selectByMouse: true
                Accessible.name: qsTranslate("Epubify", "Search books by title or author")
                onTextChanged: bookModel.search(text)
                background: Rectangle {
                    color: Theme.surface
                    radius: Theme.radius
                    border.color: search.activeFocus ? Theme.accent : Theme.border
                }
            }
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                GridView {
                    id: grid
                    objectName: "bookGrid"
                    anchors.fill: parent
                    clip: true
                    cellWidth: width / Math.max(1, Math.floor(width / (screen.compact ? 140 : 200)))
                    cellHeight: (cellWidth - 24) * 1.36 + 112
                    model: bookModel
                    boundsBehavior: Flickable.StopAtBounds
                    bottomMargin: libraryFooter.height + 12
                    keyNavigationEnabled: true
                    ScrollBar.vertical: ScrollBar { }
                    delegate: BookCard {
                        compactLayout: screen.compact
                        width: grid.cellWidth - 16
                        height: grid.cellHeight - 16
                        onClicked: if (readerEnabled) reader.openBook(bookId)
                    }
                    add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.normal } }
                }
                Flickable {
                    id: emptyState
                    anchors.fill: parent
                    visible: grid.count === 0
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    contentHeight: Math.max(height, emptyMessage.implicitHeight + libraryFooter.height + 16)
                    Column {
                    id: emptyMessage
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: Math.max(0, (emptyState.height - libraryFooter.height - height) / 2)
                    width: Math.min(380, parent.width)
                    spacing: screen.compact ? 14 : 18
                    visible: grid.count === 0
                    Image {
                        anchors.horizontalCenter: parent.horizontalCenter
                        source: "../../icons/app_icon.png"
                        sourceSize.width: 64
                        sourceSize.height: 64
                        opacity: 0.85
                    }
                    Label {
                        width: parent.width
                        text: library.count === 0 ? qsTranslate("Epubify", "Your next chapter starts here") : qsTranslate("Epubify", "No matching books")
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.Wrap
                        color: Theme.text
                        font { family: Theme.serif; pixelSize: screen.compact ? 23 : 25 }
                    }
                    Label {
                        width: parent.width
                        text: library.count === 0 ? qsTranslate("Epubify", "Bring your EPUBs. Find your quiet.\nYour books stay on this device.") : qsTranslate("Epubify", "Try another title or author.")
                        horizontalAlignment: Text.AlignHCenter
                        color: Theme.secondary
                        lineHeight: 1.3
                        wrapMode: Text.Wrap
                        font.pixelSize: 14
                    }
                    AnimatedButton {
                        visible: library.count === 0
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: qsTranslate("Epubify", "Choose your first book")
                        primary: true
                        enabled: !library.busy
                        onClicked: screen.importRequested()
                    }
                    }
                }
                LibraryFooter {
                    id: libraryFooter
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                    height: implicitHeight
                    onDetailsRequested: importReport.open()
                }
            }
        }
    }
    Drawer {
        id: navigationDrawer
        objectName: "libraryDrawer"
        width: Math.min(320, screen.width - 32)
        y: ApplicationWindow.window.topPadding
        height: screen.height
        edge: Qt.LeftEdge
        interactive: screen.compact
        modal: true
        contentItem: Sidebar {
            expanded: true
            drawerMode: true
            onSelectionMade: navigationDrawer.close()
            onImportRequested: { navigationDrawer.close(); screen.importRequested() }
        }
    }
    ImportReport { id: importReport }
}
