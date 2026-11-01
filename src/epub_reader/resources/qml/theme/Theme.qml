pragma Singleton
import QtQuick

QtObject {
    readonly property int compactBreakpoint: 720
    readonly property int touchTarget: 48
    readonly property bool dark: preferences.dark
    readonly property var colors: preferences.palette
    readonly property color background: colors.background
    readonly property color surface: colors.surface
    readonly property color elevated: colors.elevated
    readonly property color text: colors.text
    readonly property color secondary: colors.secondary
    readonly property color accent: colors.accent
    readonly property color accentText: colors.accent_text
    readonly property color border: colors.border
    readonly property color action: colors.action
    readonly property color actionText: colors.on_action
    readonly property color errorSurface: colors.error_surface
    readonly property color error: colors.error
    readonly property var coverColors: preferences.coverColors
    readonly property color coverText: preferences.coverText
    readonly property color coverSecondary: preferences.coverSecondary
    readonly property string sans: preferences.fontFamilies.sans
    readonly property string serif: preferences.fontFamilies.serif
    readonly property string mono: preferences.fontFamilies.mono
    readonly property int small: 12
    readonly property int body: 14
    readonly property int heading: 32
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space6: 24
    readonly property int space8: 32
    readonly property int radius: 10
    readonly property int largeRadius: 18
    readonly property real shadowOpacity: 0.28
    readonly property int fast: preferences.reducedMotion ? 0 : 140
    readonly property int normal: preferences.reducedMotion ? 0 : 240
    readonly property int easing: Easing.OutCubic
}
