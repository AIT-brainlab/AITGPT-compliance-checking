"""Align pipeline rules (AIT-xxxx) to gold shapes (GS-xxx) by rule text similarity."""
from __future__ import annotations
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional

from rdflib import Graph, Namespace, RDF, RDFS
from rdflib.namespace import SH

PROJECT_ROOT = Path(__file__).parent.parent
AIT = Namespace("http://example.org/ait-policy#")
DEONTIC = Namespace("http://example.org/deontic#")

@dataclass
class GoldRule:
    gs_id: str                  # "GS-001"
    text: str                   # rdfs:comment
    deontic_type: str           # "obligation" | "permission" | "prohibition"
    target_class: str
    shape_uri: str              # full URI of the sh:NodeShape

@dataclass
class Alignment:
    gs_id: str
    ait_id: Optional[str]       # None = unmatched
    pipeline_text: Optional[str]
    embedding_score: float
    tfidf_score: float
    fuzz_score: float
    aligned: bool               # passed primary threshold


def load_gold_rules(shapes_file: Path) -> List[GoldRule]:
    g = Graph()
    g.parse(str(shapes_file), format="turtle")

    rules: List[GoldRule] = []
    for shape in g.subjects(RDF.type, SH.NodeShape):
        label = g.value(shape, RDFS.label)
        comment = g.value(shape, RDFS.comment)
        target = g.value(shape, SH.targetClass)
        dtype = g.value(shape, DEONTIC.type)

        if not (label and comment and target):
            continue
        rules.append(GoldRule(
            gs_id=str(label),
            text=str(comment),
            deontic_type=_dtype_label(dtype),
            target_class=str(target).split("#")[-1],
            shape_uri=str(shape),
        ))
    return rules


def _dtype_label(dtype) -> str:
    if dtype is None:
        return "unknown"
    frag = str(dtype).split("#")[-1]
    return {"obligation": "obligation",
            "permission": "permission",
            "prohibition": "prohibition"}.get(frag, "unknown")


def load_pipeline_rules(classified_json: Path) -> list[dict]:
    return json.loads(classified_json.read_text(encoding="utf-8"))


def align_all(gold: List[GoldRule],
              pipeline: list[dict],
              threshold: float = 0.65) -> List[Alignment]:
    from sentence_transformers import SentenceTransformer, util
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from rapidfuzz import fuzz
    import numpy as np

    # --- Embeddings ---
    model = SentenceTransformer("all-MiniLM-L6-v2")
    gold_vecs = model.encode([g.text for g in gold], convert_to_tensor=True)
    pipe_vecs = model.encode([r["text"] for r in pipeline], convert_to_tensor=True)
    emb_sim = util.cos_sim(gold_vecs, pipe_vecs).cpu().numpy()  # shape (|gold|, |pipe|)

    # --- TF-IDF ---
    vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", lowercase=True)
    all_docs = [g.text for g in gold] + [r["text"] for r in pipeline]
    tfidf = vec.fit_transform(all_docs)
    tfidf_sim = cosine_similarity(tfidf[: len(gold)], tfidf[len(gold):])

    alignments: List[Alignment] = []
    for i, gr in enumerate(gold):
        # primary: embeddings
        j = int(np.argmax(emb_sim[i]))
        emb_score = float(emb_sim[i, j])
        tfidf_score = float(tfidf_sim[i, j])
        fuzz_score = float(fuzz.token_set_ratio(gr.text, pipeline[j]["text"])) / 100.0

        aligned = emb_score >= threshold
        alignments.append(Alignment(
            gs_id=gr.gs_id,
            ait_id=pipeline[j]["rule_id"] if aligned else None,
            pipeline_text=pipeline[j]["text"] if aligned else None,
            embedding_score=emb_score,
            tfidf_score=tfidf_score,
            fuzz_score=fuzz_score,
            aligned=aligned,
        ))
    return alignments


def main() -> None:
    shapes = PROJECT_ROOT / "shacl" / "shapes" / "ait_policy_shapes.ttl"
    classified = PROJECT_ROOT / "output" / "ait" / "classified_rules.json"
    out = PROJECT_ROOT / "output" / "ait" / "gold_alignment.json"

    gold = load_gold_rules(shapes)
    pipeline = load_pipeline_rules(classified)
    alignments = align_all(gold, pipeline)

    coverage = sum(1 for a in alignments if a.aligned) / len(alignments)
    print(f"Extraction coverage (M1): {coverage:.1%} ({sum(1 for a in alignments if a.aligned)}/{len(alignments)})")

    out.write_text(
        json.dumps([asdict(a) for a in alignments], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
