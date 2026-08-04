from shared.contracts import Capability, ProviderId
from shared.errors import PlatformError
from api.providers import ProviderClient, SPECS
import pytest


def test_all_seven_providers_are_declared():
    assert set(SPECS) == set(ProviderId)


def test_search_is_not_inferred_from_openai_compatibility():
    search = {provider for provider, spec in SPECS.items() if Capability.WEB_SEARCH in spec.capabilities}
    assert search == {ProviderId.OPENAI, ProviderId.QWEN}


@pytest.mark.parametrize("provider", list(ProviderId))
def test_provider_endpoint_is_pinned_to_audited_official_origin(provider):
    expected = SPECS[provider].default_base_url
    assert ProviderClient.resolve_base_url(provider, "") == expected
    assert ProviderClient.resolve_base_url(provider, expected + "/") == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000",
        "http://169.254.169.254/latest/meta-data",
        "https://api.openai.com.attacker.test/v1",
        "https://user:password@api.openai.com/v1",
    ],
)
def test_custom_provider_endpoint_is_rejected(url):
    with pytest.raises(PlatformError) as error:
        ProviderClient.resolve_base_url(ProviderId.OPENAI, url)
    assert error.value.code == "provider_endpoint_not_allowed"
