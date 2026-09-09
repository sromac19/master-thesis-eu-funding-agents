from __future__ import annotations

import hashlib
from dataclasses import dataclass
from statistics import fmean

from eu_funding_agents.retrieval.types import SearchDocument


@dataclass(frozen=True)
class CordisBenchmarkQuery:
    project_id: str
    query: str
    relevant_topic_ids: frozenset[str]


def build_topic_documents(topic_rows: list[dict[str, str]]) -> list[SearchDocument]:
    titles: dict[str, str] = {}
    for row in topic_rows:
        topic_id = row.get("topic", "").strip()
        title = row.get("title", "").strip()
        if topic_id and title:
            titles.setdefault(topic_id, title)
    if not titles:
        raise ValueError("CORDIS topic rows contain no usable topic identifiers and titles")
    return [
        SearchDocument(
            call_id=topic_id,
            title=title,
            text=title,
            programme="Horizon Europe",
            official_url="",
        )
        for topic_id, title in sorted(titles.items())
    ]


def select_benchmark_queries(
    project_rows: list[dict[str, str]],
    topic_rows: list[dict[str, str]],
    *,
    sample_size: int,
    seed: int,
) -> list[CordisBenchmarkQuery]:
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    topics_by_project: dict[str, set[str]] = {}
    for row in topic_rows:
        project_id = row.get("projectID", "").strip()
        topic_id = row.get("topic", "").strip()
        title = row.get("title", "").strip()
        if project_id and topic_id and title:
            topics_by_project.setdefault(project_id, set()).add(topic_id)

    candidates: list[CordisBenchmarkQuery] = []
    for row in project_rows:
        project_id = row.get("id", "").strip()
        title = row.get("title", "").strip()
        objective = row.get("objective", "").strip()
        topics = topics_by_project.get(project_id)
        if project_id and objective and topics:
            candidates.append(
                CordisBenchmarkQuery(
                    project_id=project_id,
                    query=f"{title}\n{objective}" if title else objective,
                    relevant_topic_ids=frozenset(topics),
                )
            )
    if len(candidates) < sample_size:
        raise ValueError(
            f"CORDIS snapshot has only {len(candidates)} usable linked projects; "
            f"requested {sample_size}"
        )
    return sorted(
        candidates,
        key=lambda item: hashlib.sha256(f"{seed}:{item.project_id}".encode()).hexdigest(),
    )[:sample_size]


def build_project_disjoint_benchmark(
    project_rows: list[dict[str, str]],
    topic_rows: list[dict[str, str]],
    *,
    sample_size: int,
    seed: int,
    examples_per_topic: int = 4,
    max_example_chars: int = 1200,
    max_query_chars: int = 4000,
) -> tuple[list[SearchDocument], list[CordisBenchmarkQuery]]:
    if min(sample_size, examples_per_topic, max_example_chars, max_query_chars) < 1:
        raise ValueError("benchmark size and text limits must be positive")

    projects = {
        row.get("id", "").strip(): (
            row.get("title", "").strip(),
            row.get("objective", "").strip(),
        )
        for row in project_rows
        if row.get("id", "").strip() and row.get("objective", "").strip()
    }
    topic_titles: dict[str, str] = {}
    topics_by_project: dict[str, set[str]] = {}
    projects_by_topic: dict[str, set[str]] = {}
    for row in topic_rows:
        project_id = row.get("projectID", "").strip()
        topic_id = row.get("topic", "").strip()
        topic_title = row.get("title", "").strip()
        if project_id not in projects or not topic_id or not topic_title:
            continue
        topic_titles.setdefault(topic_id, topic_title)
        topics_by_project.setdefault(project_id, set()).add(topic_id)
        projects_by_topic.setdefault(topic_id, set()).add(project_id)

    eligible = [
        project_id
        for project_id, topics in topics_by_project.items()
        if topics and all(len(projects_by_topic[topic_id]) >= 2 for topic_id in topics)
    ]
    ordered = sorted(
        eligible,
        key=lambda project_id: hashlib.sha256(f"{seed}:{project_id}".encode()).hexdigest(),
    )
    test_ids: set[str] = set()
    selected_per_topic: dict[str, int] = {}
    for project_id in ordered:
        topics = topics_by_project[project_id]
        if any(
            selected_per_topic.get(topic_id, 0) >= len(projects_by_topic[topic_id]) - 1
            for topic_id in topics
        ):
            continue
        test_ids.add(project_id)
        for topic_id in topics:
            selected_per_topic[topic_id] = selected_per_topic.get(topic_id, 0) + 1
        if len(test_ids) == sample_size:
            break
    if len(test_ids) < sample_size:
        raise ValueError(
            f"CORDIS snapshot supports only {len(test_ids)} project-disjoint test queries; "
            f"requested {sample_size}"
        )

    documents: list[SearchDocument] = []
    for topic_id, topic_title in sorted(topic_titles.items()):
        training_ids = sorted(
            projects_by_topic[topic_id] - test_ids,
            key=lambda project_id: hashlib.sha256(
                f"{seed}:{topic_id}:{project_id}".encode()
            ).hexdigest(),
        )[:examples_per_topic]
        if not training_ids:
            continue
        examples = [
            f"{projects[project_id][0]}\n{projects[project_id][1]}"[:max_example_chars]
            for project_id in training_ids
        ]
        documents.append(
            SearchDocument(
                call_id=topic_id,
                title=topic_title,
                text="\n".join([topic_title, *examples]),
                programme="Horizon Europe",
                official_url="",
            )
        )

    queries = [
        CordisBenchmarkQuery(
            project_id=project_id,
            query="\n".join(projects[project_id])[:max_query_chars],
            relevant_topic_ids=frozenset(topics_by_project[project_id]),
        )
        for project_id in sorted(test_ids)
    ]
    return documents, queries


def linked_topic_metrics(
    rankings: list[tuple[CordisBenchmarkQuery, list[str]]],
) -> dict[str, float]:
    if not rankings:
        raise ValueError("rankings must not be empty")
    reciprocal_ranks: list[float] = []
    first_ranks: list[int | None] = []
    for query, ranked_ids in rankings:
        first_rank = next(
            (
                rank
                for rank, topic_id in enumerate(ranked_ids, start=1)
                if topic_id in query.relevant_topic_ids
            ),
            None,
        )
        first_ranks.append(first_rank)
        reciprocal_ranks.append(1.0 / first_rank if first_rank is not None else 0.0)
    return {
        "hit_rate_at_1": fmean(rank == 1 for rank in first_ranks),
        "hit_rate_at_5": fmean(rank is not None and rank <= 5 for rank in first_ranks),
        "hit_rate_at_10": fmean(rank is not None and rank <= 10 for rank in first_ranks),
        "mrr_at_100": fmean(reciprocal_ranks),
    }
