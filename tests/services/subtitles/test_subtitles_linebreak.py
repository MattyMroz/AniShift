from anishift.text.gaps import CONJUNCTIONS


def test_complete_conjunction_list_loaded() -> None:
    assert len(CONJUNCTIONS) == 76
    for word in ("aczkolwiek", "aniżeli", "wszelako", "niżeli", "ilekroć"):
        assert word in CONJUNCTIONS
