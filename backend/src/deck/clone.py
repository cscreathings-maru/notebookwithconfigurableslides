"""Image-safe slide cloning (SC-0).

`python-pptx` has no slide-copy API. The obvious implementation --
`deepcopy` the shape tree onto a new slide -- **silently corrupts every
image**: a picture's `r:embed` names a relationship id scoped to the SOURCE
slide's part, and the copy carries that id onto a slide whose rels do not
contain it. The shapes still appear in the file and `len(slide.shapes)` still
matches; only opening an image fails, with `KeyError: "no relationship with
key 'rId3'"`. Verified against the real BRI template's timeline slide, where
all three images broke.

So every relationship reference inside the copied XML is re-related to the
target slide and rewritten. That is the whole reason this module exists.

Cloning (rather than building slides from layouts) is what preserves a
corporate template's design: in the BRI deck the 30 slides carry 476 shapes and
57 images, while the masters carry none at all -- see
`revamp/PLAN-SLIDE-CLONING.md` §1.
"""

from __future__ import annotations

import copy

from ..core.logging import get_logger

logger = get_logger("orchestrator.deck.clone")

_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

# Every attribute that can carry a relationship id into a shape's XML.
#   r:embed -> embedded picture/media
#   r:link  -> linked (external) picture/media
#   r:id    -> charts, OLE objects, hyperlinks
_REL_ATTRS = (f"{{{_R_NS}}}embed", f"{{{_R_NS}}}link", f"{{{_R_NS}}}id")


def _remap_relationships(element, *, source_part, target_part) -> int:
    """Re-relate every relationship this element references onto `target_part`.

    Walks the element AND all descendants: a picture's `r:embed` sits several
    levels down (`p:pic/p:blipFill/a:blip`), so checking only the top-level
    node would miss every image -- which is exactly the naive bug.

    Returns how many references were remapped, so a caller can log it and a
    test can assert the work actually happened rather than trusting silence.
    """
    remapped = 0
    for node in [element, *element.iter()]:
        for attr in _REL_ATTRS:
            rid = node.get(attr)
            if not rid:
                continue
            try:
                rel = source_part.rels[rid]
            except KeyError:
                # A reference the source itself cannot resolve. Leave it as-is:
                # the source deck was already broken here, and inventing a
                # target would turn a visible defect into a confusing one.
                logger.warning("clone_unresolvable_rel", extra={"rid": rid, "attr": attr})
                continue
            if rel.is_external:
                new_rid = target_part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
            else:
                new_rid = target_part.relate_to(rel.target_part, rel.reltype)
            node.set(attr, new_rid)
            remapped += 1
    return remapped


def clone_slide(prs, source):
    """Append a copy of `source` to `prs` and return the new slide.

    The copy uses the source's own layout, so inherited placeholder formatting
    still resolves. `add_slide` seeds the new slide with that layout's
    placeholders; those are removed first, because the source's own shapes --
    which include the design -- replace them wholesale.
    """
    new_slide = prs.slides.add_slide(source.slide_layout)

    for shape in list(new_slide.shapes):
        shape._element.getparent().remove(shape._element)

    total_remapped = 0
    for shape in source.shapes:
        element = copy.deepcopy(shape._element)
        total_remapped += _remap_relationships(
            element, source_part=source.part, target_part=new_slide.part
        )
        new_slide.shapes._spTree.append(element)

    logger.debug(
        "slide_cloned",
        extra={"shapes": len(source.shapes), "relationships_remapped": total_remapped},
    )
    return new_slide


def drop_slides(prs, keep_indexes: set[int]) -> None:
    """Remove every slide whose ORIGINAL index is not in `keep_indexes`.

    Indexes refer to the presentation as it was when this is called, so the
    removal is done back-to-front -- deleting front-to-back would shift the
    indexes of everything after each removal.

    Removing from `sldIdLst` alone leaves an orphaned relationship, so the rel
    is dropped with it.
    """
    slide_id_list = prs.slides._sldIdLst
    for index, slide_id in reversed(list(enumerate(slide_id_list))):
        if index in keep_indexes:
            continue
        prs.part.drop_rel(slide_id.get(f"{{{_R_NS}}}id"))
        slide_id_list.remove(slide_id)


def move_slide(prs, from_index: int, to_index: int) -> None:
    """Move one slide within the deck, by reordering `sldIdLst`.

    Slide ORDER is exactly this list's order -- the same thing the reference
    session edited by hand in `presentation.xml`.
    """
    slide_id_list = prs.slides._sldIdLst
    entries = list(slide_id_list)
    entry = entries[from_index]
    slide_id_list.remove(entry)
    slide_id_list.insert(to_index, entry)
