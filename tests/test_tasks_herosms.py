from __future__ import annotations

from application.tasks import _resolve_sms_provider_for_task
from infrastructure.provider_settings_repository import ProviderSettingsRepository


def test_resolve_sms_provider_for_task_uses_saved_herosms_default():
    repo = ProviderSettingsRepository()
    repo.save(
        setting_id=None,
        provider_type="sms",
        provider_key="herosms",
        display_name="HeroSMS",
        auth_mode="api_key",
        enabled=True,
        is_default=True,
        config={
            "sms_service": "dr",
            "sms_country": "187",
            "register_phone_extra_max": "3",
        },
        auth={"herosms_api_key": "hero123"},
        metadata={},
    )

    provider_key, settings = _resolve_sms_provider_for_task({})

    assert provider_key == "herosms"
    assert settings["herosms_api_key"] == "hero123"
    assert settings["sms_service"] == "dr"


def test_resolve_sms_provider_for_task_allows_inline_override():
    provider_key, settings = _resolve_sms_provider_for_task({
        "sms_provider": "herosms",
        "herosms_api_key": "inline",
        "sms_country": "52",
    })

    assert provider_key == "herosms"
    assert settings["herosms_api_key"] == "inline"
    assert settings["sms_country"] == "52"
