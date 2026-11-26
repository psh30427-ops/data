from datetime import date

from main import collect, run
from src.collectors import compsniper_collector as provider


def test_fetch_then_analyze_without_mixing_sources(full_import, cards, monkeypatch):
    def item(item_id, **values):
        row = dict(itemId=item_id, title="Pikachu with Grey Felt Hat SVP 085 English PSA 10",
                   listingType="sold", soldCurrency="USD", soldPrice="125.50",
                   endedAt="2025-01-08", bestOfferAccepted=False)
        row.update(values)
        return row

    pages = [
        {"items": [item("1000"), item("1001", bestOfferAccepted=True)], "hasNextPage": True},
        {"items": [item("1000"), item("1002", endedAt="2024-01-01"),
                   item("1003", title="Pikachu with Grey Felt Hat 085 PSA 10 bundle")],
         "hasNextPage": False},
    ]
    calls = []

    def fake_request(path, params):
        calls.append((path, params))
        return pages[params["page"] - 1]

    monkeypatch.setattr(provider, "get_json", fake_request)
    raw = full_import / "data/raw"
    stats = provider.fetch_card(raw, cards[0], date(2025, 1, 1), date(2025, 1, 31), 2)
    assert stats["eligible"] == stats["distinct_dates"] == 1
    assert stats["pages"] == 2
    assert calls[0][1]["soldAfter"] == "2025-01-01"
    assert calls[1][1]["page"] == 2
    assert len(collect(raw).query("source == 'CompSniper'")) == 1
    assert run("all", full_import, "CompSniper") == 0
    report = (full_import / "REPORT.md").read_text(encoding="utf-8")
    assert "CompSniper 실거래 1건" in report
    assert "PSA 실거래 160건" not in report


def test_other_card_requires_explicit_edition(cards):
    row = dict(itemId="123", title="Umbreon VMAX 215/203 PSA 10",
               listingType="sold", soldCurrency="USD", soldPrice="250",
               endedAt="2025-01-08")
    args = (cards[1], date(2025, 1, 1), date(2025, 1, 31), date(2025, 2, 1))
    assert provider.row_from_item(row, *args) is None
    row["title"] += " English"
    assert provider.row_from_item(row, *args)["language"] == "en"
