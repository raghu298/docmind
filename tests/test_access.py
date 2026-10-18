from docmind import access
from docmind.access import (LIVE_REQUEST_CAP, can_make_live_request, check_access_code,
                            next_count, owner_access_configured, resolve_key, resolve_key_source)

OWNER = "sk-ant-owner-PLACEHOLDER"
SECRETS = {"ANTHROPIC_API_KEY": OWNER, "ACCESS_CODE": "open-sesame"}


class RaisingSecrets:
    def get(self, k):
        raise FileNotFoundError("no secrets.toml")


def test_owner_access_configured():
    assert owner_access_configured(SECRETS)
    assert not owner_access_configured({"ANTHROPIC_API_KEY": OWNER})
    assert not owner_access_configured({"ANTHROPIC_API_KEY": OWNER, "ACCESS_CODE": "  "})
    assert not owner_access_configured({})
    assert not owner_access_configured(None)
    assert not owner_access_configured(RaisingSecrets())


def test_access_code_right_and_wrong():
    assert check_access_code(SECRETS, "open-sesame")
    assert check_access_code(SECRETS, " open-sesame ")
    assert not check_access_code(SECRETS, "open-sesam")
    assert not check_access_code(SECRETS, "")
    assert not check_access_code(SECRETS, None)
    assert not check_access_code({"ACCESS_CODE": "open-sesame"}, "open-sesame")  # no owner key


def test_resolve_key_priority():
    env = {"ANTHROPIC_API_KEY": "sk-env-PLACEHOLDER"}
    assert resolve_key(SECRETS, "sk-user", True, env) == "sk-user"
    assert resolve_key_source(SECRETS, "sk-user", True, env) == "user"
    assert resolve_key(SECRETS, "", True, env) == OWNER
    assert resolve_key_source(SECRETS, None, True, env) == "owner"
    assert resolve_key(SECRETS, "", False, env) == "sk-env-PLACEHOLDER"
    assert resolve_key(SECRETS, "  ", False, {}) is None
    assert resolve_key_source(SECRETS, "", False, {}) is None


def test_cap():
    assert LIVE_REQUEST_CAP == 20
    count = 0
    for _ in range(LIVE_REQUEST_CAP):
        assert can_make_live_request(count)
        count = next_count(count)
    assert count == 20 and not can_make_live_request(count)


def test_messages_never_contain_key():
    for msg in (access.cap_message(), access.ACCESS_GRANTED_MESSAGE, access.ACCESS_DENIED_MESSAGE):
        assert OWNER not in msg and "sk-" not in msg
    assert "20" in access.cap_message()
