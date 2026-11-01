import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    property bool expanded: true
    property bool drawerMode: false
    signal importRequested()
    signal selectionMade()
    color: Theme.surface
    implicitWidth: expanded ? 208 : 72
    Behavior on implicitWidth { NumberAnimation { duration: Theme.normal; easing.type: Theme.easing } }
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.border }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 16
        spacing: root.drawerMode ? 10 : 16
        RowLayout {
            Layout.fillWidth: true
            Image { source: "../../icons/app_icon.png"; sourceSize.width: 40; sourceSize.height: 40 }
            Label {
                visible: root.expanded
                text: "epubify"
                color: Theme.text
                font { family: Theme.sans; pixelSize: 22; weight: Font.DemiBold; letterSpacing: -0.6 }
            }
        }
        Label {
            visible: root.expanded
            text: qsTranslate("Epubify", "YOUR SPACE")
            color: Theme.secondary
            font { pixelSize: 10; letterSpacing: 1.8; weight: Font.DemiBold }
            Layout.topMargin: root.drawerMode ? 6 : 26
        }
        AnimatedButton {
            Layout.fillWidth: true
            text: root.expanded ? qsTranslate("Epubify", "All books · %1").arg(library.count) : ""
            glyph: "../../icons/library.svg"
            ToolTip.text: qsTranslate("Epubify", "Your library")
            onClicked: { library.selectCategory(""); reader.close(); root.selectionMade() }
            background: Rectangle { radius: Theme.radius; color: Theme.elevated; border.color: Theme.border }
            Accessible.name: qsTranslate("Epubify", "All books")
        }
        AnimatedButton {
            objectName: "favoritesButton"
            Layout.fillWidth: true
            text: root.expanded ? qsTranslate("Epubify", "Favorites · %1").arg(library.favoriteCount) : ""
            glyph: "../../icons/heart.svg"
            Accessible.name: qsTranslate("Epubify", "Favorites")
            onClicked: { library.selectFavorites(); reader.close(); root.selectionMade() }
            background: Rectangle { radius: Theme.radius; color: library.favoritesOnly ? Theme.elevated : "transparent"; border.color: parent.activeFocus ? Theme.accent : "transparent" }
        }
        Label {
            visible: root.expanded
            text: library.classifying ? qsTranslate("Epubify", "SORTING YOUR BOOKS…") : qsTranslate("Epubify", "CATEGORIES")
            color: Theme.secondary
            font { family: Theme.sans; pixelSize: 10; letterSpacing: 1.2 }
        }
        CategoryList {
            onSelectionMade: root.selectionMade()
            visible: root.expanded
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
        Item { visible: !root.expanded; Layout.fillHeight: true }
        AnimatedButton {
            visible: !root.drawerMode
            Layout.fillWidth: true
            text: root.expanded ? (preferences.dark ? qsTranslate("Epubify", "Light appearance") : qsTranslate("Epubify", "Dark appearance")) : ""
            glyph: preferences.dark ? "../../icons/sun.svg" : "../../icons/moon.svg"
            Accessible.name: qsTranslate("Epubify", "Switch color theme")
            ToolTip.text: qsTranslate("Epubify", "Switch color theme")
            onClicked: preferences.toggleTheme()
        }
        AnimatedButton {
            visible: !root.drawerMode
            Layout.fillWidth: true
            text: root.expanded ? qsTranslate("Epubify", "Reduce motion") : ""
            glyph: "../../icons/motion.svg"
            checkable: true
            checked: preferences.reducedMotion
            Accessible.name: qsTranslate("Epubify", "Reduce motion")
            ToolTip.text: qsTranslate("Epubify", "Reduce motion")
            onClicked: preferences.toggleReducedMotion()
        }
        AnimatedButton {
            objectName: "settingsButton"
            Layout.fillWidth: true
            text: root.expanded ? qsTranslate("Epubify", "Settings") : ""
            glyph: "../../icons/settings.svg"
            Accessible.name: qsTranslate("Epubify", "Settings")
            onClicked: settings.opened ? settings.close() : settings.open()
            SettingsPanel {
                id: settings
                objectName: "librarySettings"
            }
        }
        AnimatedButton {
            visible: !root.drawerMode
            Layout.fillWidth: true
            text: root.expanded ? qsTranslate("Epubify", "Collapse sidebar") : ""
            glyph: "../../icons/sidebar.svg"
            Accessible.name: qsTranslate("Epubify", "Toggle sidebar")
            ToolTip.text: qsTranslate("Epubify", "Toggle sidebar")
            onClicked: root.expanded = !root.expanded
        }
    }
}
