from analyst.contracts import RetrievalPolicy


def select_evidence(rows: list[dict], publishers: list[str], policy: RetrievalPolicy):
    """Policy-controlled selection over an already ranked list; not vector retrieval."""
    if policy.comparison_strategy == "pooled":
        selected = rows[: policy.top_k_per_publisher]
    else:
        selected = []
        for publisher in publishers[:3]:
            selected.extend(
                [row for row in rows if row["publisher"] == publisher][: policy.top_k_per_publisher]
            )
    return selected[:12]
