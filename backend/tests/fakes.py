"""Test doubles for the ingestion slice.

These duck-type the collaborators the ingest service depends on (Open Notebook
client + object store) so upload->ready and failure paths are exercised without a
live engine, MinIO, Redis, or Arq.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Collection
from typing import Any

from src.engines.open_notebook import SourceProgress


def usable_pptx_bytes() -> bytes:
    """A real, valid `.pptx` with actual SLIDES, not just layouts.

    `python-pptx`'s bare `Presentation()` (the old go-to test fixture) ships
    layouts but ZERO slides -- `deck/catalog.py::catalog_template` correctly
    refuses that (nothing to catalogue), where the old geometric
    `deck/inspect.py` was happy reading layouts alone. Every test that just
    needs "a working template" for the Phase C pipeline should build one with
    this, not the bare default.
    """
    from pptx import Presentation

    prs = Presentation()
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = "Cover"

    content_slide = prs.slides.add_slide(prs.slide_layouts[1])
    content_slide.shapes.title.text = "Content"
    content_slide.placeholders[1].text_frame.text = "Point one"

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


async def catalog_and_approve(*, tenant_id: uuid.UUID, template_logical_id: str, client, headers: dict) -> dict:
    """Runs LD-2 cataloguing directly (no live Arq worker in this harness --
    same posture as `test_ingestion.py::_run_ingest` calling the service
    function instead of the task wrapper) and then approves the catalog via
    the real review endpoint (L3), so the template lands `status: approved`
    the way `TemplateService.review_catalog` actually requires. Returns the
    final template JSON.
    """
    from src.core.db import SessionLocal
    from src.deck.catalog import catalog_template
    from src.deck.dump import dump_presentation
    from src.models import Template
    from src.registry.repository import TemplateRepository
    from src.registry.service import apply_catalog_result

    logical_id = uuid.UUID(template_logical_id)
    with SessionLocal() as db:
        row = db.query(Template).filter(Template.logical_id == logical_id).one()
        pptx_bytes = FakeObjectStore().get_bytes(key=row.source_pptx_uri)
        dumps = dump_presentation(pptx_bytes)
        catalog, _usage = await catalog_template(dumps=dumps, llm=FakeLlm(), provider_config={})
        template = TemplateRepository(db, tenant_id).get(row.id)
        apply_catalog_result(template, catalog=catalog, error=None)
        db.add(template)
        db.commit()

    resp = client.post(f"/api/v1/templates/{template_logical_id}/catalog/review", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


class FakeObjectStore:
    """In-memory object store with the same surface as the MinIO store.

    Backed by ONE shared dict, because the real store is one bucket: `get_object_store`
    is `@lru_cache`d, so every collaborator in a process talks to the same MinIO. Tests
    routinely wire one instance into the API (which stores the upload) and hand a second
    to `ingest_source` (which now reads it back); per-instance dicts made those two
    look like different buckets and lost the object. `reset()` clears it between tests.
    """

    _objects: dict[str, bytes] = {}

    def __init__(self) -> None:
        self.objects = type(self)._objects

    @classmethod
    def reset(cls) -> None:
        cls._objects.clear()

    def tenant_key(self, *, tenant_id: str, project_id: str, source_id: str, filename: str) -> str:
        return f"{tenant_id}/{project_id}/sources/{source_id}/{filename}"

    def put_bytes(self, *, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get_bytes(self, *, key: str) -> bytes:
        return self.objects[key]

    def presigned_get(self, *, key: str) -> str:
        return f"https://objectstore.test/{key}"


class FakeOpenNotebook:
    """Configurable fake of the Open Notebook client surface used by ingestion."""

    def __init__(
        self,
        *,
        notebook_id: str = "nb_fake",
        source_id: str = "src_fake",
        status_sequence: list[str] | None = None,
        analysis_ref: str = "analysis_fake",
        add_source_error: Exception | None = None,
        corpus: dict[str, str] | None = None,
        status_detail: str | None = "Unsupported file type: could not extract text.",
    ) -> None:
        # What the engine says when a source fails. Real instances always populate
        # `message`, so a fake that returns None would be less strict than reality.
        self.status_detail = status_detail
        self.notebook_id = notebook_id
        self.source_id = source_id
        # Each get_source_status call pops the next status; defaults to ready.
        self._statuses = list(status_sequence or ["ready"])
        self.analysis_ref = analysis_ref
        self.add_source_error = add_source_error
        # {engine_source_ref: text}. Models the real engine's ONE GLOBAL INDEX -- every
        # project's content is visible to every query, which is exactly the condition
        # the caller-side scoping in search() has to survive.
        self.corpus = dict(corpus or {})
        self.searched_scopes: list[set[str]] = []
        self.calls: list[str] = []
        # What actually crossed the boundary, so a test can assert files were UPLOADED
        # (filename, content_type, byte count) rather than linked.
        self.uploaded: list[tuple[str, str, int]] = []
        self.linked: list[str] = []

    async def create_notebook(self, *, name: str, namespace: str) -> str:
        self.calls.append("create_notebook")
        return self.notebook_id

    async def add_source_file(
        self, *, notebook_id: str, filename: str, content: bytes, content_type: str
    ) -> str:
        self.calls.append("add_source")
        self.uploaded.append((filename, content_type, len(content)))
        if self.add_source_error is not None:
            raise self.add_source_error
        return self.source_id

    async def add_source_link(self, *, notebook_id: str, url: str) -> str:
        self.calls.append("add_source")
        self.linked.append(url)
        if self.add_source_error is not None:
            raise self.add_source_error
        return self.source_id

    async def get_source_status(self, *, source_id: str) -> SourceProgress:
        """Mirrors the real client: state plus the engine's own explanation."""
        self.calls.append("get_source_status")
        state = self._statuses.pop(0) if len(self._statuses) > 1 else self._statuses[0]
        detail = self.status_detail if state == "failed" else None
        return SourceProgress(state=state, detail=detail)

    async def run_transformation(
        self, *, source_id: str, provider_config: dict[str, Any]
    ) -> str:
        self.calls.append("run_transformation")
        return self.analysis_ref

    async def search(
        self, *, allowed_source_refs: Collection[str], query: str
    ) -> list[dict[str, Any]]:
        """Serve from the global corpus, honouring the caller's allow-set.

        Mirrors the real client: the engine itself cannot scope, so anything not in
        `allowed_source_refs` must not come back.
        """
        self.calls.append("search")
        allowed = {str(r).strip() for r in allowed_source_refs if str(r).strip()}
        self.searched_scopes.append(allowed)
        if not allowed:
            return []
        if self.corpus:
            return [
                {"text": text, "source_ref": ref}
                for ref, text in self.corpus.items()
                if ref in allowed
            ]
        # No corpus configured: one canned snippet, attributed to an allowed source.
        return [{"text": "Revenue grew 12% YoY.", "source_ref": sorted(allowed)[0]}]


class FakeLlm:
    """Deterministic-structure LLM fake. Talking-point wording varies per call to
    prove that structure (sections/order) is fixed independently of the model."""

    def __init__(self, *, truncate_first_answer: bool = False) -> None:
        self._call = 0
        self.calls: list[str] = []
        self.chat_models: list[str | None] = []
        # What max_tokens each `chat()` call actually received, in order — lets a
        # test assert the configured cap reached the provider instead of a stale
        # hard-coded one.
        self.max_tokens_seen: list[int] = []
        # F1: simulate the provider hitting its token cap on the FIRST grounded
        # answer only, so a test can exercise both "answer arrives truncated" and,
        # via a second `chat()` call (continue_message's), "continuing clears it".
        self._truncate_first_answer = truncate_first_answer
        self._answer_calls = 0

    async def talking_points(self, *, section_ids, context, profile, provider_config):
        from src.outline.builder import LlmResult

        self._call += 1
        self.calls.append("talking_points")
        points = {sid: [f"point {sid} run{self._call}"] for sid in section_ids}
        return LlmResult(points_by_section=points, tokens_in=120, tokens_out=80)

    async def draft_outline(
        self, *, content, tone, density, n_slides_hint, language, provider_config
    ):
        """Deterministic-shape freeform draft: splits the content into one section
        per non-empty paragraph (or a single section if there's only one), so a
        test can assert structure without depending on real LLM output."""
        from src.outline.builder import FreeformOutlineLlmResult

        self._call += 1
        self.calls.append("draft_outline")
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [content.strip()] if content.strip() else []
        sections = [
            {"title": f"Section {i + 1} run{self._call}", "bullets": [p[:80]]}
            for i, p in enumerate(paragraphs)
        ]
        return FreeformOutlineLlmResult(sections=sections, tokens_in=90, tokens_out=60)

    async def catalog_template(
        self,
        *,
        slide_dump_text,
        slide_indexes,
        provider_config,
        model_override=None,
    ):
        """LD-2 fake: deterministic-shape catalog. A slide whose dump text
        contains a `[picture]` shape and no `[text]` shape is classified
        `usable=False` (an image library / pure decoration); every other
        slide gets one `title` anchor (its first `[text]` shape id found in
        the dump) plus, when a second `[text]` shape exists, one
        `item_1_body` anchor -- enough structure for a test to assert
        `catalog_template()` never invents an anchor id absent from the dump,
        without depending on real model output."""
        from src.deck.catalog import CatalogLlmResult

        self.calls.append("catalog_template")
        designs = []
        blocks = slide_dump_text.split("\n\nSLIDE ")
        for i, block in enumerate(blocks):
            text = block if i == 0 else "SLIDE " + block
            idx = slide_indexes[i] if i < len(slide_indexes) else None
            if idx is None:
                continue
            shape_lines = [
                line for line in text.splitlines() if line.strip().startswith("shape ")
            ]
            text_ids = [
                line.split()[1] for line in shape_lines if "[text" in line and 'text="' in line
            ]
            has_picture = any("[picture" in line for line in shape_lines)
            if not text_ids:
                designs.append(
                    {
                        "slide_index": idx,
                        "role": "logo_library" if has_picture else "blank",
                        "usable": False,
                        "reason": "no replaceable text content on this slide",
                        "anchors": [],
                    }
                )
                continue
            anchors = [{"anchor_id": text_ids[0], "purpose": "title"}]
            if len(text_ids) > 1:
                anchors.append({"anchor_id": text_ids[1], "purpose": "item_1_body"})
            designs.append(
                {
                    "slide_index": idx,
                    "role": "cover" if i == 0 else "bullets",
                    "usable": True,
                    "reason": None,
                    "anchors": anchors,
                }
            )
        return CatalogLlmResult(raw_designs=designs, tokens_in=200, tokens_out=120)

    async def plan_deck(
        self,
        *,
        content,
        catalog,
        n_slides_hint,
        tone,
        density,
        language,
        provider_config,
        model_override=None,
    ):
        """LD-6 fake: one slide per non-empty paragraph, cycling through the
        catalog's usable designs so a test can assert `plan_deck()` never
        emits a `design_id` or `anchor_id` absent from the catalog it was
        given, without depending on real model output. Writes into the
        FIRST anchor of the chosen design only -- deliberately partial (real
        content rarely fills every anchor), which exercises the
        "skip anchors with nothing to say" path in `deck/plan.py`."""
        from src.deck.plan import PlanLlmResult

        self.calls.append("plan_deck")
        usable = [d for d in catalog if d.get("anchors")]
        if not usable:
            return PlanLlmResult(raw_slides=[], notes=None, tokens_in=80, tokens_out=0)

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()] or [content.strip() or "Presentation"]
        slides = []
        for i, paragraph in enumerate(paragraphs):
            design = usable[i % len(usable)]
            first_anchor = design["anchors"][0]["anchor_id"]
            slides.append({"design_id": design["design_id"], "anchor_texts": {first_anchor: paragraph[:200]}})
        return PlanLlmResult(raw_slides=slides, notes=f"planned {len(slides)} slide(s)", tokens_in=220, tokens_out=140)

    async def chat(
        self,
        *,
        system: str,
        user: str,
        provider_config: dict[str, Any],
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        model_override: str | None = None,
    ):
        """Grounded completion fake. Returns a JSON question array when the prompt
        asks for questions, otherwise a plain grounded answer/summary."""
        from src.engines.llm import ChatAnswer

        self.calls.append("chat")
        self.chat_models.append(model_override or provider_config.get("model"))
        self.max_tokens_seen.append(max_tokens)
        # "JSON" alone: guide's suggested-questions prompt asks for STRICT JSON, but
        # chat's OWN system prompt ("You answer questions strictly...") also contains
        # the word "question" -- `or "question" in system.lower()` used to match that
        # too, so every ordinary chat answer silently came back as the JSON array
        # instead of prose. Harmless while tests only asserted `content` was truthy,
        # but it would have hidden real answer content in any test that checked it.
        if "JSON" in system:
            text = '["What drove revenue growth?", "What are the key risks?", "What is the outlook?"]'
            return ChatAnswer(text=text, tokens_in=100, tokens_out=50)

        self._answer_calls += 1
        if self._truncate_first_answer and self._answer_calls == 1:
            return ChatAnswer(
                text="Revenue grew 12% YoY, driven mainly by",
                tokens_in=100,
                tokens_out=50,
                truncated=True,
            )
        if "continuing" in system.lower():
            text = "the launch of the new product line in Q3."
        else:
            text = "Grounded overview: revenue grew 12% YoY based on the sources."
        return ChatAnswer(text=text, tokens_in=100, tokens_out=50)
