#!/usr/bin/env python3
"""Dump a large ``/api/v1/graph`` payload as static JSON for the web perf tests.

Why this lives here
-------------------
The frontend perf test in ``web/test/render.perf.test.ts`` needs a graph payload the exact
shape the browser actually receives from ``GET /api/v1/graph`` -- 10,000 people, each already
carrying its computed ``relationships`` and ``seniorityQuestion`` -- so that the layout and
culling functions are measured against a realistic payload rather than a hand-mocked one.

Rather than re-encode that shape by hand (and risk it drifting from the server), this script
reuses the server's OWN serialization: the deterministic generator from
``tests/fixtures/synthetic_tree.py`` (PR #4) builds the graph, and the very functions
``Tree/api/routes.py:graph_view`` uses -- ``relationships``, ``render_english``,
``render_telugu``, ``explain``, ``unresolved_seniority`` and an empty ``Vocabulary`` -- turn it
into the payload. The committed JSON is therefore byte-identical in shape to production.

This script is a DEV CONVENIENCE, not a build step: the committed
``graph_10k.json`` is what the tests load, and regenerating it requires the backend deps
(Flask etc.). It is not run in CI. Regenerate with:

    python3 web/test/fixtures/dump_graph_fixture.py            # default 10k, seed 0
    python3 web/test/fixtures/dump_graph_fixture.py 2000 7     # 2000 people, seed 7

Run from the repository root.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# The generator lives under tests/fixtures on master; import it without modifying it.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))  # so ``Tree`` resolves
sys.path.insert(0, str(_REPO_ROOT / "tests" / "fixtures"))

from synthetic_tree import build_synthetic_family  # noqa: E402

from Tree.kinship.engine import relationships, unresolved_seniority  # noqa: E402
from Tree.kinship.render import explain, render_english, render_telugu  # noqa: E402
from Tree.kinship.vocabulary import Vocabulary  # noqa: E402


def _person_json(person) -> dict:
    """Mirror of Tree/api/routes.py:_person_json."""
    return {
        "id": person.id,
        "given": person.given,
        "surname": person.surname,
        "name": person.full_name,
        "sex": person.sex,
        "birthYear": person.birth_year,
        "deathYear": person.death_year,
        "birth": person.birth_date.to_payload(),
        "death": person.death_date.to_payload(),
        "living": person.living,
    }


def _link_json(kinship, vocab, person_id, show_via: bool) -> dict:
    """Mirror of Tree/api/routes.py:_link_json."""
    term = vocab.apply(render_telugu(kinship), person_id=person_id)
    return {
        "en": render_english(kinship),
        "te": term.text,
        "roman": term.roman,
        "gloss": term.gloss,
        "unresolved": term.unresolved,
        "pinned": term.pinned,
        "bases": list(term.bases),
        "alternatives": list(term.alternatives),
        "adoptive": kinship.adoptive,
        "via": ("Through the adoption" if kinship.adoptive else "By birth") if show_via else None,
        "why": explain(kinship),
        "kind": kinship.kind,
    }


def build_payload(n_people: int, seed: int, side: str = "paternal") -> dict:
    """Build the same dict Tree/api/routes.py:graph_view returns, offline."""
    family = build_synthetic_family(n_people, seed=seed)
    vocab = Vocabulary(side=side)
    root = min(family.people)

    people = []
    open_questions = 0
    for person in sorted(family.people.values(), key=lambda p: p.id):
        links = relationships(family, root, person.id)
        pair = unresolved_seniority(links)
        if pair:
            open_questions += 1
        people.append({
            **_person_json(person),
            "relationships": [
                _link_json(k, vocab, person.id, show_via=len(links) > 1) for k in links
            ],
            "seniorityQuestion": (
                {"a": pair[0], "b": pair[1],
                 "aName": family.people[pair[0]].full_name,
                 "bName": family.people[pair[1]].full_name}
                if pair else None
            ),
        })

    parent_links = [
        {"child": child_id, "parent": link.parent_id, "role": link.role}
        for child_id, links in family.parents.items() for link in links
    ]

    return {
        "Message": "Tree loaded",
        "Root": root,
        "Side": side,
        "People": people,
        "ParentLinks": parent_links,
        "Unions": [{"a": u.a_id, "b": u.b_id} for u in family.unions],
        "Counts": {
            "people": len(family.people),
            "unions": len(family.unions),
            "openBirthOrderQuestions": open_questions,
        },
    }


def main() -> None:
    n_people = int(sys.argv[1]) if len(sys.argv) > 1 else 10_000
    # Seed 5 yields the most tree-like 10k graph the deterministic generator produces
    # (9470 parent links across ~6300 connected people), which best exercises the
    # generation-bucketed layout. Any seed is valid; this one is committed.
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    out = Path(__file__).resolve().parent / f"graph_{n_people // 1000}k.json"
    if n_people < 1000:
        out = Path(__file__).resolve().parent / f"graph_{n_people}.json"

    payload = build_payload(n_people, seed)
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {out} ({len(payload['People'])} people, "
          f"{len(payload['ParentLinks'])} parent links, {len(payload['Unions'])} unions)")


if __name__ == "__main__":
    main()
