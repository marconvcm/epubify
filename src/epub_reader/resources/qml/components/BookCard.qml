import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import "../theme"

Button {
    id: card
    required property string bookId
    required property string bookTitle
    required property string author
    required property url coverUrl
    required property real progressValue
    required property bool favorite
    property int tint: parseInt(bookId.slice(0, 2), 16) % Theme.coverColors.length
    property bool compactLayout: false
    hoverEnabled: true
    padding: 8
    Accessible.name: qsTranslate("Epubify", "%1, by %2, %3 percent read").arg(bookTitle).arg(author).arg(Math.round(progressValue * 100))
    background: Rectangle {
        color: card.hovered ? Theme.surface : "transparent"
        radius: Theme.largeRadius
        border.color: card.activeFocus ? Theme.accent : "transparent"
        border.width: 2
        Behavior on color { ColorAnimation { duration: Theme.fast } }
    }
    contentItem: Column {
        spacing: 10
        Rectangle {
            id: cover
            width: parent.width
            height: width * 1.36
            radius: 6
            color: Theme.coverColors[card.tint]
            y: card.hovered ? -4 : 0
            Behavior on y { NumberAnimation { duration: Theme.normal; easing.type: Theme.easing } }
            layer.enabled: card.hovered && !preferences.reducedMotion
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowBlur: 0.6
                shadowVerticalOffset: 8
                shadowOpacity: Theme.shadowOpacity
            }
            Column {
                anchors { fill: parent; margins: 20 }
                anchors.topMargin: card.compactLayout ? 56 : 20
                spacing: 12
                Rectangle { width: 28; height: 2; color: Theme.coverText }
                Label {
                    width: parent.width
                    text: card.bookTitle
                    textFormat: Text.PlainText
                    color: Theme.coverText
                    wrapMode: Text.Wrap
                    maximumLineCount: card.compactLayout ? 3 : 5
                    elide: Text.ElideRight
                    font { family: Theme.serif; pixelSize: Math.max(18, cover.width / 9); weight: Font.Medium }
                }
                Label {
                    width: parent.width
                    text: card.author
                    textFormat: Text.PlainText
                    color: Theme.coverSecondary
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    font.pixelSize: 11
                }
            }
            Image {
                anchors.fill: parent
                source: card.coverUrl
                asynchronous: true
                sourceSize.width: 420
                sourceSize.height: 560
                fillMode: Image.PreserveAspectCrop
                visible: status === Image.Ready
            }
            AnimatedButton {
                objectName: "favorite-" + card.bookId
                anchors { top: parent.top; right: parent.right; margins: 8 }
                width: card.compactLayout ? 44 : 34; height: width
                visible: card.compactLayout || card.favorite || card.hovered || hovered || activeFocus
                glyph: card.favorite ? "../../icons/heart-filled.svg" : "../../icons/heart.svg"
                icon.color: card.favorite ? Theme.accent : Theme.text
                Accessible.name: card.favorite ? qsTranslate("Epubify", "Remove from favorites") : qsTranslate("Epubify", "Add to favorites")
                ToolTip.text: Accessible.name
                onClicked: library.toggleFavorite(card.bookId)
                background: Rectangle { radius: 17; color: Theme.background; opacity: 0.95; border.color: Theme.border }
            }
            Rectangle {
                x: 3; width: 3; height: parent.height
                color: "#20000000"
            }
        }
        Label {
            width: parent.width
            text: card.bookTitle
            textFormat: Text.PlainText
            color: Theme.text
            font { pixelSize: 14; weight: Font.DemiBold }
            elide: Text.ElideRight
        }
        Label {
            width: parent.width
            text: card.author
            textFormat: Text.PlainText
            color: Theme.secondary
            font.pixelSize: 12
            elide: Text.ElideRight
        }
        Row {
            width: parent.width
            spacing: 8
            Rectangle {
                width: parent.width - 40; height: 3; radius: 2
                anchors.verticalCenter: parent.verticalCenter
                color: Theme.border
                Rectangle { width: parent.width * card.progressValue; height: 3; radius: 2; color: Theme.accent }
            }
            Label {
                text: card.progressValue > 0 ? Math.round(card.progressValue * 100) + "%" : qsTranslate("Epubify", "New")
                color: Theme.secondary
                font.pixelSize: 10
            }
        }
    }
}
