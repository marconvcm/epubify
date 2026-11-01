from typing import Any

from epub_reader.rendering.publication import NavigationEntry


def ancestors(entries: list[NavigationEntry], index: int) -> set[int]:
    result: set[int] = set()
    parent = entries[index].parent
    while 0 <= parent < len(entries) and parent not in result:
        result.add(parent)
        parent = entries[parent].parent
    return result


def navigation_rows(
    entries: list[NavigationEntry], collapsed: set[int], query: str, active: int
) -> list[dict[str, Any]]:
    query = query.strip().casefold()
    matches = {i for i, entry in enumerate(entries) if query in entry.label.casefold()}
    visible = set(matches)
    if query:
        for index in matches:
            visible.update(ancestors(entries, index))
    parents = {entry.parent for entry in entries}
    active_path = ancestors(entries, active) if 0 <= active < len(entries) else set()
    rows = []
    for index, entry in enumerate(entries):
        if (query and index not in visible) or (
            not query and ancestors(entries, index) & collapsed
        ):
            continue
        rows.append(
            {
                "nodeId": index,
                "label": entry.label,
                "href": entry.href,
                "depth": entry.depth,
                "hasChildren": index in parents,
                "expanded": bool(query) or index not in collapsed,
                "active": index == active,
                "inActivePath": index in active_path,
            }
        )
    return rows
