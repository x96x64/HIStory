def test_matches_only_ignores_case_accents_and_an_empty_filter():
    from hist import tags

    assert tags.matches_only("", "Anything")
    assert tags.matches_only("cafe", "Le Café Album")
    assert not tags.matches_only("hits", "Ballads")
