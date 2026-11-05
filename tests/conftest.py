import importlib.util

# The Discord bot is optional (requirements-bot.txt). Without discord.py
# installed, skip the bot-layer test modules instead of failing on import.
collect_ignore: list[str] = []
if importlib.util.find_spec("discord") is None:
    collect_ignore += ["test_digest_embed.py", "test_pagination.py"]
