import pytest

from supportdesk.rulecheck import RULES


@pytest.mark.parametrize("name, rule", RULES, ids=[name for name, _ in RULES])
def test_rule(name, rule):
    assert rule(), name
