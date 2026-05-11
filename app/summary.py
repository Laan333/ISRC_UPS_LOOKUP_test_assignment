from app.normalize import norm_compare
from app.schemas.lookup import ProviderEntry, SummaryBlock


def build_summary(providers: list[ProviderEntry]) -> SummaryBlock:
    found_entries = [p for p in providers if p.found]
    found_in = len(found_entries)

    if found_in == 0:
        return SummaryBlock(found_in=0, confidence="low", note=None)

    if found_in == 1:
        return SummaryBlock(found_in=1, confidence="medium", note=None)

    titles = [norm_compare(p.title) for p in found_entries if p.title]
    artists = [norm_compare(p.artist) for p in found_entries if p.artist]

    title_agree = len(titles) >= 2 and bool(titles[0]) and all(t == titles[0] for t in titles)
    artist_agree = len(artists) < 2 or (
        bool(artists[0]) and all(a == artists[0] for a in artists)
    )

    if title_agree and artist_agree:
        return SummaryBlock(found_in=found_in, confidence="high", note=None)

    if title_agree or (not titles and artist_agree):
        return SummaryBlock(
            found_in=found_in,
            confidence="medium",
            note="Partial agreement between providers.",
        )

    return SummaryBlock(
        found_in=found_in,
        confidence="low",
        note="Metadata differs across providers.",
    )
