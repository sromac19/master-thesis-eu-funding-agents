from scripts.load_demo_catalog import load_records


def test_demo_catalog_contains_public_current_call_metadata() -> None:
    records = load_records()

    assert len(records) == 8
    assert {record["source"] for record in records} == {"demo_sedia"}
    assert all(
        str(record["official_url"]).startswith("https://ec.europa.eu/") for record in records
    )
    assert all(record["deadline"] is not None for record in records)
