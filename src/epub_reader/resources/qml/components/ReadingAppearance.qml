import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Epubify.Native 1.0
import "../theme"

Popup {
    id: popup
    objectName: "readingAppearance"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(360, parent.width - 24)
    height: Math.min(body.implicitHeight + padding * 2, parent.height - 32)
    padding: 18
    focus: true
    modal: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    background: Rectangle {
        color: Theme.surface
        radius: Theme.largeRadius
        border.color: Theme.border
    }
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
        id: body
        width: scroll.availableWidth
        spacing: 14
        Label { text: qsTranslate("Epubify", "Appearance"); color: Theme.text; font { pixelSize: 17; weight: Font.DemiBold } }
        RowLayout {
            Layout.fillWidth: true
            AnimatedButton {
                objectName: "mobileFontDecrease"
                text: "A−"
                enabled: preferences.fontSize > 14
                Accessible.name: qsTranslate("Epubify", "Decrease font size")
                onClicked: preferences.setFontSize(preferences.fontSize - 1)
            }
            Label { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; text: preferences.fontSize; color: Theme.text; font.pixelSize: 18 }
            AnimatedButton {
                objectName: "mobileFontIncrease"
                text: "A+"
                enabled: preferences.fontSize < 32
                Accessible.name: qsTranslate("Epubify", "Increase font size")
                onClicked: preferences.setFontSize(preferences.fontSize + 1)
            }
        }
        Label {
            Layout.fillWidth: true
            text: qsTranslate("Epubify", "Choose the tone and texture of your page.")
            color: Theme.secondary
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Label { text: qsTranslate("Epubify", "Color scheme"); color: Theme.secondary; font.pixelSize: 12 }
        ComboBox {
            id: schemePicker
            objectName: "colorSchemePicker"
            Layout.fillWidth: true
            model: preferences.schemeOptions
            textRole: "name"
            valueRole: "id"
            currentIndex: count > 0 ? indexOfValue(preferences.colorScheme) : -1
            palette.buttonText: Theme.text
            palette.text: Theme.text
            font.family: Theme.sans
            Accessible.name: qsTranslate("Epubify", "Application color scheme")
            onActivated: preferences.setColorScheme(currentValue)
        }
        Label { text: qsTranslate("Epubify", "Reading surface"); color: Theme.secondary; font.pixelSize: 12 }
        GridLayout {
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 8
            rowSpacing: 8
            Repeater {
                model: preferences.surfaceOptions
                delegate: Button {
                    id: swatch
                    required property var modelData
                    objectName: "surface-" + modelData.key
                    Layout.fillWidth: true
                    Layout.preferredWidth: 86
                    implicitHeight: 94
                    padding: 6
                    checked: preferences.readingSurface === modelData.key
                    Accessible.name: qsTranslate("Epubify", "%1 reading surface").arg(qsTranslate("Epubify", modelData.label))
                    onClicked: preferences.setReadingSurface(modelData.key)
                    contentItem: Column {
                        spacing: 7
                        SurfacePreview {
                            width: parent.width
                            height: 50
                            surface: swatch.modelData.key
                            dark: preferences.dark
                            colorScheme: preferences.colorScheme
                            Label {
                                anchors.centerIn: parent
                                text: "Aa"
                                color: swatch.modelData.foreground
                                font { family: Theme.serif; pixelSize: 25 }
                            }
                        }
                        Label {
                            width: parent.width
                            text: qsTranslate("Epubify", swatch.modelData.label)
                            horizontalAlignment: Text.AlignHCenter
                            color: swatch.checked ? Theme.accent : Theme.secondary
                            font { pixelSize: 11; weight: swatch.checked ? Font.DemiBold : Font.Normal }
                        }
                    }
                    background: Rectangle {
                        color: swatch.hovered ? Theme.elevated : "transparent"
                        radius: 9
                        border.width: swatch.checked || swatch.activeFocus ? 2 : 1
                        border.color: swatch.checked || swatch.activeFocus ? Theme.accent : Theme.border
                    }
                }
            }
        }
        AnimatedButton { Layout.fillWidth: true; text: qsTranslate("Epubify", "Done"); onClicked: popup.close() }
        }
    }
}
