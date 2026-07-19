"""
Tests de main._apply_env_overrides: los secretos de GitHub Actions llegan
por variables de entorno y deben tener prioridad sobre config.yaml, además
de activar el canal automáticamente.
"""
import main


def _base_cfg():
    return {
        "notifications": {
            "discord": {"enabled": False, "webhook_url": "https://discord.com/api/webhooks/TU_WEBHOOK_AQUI"},
            "telegram": {"enabled": False, "bot_token": "TU_BOT_TOKEN_AQUI", "chat_id": "TU_CHAT_ID_AQUI"},
        }
    }


def test_discord_webhook_env_overrides_and_enables(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/real/token")
    cfg = _base_cfg()
    main._apply_env_overrides(cfg)

    assert cfg["notifications"]["discord"]["webhook_url"] == "https://discord.com/api/webhooks/real/token"
    assert cfg["notifications"]["discord"]["enabled"] is True


def test_telegram_needs_both_token_and_chat_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "real-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    cfg = _base_cfg()
    main._apply_env_overrides(cfg)

    # Sin chat_id no debe activar ni sobreescribir a medias.
    assert cfg["notifications"]["telegram"]["bot_token"] == "TU_BOT_TOKEN_AQUI"
    assert cfg["notifications"]["telegram"]["enabled"] is False


def test_no_env_vars_leaves_config_untouched(monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    cfg = _base_cfg()
    main._apply_env_overrides(cfg)

    assert cfg["notifications"]["discord"]["enabled"] is False
    assert cfg["notifications"]["telegram"]["enabled"] is False
