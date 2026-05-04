# Migrate Telegram Sessions to Telethon

Phase 6 replaces PyroTGFork/Pyrogram with Telethon for both the bot adapter and
the channel-digest userbot. BotFather bot tokens do not need migration, but the
digest userbot `.session` file must be recreated because Telethon uses a
different session format.

## Recreate the digest userbot session

Preferred path:

```text
/init_session
```

The bot asks for your phone contact, sends the Telegram verification code, and
opens the Mini App for OTP and optional 2FA password entry.

CLI fallback:

```bash
python -m app.cli.init_userbot_session
```

The session is stored under `/data/<DIGEST_SESSION_NAME>.session`; the default
name is `/data/digest_userbot.session`.

## Existing session safety

The `/init_session` flow writes to a temporary Telethon session first:

```text
/data/<DIGEST_SESSION_NAME>.telethon_pending.session
```

Only after Telethon authentication succeeds does Ratatoskr move the pending file
into the runtime session path. If an old session file already exists, it is
renamed to:

```text
/data/<DIGEST_SESSION_NAME>.legacy.bak.session
```

If authentication fails, the existing session file is left in place.

## Verify readiness

After creating the session, run:

```bash
python -m app.cli.check_userbot_session
```

The command exits with status `0` when the Telethon session can connect and
`get_me()` succeeds.
