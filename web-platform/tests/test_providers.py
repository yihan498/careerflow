from shared.contracts import Capability, ProviderId
from api.providers import SPECS


def test_all_seven_providers_are_declared():
    assert set(SPECS) == set(ProviderId)


def test_search_is_not_inferred_from_openai_compatibility():
    search = {provider for provider, spec in SPECS.items() if Capability.WEB_SEARCH in spec.capabilities}
    assert search == {ProviderId.OPENAI, ProviderId.QWEN}

