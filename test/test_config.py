import pytest

from cr_bookmeter.config import get_user_id


def test_user_id_environment_variable_overrides_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('USER_ID="dotenv-user"\n', encoding="utf-8")
    monkeypatch.setenv("USER_ID", "environment-user")

    assert get_user_id(env_file) == "environment-user"


def test_user_id_falls_back_to_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('USER_ID="dotenv-user"\n', encoding="utf-8")
    monkeypatch.delenv("USER_ID", raising=False)

    assert get_user_id(env_file) == "dotenv-user"


def test_user_id_environment_variable_works_without_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_ID", "environment-user")

    assert get_user_id(tmp_path / "missing.env") == "environment-user"


def test_user_id_is_required(tmp_path, monkeypatch):
    monkeypatch.delenv("USER_ID", raising=False)

    with pytest.raises(ValueError, match="USER_ID"):
        get_user_id(tmp_path / "missing.env")
