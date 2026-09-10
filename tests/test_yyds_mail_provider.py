"""YYDS Mail provider unit tests."""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock

from core.base_mailbox import YYDSMailMailbox, MailboxAccount, _create_yyds_mail


# ─ 构造辅助 ────────────────────────────────────────────────────────────

def _make_mailbox(**overrides) -> YYDSMailMailbox:
    kwargs = {"api_key": "AC-test123"}
    kwargs.update(overrides)
    return YYDSMailMailbox(**kwargs)


def _fake_response(data: dict, success: bool = True) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"success": success, "data": data}
    resp.raise_for_status = MagicMock()
    resp.text = json.dumps({"success": success, "data": data})
    return resp


# ── 初始化验证 ──────────────────────────────────────────────────────────

class TestYYDSMailInit:
    def test_default_api_url(self):
        mb = _make_mailbox()
        assert mb.api == "https://maliapi.215.im"

    def test_custom_api_url(self):
        mb = _make_mailbox(api_url="https://custom.example.com")
        assert mb.api == "https://custom.example.com"

    def test_missing_api_key_raises(self):
        mb = YYDSMailMailbox(api_key="")
        with pytest.raises(RuntimeError, match="未配置 API Key"):
            mb._assert_ready()

    def test_api_key_stripped(self):
        mb = _make_mailbox(api_key="  AC-test  ")
        assert mb.api_key == "AC-test"


# ─ get_email ──────────────────────────────────────────────────────────

class TestYYDSMailGetEmail:
    @patch("curl_cffi.requests.post")
    def test_create_email_success(self, mock_post):
        mock_post.return_value = _fake_response({
            "id": "inbox_001",
            "address": "test123@zran.cc.cd",
            "token": "temp_token_xyz",
        })
        mb = _make_mailbox()
        account = mb.get_email()
        assert account.email == "test123@zran.cc.cd"
        assert account.account_id == "inbox_001"
        assert (account.extra or {}).get("yyds_mail_token") == "temp_token_xyz"

    @patch("curl_cffi.requests.post")
    def test_create_email_with_domain(self, mock_post):
        mock_post.return_value = _fake_response({
            "id": "inbox_002",
            "address": "user@zran.cc.cd",
            "token": "t",
        })
        mb = _make_mailbox(domain="zran.cc.cd")
        mb.get_email()
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["domain"] == "zran.cc.cd"

    @patch("curl_cffi.requests.post")
    def test_create_email_with_subdomain(self, mock_post):
        mock_post.return_value = _fake_response({
            "id": "inbox_003",
            "address": "user@sub.zran.cc.cd",
            "token": "t",
        })
        mb = _make_mailbox(domain="zran.cc.cd", subdomain="sub")
        mb.get_email()
        call_kwargs = mock_post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["subdomain"] == "sub"

    @patch("curl_cffi.requests.post")
    def test_create_email_api_failure(self, mock_post):
        mock_post.return_value = _fake_response({}, success=False)
        mock_post.return_value.json.return_value = {"success": False, "message": "invalid key"}
        mb = _make_mailbox()
        with pytest.raises(RuntimeError, match="API 失败"):
            mb.get_email()


# ── get_current_ids ─────────────────────────────────────────────────────

class TestYYDSMailGetCurrentIds:
    @patch("curl_cffi.requests.get")
    def test_returns_message_ids(self, mock_get):
        mock_get.return_value = _fake_response({
            "messages": [
                {"id": "msg_1", "subject": "Hello"},
                {"id": "msg_2", "subject": "World"},
            ],
            "total": 2,
        })
        mb = _make_mailbox()
        account = MailboxAccount(
            email="test@zran.cc.cd",
            extra={"yyds_mail_address": "test@zran.cc.cd"},
        )
        ids = mb.get_current_ids(account)
        assert ids == {"msg_1", "msg_2"}

    @patch("curl_cffi.requests.get")
    def test_empty_inbox(self, mock_get):
        mock_get.return_value = _fake_response({"messages": [], "total": 0})
        mb = _make_mailbox()
        account = MailboxAccount(email="test@zran.cc.cd", extra={"yyds_mail_address": "test@zran.cc.cd"})
        ids = mb.get_current_ids(account)
        assert ids == set()


# ── wait_for_code ───────────────────────────────────────────────────────

class TestYYDSMailWaitForCode:
    @patch("curl_cffi.requests.get")
    def test_native_verification_code(self, mock_get):
        mock_get.return_value = _fake_response({
            "message": {
                "id": "msg_1",
                "subject": "Verify",
                "text": "Your code is 123456",
                "verificationCode": "123456",
            },
            "inboxAddress": "test@zran.cc.cd",
        })
        mb = _make_mailbox()
        account = MailboxAccount(email="test@zran.cc.cd", extra={"yyds_mail_address": "test@zran.cc.cd"})
        code = mb.wait_for_code(account, timeout=5)
        assert code == "123456"

    @patch("curl_cffi.requests.get")
    def test_fallback_regex_extraction(self, mock_get):
        mock_get.return_value = _fake_response({
            "message": {
                "id": "msg_2",
                "subject": "Code",
                "text": "Your verification code is 654321.",
                "verificationCode": None,
            },
            "inboxAddress": "test@zran.cc.cd",
        })
        mb = _make_mailbox()
        account = MailboxAccount(email="test@zran.cc.cd", extra={"yyds_mail_address": "test@zran.cc.cd"})
        code = mb.wait_for_code(account, timeout=5)
        assert code == "654321"

    @patch("curl_cffi.requests.get")
    def test_timeout_raises(self, mock_get):
        mock_get.return_value = _fake_response({})  # 204 → empty data
        mb = _make_mailbox()
        account = MailboxAccount(email="test@zran.cc.cd", extra={"yyds_mail_address": "test@zran.cc.cd"})
        with pytest.raises(TimeoutError, match="超时"):
            mb.wait_for_code(account, timeout=2)


# ─ wait_for_link ───────────────────────────────────────────────────────

class TestYYDSMailWaitForLink:
    @patch("curl_cffi.requests.get")
    def test_extract_verification_link(self, mock_get):
        mock_get.return_value = _fake_response({
            "message": {
                "id": "msg_3",
                "subject": "Confirm your email",
                "text": "Click here to verify: https://example.com/verify?token=abc123",
                "verificationCode": None,
            },
            "inboxAddress": "test@zran.cc.cd",
        })
        mb = _make_mailbox()
        account = MailboxAccount(email="test@zran.cc.cd", extra={"yyds_mail_address": "test@zran.cc.cd"})
        link = mb.wait_for_link(account, timeout=5)
        assert "example.com/verify" in link


# ── Factory function ────────────────────────────────────────────────────

class TestCreateYYDSMail:
    def test_factory_creates_instance(self):
        extra = {
            "yyds_mail_api_key": "AC-test",
            "yyds_mail_domain": "zran.cc.cd",
        }
        mb = _create_yyds_mail(extra, None)
        assert isinstance(mb, YYDSMailMailbox)
        assert mb.api_key == "AC-test"
        assert mb.domain == "zran.cc.cd"

    def test_factory_with_proxy(self):
        extra = {"yyds_mail_api_key": "AC-test"}
        mb = _create_yyds_mail(extra, "http://proxy:8080")
        assert mb.proxy == {"http": "http://proxy:8080", "https": "http://proxy:8080"}


# ── Registry integration ────────────────────────────────────────────────

class TestYYDSMailRegistry:
    def test_provider_registered(self):
        from providers.registry import load_all, get_provider_class
        load_all()
        cls = get_provider_class("mailbox", "yyds_mail_api")
        assert cls is YYDSMailMailbox

    def test_factory_registry(self):
        from core.base_mailbox import MAILBOX_FACTORY_REGISTRY
        assert "yyds_mail_api" in MAILBOX_FACTORY_REGISTRY
        assert "yyds_mail" in MAILBOX_FACTORY_REGISTRY
