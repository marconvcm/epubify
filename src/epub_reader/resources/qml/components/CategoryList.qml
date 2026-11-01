import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ListView {
    id: categories
    signal selectionMade()
    objectName: "libraryCategories"
    model: library.categories
    clip: true
    spacing: 4
    boundsBehavior: Flickable.StopAtBounds
    ScrollBar.vertical: ScrollBar { }
    delegate: ItemDelegate {
        id: entry
        required property var modelData
        objectName: "category-" + modelData.categoryId
        width: ListView.view.width
        implicitHeight: Math.max(Theme.touchTarget, contentItem.implicitHeight + 16)
        padding: 10
        onClicked: {
            const view = entry.ListView.view
            library.selectCategory(modelData.categoryId)
            view.selectionMade()
        }
        Accessible.name: qsTranslate("Epubify", "%1, %2 books").arg(qsTranslate("Epubify", modelData.label)).arg(modelData.count)
        contentItem: RowLayout {
            spacing: 8
            Label {
                Layout.fillWidth: true
                text: qsTranslate("Epubify", entry.modelData.label)
                textFormat: Text.PlainText
                color: library.activeCategory === entry.modelData.categoryId ? Theme.accent : Theme.text
                font { family: Theme.sans; pixelSize: 12 }
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Label {
                text: entry.modelData.count
                color: Theme.secondary
                font { family: Theme.mono; pixelSize: 10 }
            }
        }
        background: Rectangle {
            radius: Theme.radius
            color: library.activeCategory === entry.modelData.categoryId || entry.hovered ? Theme.elevated : "transparent"
            border.color: entry.activeFocus ? Theme.accent : "transparent"
        }
    }
}
