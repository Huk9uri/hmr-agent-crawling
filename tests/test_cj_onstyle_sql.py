from pathlib import Path


SQL_ROOT = Path(__file__).parents[1] / "sql" / "channel_orders"


def test_cj_onstyle_migration_has_history_identity_and_pii_safe_columns():
    sql = (SQL_ROOT / "045_create_cj_onstyle_table.sql").read_text(encoding="utf-8")
    for token in (
        "CJ_ONSTYLE_ORDER_ITEM", "OrderNo", "OrderItemSequence",
        "OrderDetailSequence", "OrderProcessingSequence", "RawJson",
        "PayloadHash", "IsLatest", "CK_CJ_ONSTYLE_ORDER_ITEM_RawJson",
    ):
        assert token in sql
    for pii_column in ("RecipientName ", "Address ", "PostalCode ", "TelephoneNo "):
        assert pii_column not in sql


def test_cj_onstyle_indexes_are_part_of_shared_history_verifier():
    create = (SQL_ROOT / "050_create_channel_order_indexes.sql").read_text(encoding="utf-8")
    verify = (SQL_ROOT / "060_verify_history_constraints.sql").read_text(encoding="utf-8")
    for name in (
        "IX_CJ_ONSTYLE_ORDER_ITEM_CollectionRunId",
        "IX_CJ_ONSTYLE_ORDER_ITEM_Identity_CollectedAt",
        "IX_CJ_ONSTYLE_ORDER_ITEM_Identity_PayloadHash",
        "UX_CJ_ONSTYLE_ORDER_ITEM_Latest",
    ):
        assert name in create
        assert name in verify
