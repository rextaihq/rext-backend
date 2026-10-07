"""A proof for rext-control task 767, never to be merged: one test that fails on purpose, so the
pull request's Tests check has to turn red now that the step is blocking."""


def test_this_fails_on_purpose():
    assert 1 + 1 == 3, "the Tests check must be red for this pull request"
