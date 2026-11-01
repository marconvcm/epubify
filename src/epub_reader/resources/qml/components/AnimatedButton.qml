import QtQuick
import QtQuick.Controls
import "../theme"

Button {
    id: control
    property bool primary: false
    property url glyph
    readonly property bool compact: ApplicationWindow.window ? ApplicationWindow.window.touchInterface || ApplicationWindow.window.width < Theme.compactBreakpoint : false
    objectName: primary ? "primary-" + text : ""
    implicitHeight: compact ? Theme.touchTarget : 38
    implicitWidth: Math.max(compact ? Theme.touchTarget : 38, contentItem.implicitWidth + 24)
    hoverEnabled: true
    font.family: Theme.sans
    font.pixelSize: Theme.body
    icon.source: glyph
    icon.width: 18
    icon.height: 18
    icon.color: control.primary ? Theme.actionText : Theme.text
    palette.buttonText: control.primary ? Theme.actionText : Theme.text
    palette.windowText: control.primary ? Theme.actionText : Theme.text
    palette.text: control.primary ? Theme.actionText : Theme.text
    palette.highlightedText: control.primary ? Theme.actionText : Theme.text
    opacity: enabled ? 1 : 0.45
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Theme.easing } }
    background: Rectangle {
        radius: Theme.radius
        color: control.primary ? Theme.action : control.hovered || control.down ? Theme.elevated : "transparent"
        border.width: control.activeFocus ? 2 : 1
        border.color: control.activeFocus ? Theme.accent : control.primary ? Theme.accent : Theme.border
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    ToolTip.visible: hovered && ToolTip.text.length > 0
    ToolTip.delay: 700
}
