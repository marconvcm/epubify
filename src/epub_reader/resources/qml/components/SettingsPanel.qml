import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Popup {
    id: panel
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(360, parent.width - 24)
    height: Math.min(body.implicitHeight + padding * 2, parent.height - 32)
    padding: 20
    focus: true
    modal: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle { color: Theme.surface; radius: Theme.largeRadius; border.color: Theme.border }
    SyncPanel { id: devices }
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
        id: body
        width: scroll.availableWidth
        spacing: 14
        Label { text: qsTranslate("Epubify", "Settings"); color: Theme.text; font { family: Theme.sans; pixelSize: 20; weight: Font.DemiBold } }
        Label { text: qsTranslate("Epubify", "Language"); color: Theme.secondary; font.pixelSize: 12 }
        ComboBox {
            objectName: "languagePicker"
            Layout.fillWidth: true
            model: i18n.languages
            textRole: "name"
            valueRole: "code"
            currentIndex: count > 0 ? indexOfValue(i18n.language) : -1
            palette.text: Theme.text
            palette.buttonText: Theme.text
            Accessible.name: qsTranslate("Epubify", "Application language")
            onActivated: i18n.setLanguage(currentValue)
        }
        Label { text: qsTranslate("Epubify", "Color scheme"); color: Theme.secondary; font.pixelSize: 12 }
        ComboBox {
            objectName: "settingsSchemePicker"
            Layout.fillWidth: true
            model: preferences.schemeOptions
            textRole: "name"
            valueRole: "id"
            currentIndex: count > 0 ? indexOfValue(preferences.colorScheme) : -1
            palette.text: Theme.text
            palette.buttonText: Theme.text
            Accessible.name: qsTranslate("Epubify", "Application color scheme")
            onActivated: preferences.setColorScheme(currentValue)
        }
        AnimatedButton {
            objectName: "openSyncButton"
            text: qsTranslate("Epubify", "Devices & sync")
            Layout.fillWidth: true
            onClicked: devices.open()
        }
        Switch {
            Layout.fillWidth: true
            text: qsTranslate("Epubify", "Dark appearance")
            checked: preferences.dark
            palette.windowText: Theme.text
            onClicked: preferences.toggleTheme()
        }
        Switch {
            Layout.fillWidth: true
            text: qsTranslate("Epubify", "Reduce motion")
            checked: preferences.reducedMotion
            palette.windowText: Theme.text
            onClicked: preferences.toggleReducedMotion()
        }
        AnimatedButton {
            Layout.fillWidth: true
            text: qsTranslate("Epubify", "Done")
            onClicked: panel.close()
        }
        }
    }
}
