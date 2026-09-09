from __future__ import annotations


def build_retrieval_silver_rows(
    candidates: list[dict[str, str]], labels: list[dict[str, str]]
) -> list[dict[str, str]]:
    candidate_by_key = {(row["profile_id"], row["call_id"]): row for row in candidates}
    label_by_key = {(row["profile_id"], row["call_id"]): row for row in labels}
    if len(candidate_by_key) != len(candidates) or len(label_by_key) != len(labels):
        raise ValueError("candidate and label pairs must be unique")
    missing = candidate_by_key.keys() - label_by_key.keys()
    extra = label_by_key.keys() - candidate_by_key.keys()
    if missing or extra:
        raise ValueError(
            f"candidate and label pair sets differ: missing={len(missing)}, extra={len(extra)}"
        )

    output: list[dict[str, str]] = []
    for key in sorted(candidate_by_key):
        candidate = candidate_by_key[key]
        label = label_by_key[key]
        relevance = int(label["relevance"])
        if relevance not in range(4):
            raise ValueError(f"invalid relevance for {key[0]} / {key[1]}")
        provider = label["provider"].strip()
        model = label["model"].strip()
        prompt_version = label["prompt_version"].strip()
        if not provider or not model or not prompt_version:
            raise ValueError(f"missing LLM provenance for {key[0]} / {key[1]}")
        output.append(
            {
                "profile_id": candidate["profile_id"],
                "sector": candidate["sector"],
                "organisation_type": candidate["organisation_type"],
                "project_description": candidate["project_description"],
                "call_id": candidate["call_id"],
                "relevance": str(relevance),
                "annotator": f"{provider}:{model}:{prompt_version}",
                "annotation_round": "initial",
                "notes": (
                    f"LLM silver; confidence={label['confidence']}; "
                    f"needs_human_review={label['needs_human_review']}; "
                    f"rationale={label['rationale']}"
                ),
            }
        )
    return output
