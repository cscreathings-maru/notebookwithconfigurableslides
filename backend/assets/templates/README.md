# Bundled templates

`bri-default.pptx` is seeded as the workspace's starting template by
`scripts/seed_lite.py`, so a fresh install can generate a deck before anyone
uploads anything.

## The 30 slides are the product — do not strip them

This file is committed **complete**, at ~16.6 MB. An earlier version stripped
its 30 example slides to get it down to 2.4 MB. That was wrong, and it shipped
a deck with no logo:

| | shapes | images |
|---|---|---|
| the 30 slides | **476** | **57** |
| the 45 layouts | 182 | 29 |
| the 3 masters | 11 | **0** |

The masters carry no images at all, so there is no logo to inherit from them.
The design lives on the slides — slide 21 alone is 95 shapes and 3 images.
`deck/clone.py` renders by **cloning these slides**, so removing them removes
the thing being rendered. The file size is the cost of shipping a real
corporate template.

See `revamp/PLAN-SLIDE-CLONING.md` §1 for the full diagnosis.

## Note on the footer

One layout carries `|Strictly confidential` as baked-in footer text. That is
part of the source deck's brand furniture, not a classification applied by this
system — decks rendered into it will show it. Edit the layout in PowerPoint and
re-import if that is not wanted.

## Replacing it

Drop a new `.pptx` in as `bri-default.pptx`. Do **not** pre-process it.
`tests/unit/test_house_template.py` and `tests/unit/test_deck_clone.py` both
run against this exact file and will fail if the replacement carries no
designed slides — which is the point of committing tests alongside a binary.
