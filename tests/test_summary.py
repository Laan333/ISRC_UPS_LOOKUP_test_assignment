from app.schemas.lookup import ProviderEntry, SummaryBlock
from app.summary import build_summary


def test_summary_none_found() -> None:
    s = build_summary(
        [
            ProviderEntry(provider="a", found=False, error="timeout"),
            ProviderEntry(provider="b", found=False),
        ]
    )
    assert s == SummaryBlock(found_in=0, confidence="low", note=None)


def test_summary_single_found() -> None:
    s = build_summary([ProviderEntry(provider="a", found=True, title="X", artist="Y")])
    assert s.found_in == 1 and s.confidence == "medium"


def test_summary_two_agree() -> None:
    s = build_summary(
        [
            ProviderEntry(provider="a", found=True, title="Same", artist="Art"),
            ProviderEntry(provider="b", found=True, title="Same", artist="Art"),
        ]
    )
    assert s.found_in == 2 and s.confidence == "high"


def test_summary_two_disagree_titles() -> None:
    s = build_summary(
        [
            ProviderEntry(provider="a", found=True, title="One", artist="A"),
            ProviderEntry(provider="b", found=True, title="Two", artist="A"),
        ]
    )
    assert s.found_in == 2 and s.confidence == "low"
    assert s.note is not None
