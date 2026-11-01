import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Popup {
    id: panel
    objectName: "syncPanel"
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(600, parent.width - 24)
    height: Math.min(680, parent.height - 32)
    padding: 20
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: sync.refresh()
    background: Rectangle { color: Theme.surface; radius: Theme.largeRadius; border.color: Theme.border }
    contentItem: ScrollView {
        id: scroll
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: scroll.availableWidth
            spacing: 12
            Label { text: qsTranslate("Epubify", "Devices & sync"); color: Theme.text; font { family: Theme.sans; pixelSize: 22; weight: Font.DemiBold } }
            Switch {
                text: qsTranslate("Epubify", "Local network sync")
                checked: sync.enabled
                palette.windowText: Theme.text
                enabled: sync.available
                onClicked: sync.setEnabled(checked)
            }
            Label {
                Layout.fillWidth: true
                text: sync.available ? sync.status : qsTranslate("Epubify", "Local sync is unavailable in this build.")
                color: Theme.secondary
                wrapMode: Text.Wrap
            }
            Label { text: qsTranslate("Epubify", "Pair another device"); color: Theme.text; font.weight: Font.DemiBold }
            GridLayout {
                Layout.fillWidth: true
                columns: panel.width < 440 ? 1 : 2
                AnimatedButton { text: qsTranslate("Epubify", "Create invitation"); enabled: sync.ready; onClicked: sync.createInvitation() }
                AnimatedButton { text: qsTranslate("Epubify", "Copy invitation"); enabled: sync.invitation.length > 0; onClicked: sync.copyInvitation() }
            }
            TextArea {
                Layout.fillWidth: true
                Layout.maximumHeight: 80
                visible: sync.invitation.length > 0
                text: sync.invitation
                readOnly: true
                selectByMouse: true
                wrapMode: Text.WrapAnywhere
                color: Theme.text
                font { family: Theme.mono; pixelSize: 10 }
                background: Rectangle { color: Theme.background; radius: Theme.radius }
            }
            Label {
                Layout.fillWidth: true
                text: qsTranslate("Epubify", "Share the invitation with the device you trust. It expires in 5 minutes and can be used once.")
                color: Theme.secondary
                wrapMode: Text.Wrap
                font.pixelSize: 12
            }
            TextField {
                id: invitation
                objectName: "pairingInvitation"
                Layout.fillWidth: true
                placeholderText: qsTranslate("Epubify", "Paste an invitation")
                placeholderTextColor: Theme.secondary
                color: Theme.text
                selectByMouse: true
                background: Rectangle { color: Theme.background; radius: Theme.radius; border.color: Theme.border }
            }
            AnimatedButton { text: qsTranslate("Epubify", "Pair device"); primary: true; enabled: sync.ready && invitation.text.length > 0; onClicked: { sync.pair(invitation.text); invitation.clear() } }
            Label { text: qsTranslate("Epubify", "Nearby devices"); color: Theme.text; font.weight: Font.DemiBold }
            Repeater {
                model: sync.peers
                delegate: RowLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    ColumnLayout {
                        Layout.fillWidth: true
                        Label { text: modelData.name; textFormat: Text.PlainText; color: Theme.text }
                        Label { text: modelData.id.slice(0,16); color: Theme.secondary; font { family: Theme.mono; pixelSize: 10 } }
                        Label { text: modelData.connected ? qsTranslate("Epubify", "Connected") : modelData.paired ? qsTranslate("Epubify", "Paired") : qsTranslate("Epubify", "Nearby"); color: Theme.secondary }
                    }
                    AnimatedButton { text: qsTranslate("Epubify", "Revoke"); visible: !!modelData.paired; onClicked: sync.revoke(modelData.id) }
                }
            }
            Label { visible: sync.peers.length === 0; text: qsTranslate("Epubify", "No devices found"); color: Theme.secondary }
            Label { text: qsTranslate("Epubify", "Conflicts"); color: Theme.text; font.weight: Font.DemiBold }
            Repeater {
                model: sync.conflicts
                delegate: ColumnLayout {
                    id: conflict
                    required property var modelData
                    Layout.fillWidth: true
                    Label { text: conflict.modelData.kind === "preference" ? qsTranslate("Epubify", conflict.modelData.context) : conflict.modelData.context; textFormat: Text.PlainText; color: Theme.secondary; font.pixelSize: 11 }
                    Repeater {
                        model: conflict.modelData.choices
                        delegate: RowLayout {
                            required property var modelData
                            Layout.fillWidth: true
                            Label { Layout.fillWidth: true; text: modelData.device + " · " + (modelData.translate_summary ? qsTranslate("Epubify", modelData.summary) : modelData.summary); textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere; maximumLineCount: 4; elide: Text.ElideRight; color: Theme.text; font.pixelSize: 11 }
                            AnimatedButton { text: qsTranslate("Epubify", "Keep this version"); onClicked: sync.resolve(conflict.modelData.kind,conflict.modelData.key,modelData.id) }
                        }
                    }
                }
            }
            Label { visible: sync.conflicts.length === 0; text: qsTranslate("Epubify", "No conflicts"); color: Theme.secondary }
            AnimatedButton { text: qsTranslate("Epubify", "Done"); onClicked: panel.close() }
        }
    }
}
