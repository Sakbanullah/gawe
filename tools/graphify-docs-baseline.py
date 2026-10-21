"""Build the documentation graph for Gawe without any LLM or network call.

Only `.md` files are indexed, using graphify's deterministic markdown
extractor. Semantic extraction (concepts, rationale) is deliberately skipped:
it needs an LLM backend, and the project has not approved one.

Usage:
    python tools/graphify-docs-baseline.py [--force]

`--force` allows the new graph to be smaller than the existing one, e.g. after
deleting a document.
"""

import argparse
import json
from pathlib import Path

from graphify.analyze import god_nodes, suggest_questions, surprising_connections
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.detect import detect
from graphify.export import to_json
from graphify.extract import extract
from graphify.report import generate

root = Path(__file__).resolve().parent.parent
out = root / "graphify-out"
out.mkdir(exist_ok=True)

ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true", help="allow a smaller graph than the existing one")
args = ap.parse_args()

detection = detect(root)
(out / ".graphify_detect.json").write_text(json.dumps(detection, indent=2, ensure_ascii=False), encoding="utf-8")

docs = [Path(p) for p in detection["files"].get("document", [])]
if not docs:
    raise SystemExit("No documentation files found.")

ast = extract(docs, cache_root=root, root=root)
(out / ".graphify_ast.json").write_text(json.dumps(ast, indent=2, ensure_ascii=False), encoding="utf-8")

# No semantic pass: keep the shape the merge step expects.
(out / ".graphify_semantic.json").write_text(
    json.dumps({"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}, indent=2),
    encoding="utf-8",
)
extraction = {"nodes": ast["nodes"], "edges": ast["edges"], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
(out / ".graphify_extract.json").write_text(json.dumps(extraction, indent=2, ensure_ascii=False), encoding="utf-8")

G = build_from_json(extraction, root=str(root), directed=False)
if G.number_of_nodes() == 0:
    raise SystemExit("Extraction produced no nodes; refusing to overwrite graph.json.")

communities = cluster(G)
cohesion = score_all(G, communities)
labels = {cid: f"Community {cid}" for cid in communities}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
questions = suggest_questions(G, communities, labels)

if not to_json(G, communities, str(out / "graph.json"), force=args.force):
    raise SystemExit("Refused to shrink graph.json; re-run with --force if intended.")

report = generate(
    G, communities, cohesion, labels, gods, surprises, detection,
    {"input": 0, "output": 0}, str(root), suggested_questions=questions,
)
(out / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
(out / ".graphify_analysis.json").write_text(
    json.dumps(
        {
            "communities": {str(k): v for k, v in communities.items()},
            "cohesion": {str(k): v for k, v in cohesion.items()},
            "gods": gods,
            "surprises": surprises,
            "questions": questions,
        },
        indent=2,
        ensure_ascii=False,
    ),
    encoding="utf-8",
)

print(f"files: {len(docs)} | nodes: {G.number_of_nodes()} | edges: {G.number_of_edges()} | communities: {len(communities)}")
