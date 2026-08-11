from pathlib import Path

from hmr_order_collection.field_dictionary import render_field_dictionary


CONTRACT_PATH = Path(__file__).parent / "fixtures" / "channel_field_contracts.json"


def test_render_field_dictionary_is_grouped_and_stable():
    rendered = render_field_dictionary(CONTRACT_PATH)
    assert rendered.startswith("# 채널별 주문·배송 API 필드 사전\n")
    assert "## 네이버 스마트스토어" in rendered
    assert "## 한촌몰·고도몰(네이버페이 포함)" in rendered
    assert rendered.index("## 네이버 스마트스토어") < rendered.index("## 토스쇼핑")
    assert "`order.orderDate`" in rendered
    assert "`OrderDate`" in rendered
