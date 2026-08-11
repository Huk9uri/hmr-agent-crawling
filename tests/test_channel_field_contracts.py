import json
from pathlib import Path

from hmr_order_collection.database import TABLES


CONTRACT_PATH = Path(__file__).parent / "fixtures" / "channel_field_contracts.json"
CLASSIFICATIONS = {"stored", "masked", "structural", "transport"}
EVIDENCE = {"official", "sample", "live"}
SQL_TYPES = {
    "bigint",
    "bit",
    "date",
    "datetime2(3)",
    "decimal(19,4)",
    "int",
    "nvarchar(100)",
    "nvarchar(500)",
    "nvarchar(max)",
}


def contracts():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_field_contract_entries_are_complete_and_supported():
    entries = contracts()
    assert {entry["channel"] for entry in entries} == set(TABLES)
    for entry in entries:
        assert entry["response_path"].strip()
        assert entry["classification"] in CLASSIFICATIONS
        assert entry["evidence"] in EVIDENCE
        assert entry["sql_type"] in SQL_TYPES
        assert isinstance(entry["nullable"], bool)
        if entry["classification"] == "stored":
            assert entry["column"].strip()


def test_every_stored_contract_column_is_writable():
    for entry in contracts():
        if entry["classification"] == "stored":
            assert entry["column"] in TABLES[entry["channel"]].columns
