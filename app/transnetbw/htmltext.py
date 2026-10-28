"""
HTML helpers shared by the page parsers: cleaned element text, and the
boilerplate test that keeps site-wide blocks (contact form, hotline card,
event teasers, cross-links, media, downloads) out of extracted content.
"""

from __future__ import annotations

from bs4 import Tag

from app.transnetbw.normalize import clean_text


BOILERPLATE_CLASSES = frozenset(
    {
        "header-nav",
        "card-contact",
        "form-contact",
        "card-events",
        "image-link-list",
        "linkgroup",
        "media-element",
        "video-player",
        "download-list",
        "contact",
        "quote",
    }
)


def element_text(node) -> str | None:
    """
    Cleaned text of an element, or None when there is none.
    """

    return clean_text(node.get_text(" ", strip=True)) if node is not None else None


def is_boilerplate(tag: Tag) -> bool:
    """
    True when the element or any ancestor is a site-wide block.
    """

    for node in [tag, *tag.parents]:

        if not isinstance(node, Tag):
            continue

        classes = node.get("class") or []

        if BOILERPLATE_CLASSES.intersection(classes):
            return True

    return False
