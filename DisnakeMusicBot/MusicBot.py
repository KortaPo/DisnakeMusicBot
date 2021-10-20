import json
import pkgutil
import traceback
from traceback import print_exc
from typing import Optional
import disnake
from aiohttp import ClientSession
from disnake import Intents, AllowedMentions
from disnake.ext import commands

from bot_utils.Help_ import HelpCommand


class Bot(commands.AutoShardedBot):
    """A subclass of `commands.AutoShardedBot` with additional features."""

    def __init__(self, *args, **kwargs):
        intents = Intents.all()
        intents.dm_messages = False  # Disabling this Intent will make the Bot not receive DM message events
        with open("./bot_utils/config.json") as f:
            icons = json.load(f)
        icons = icons["ICONS"]

        super().__init__(
            command_prefix="k!",
            intents=intents,
            allowed_mentions=AllowedMentions(everyone=False, users=False, roles=False),
            help_command=HelpCommand(),
            case_insensitive=True,
            reload=True,  # This Kwarg Enables Cog watchdog, Hot reloading of cogs.
            activity=disnake.Game("Music Bot written in Disnake"),
            *args,
            **kwargs,
        )

        self.session: Optional[ClientSession] = None
        with open("./bot_utils/config.json") as f:
            data = json.load(f)

    def load_cogs(self, exts) -> None:
        """Load a set of extensions."""

        for m in pkgutil.iter_modules([exts]):
            # a much better way to load cogs
            module = f"cogs.{m.name}"  # sadly no proper way to do this
            try:
                self.load_extension(module)
                print(f"Loaded extension '{m.name}'")
            except Exception as e:
                traceback.format_exc()
        self.load_extension("jishaku")

    async def login(self, *args, **kwargs) -> None:
        """Create the ClientSession before logging in."""

        self.session = ClientSession()

        await super().login(*args, **kwargs)

    async def on_ready(self):
        print(f"----------Bot Initialization.-------------\n"
              f"Bot name: {self.user.name}\n"
              f"Bot ID: {self.user.id}\n"
              f"Total Guilds: {len(self.guilds)}\n"
              f"Total Users: {len(self.users)}\n"
              f"------------------------------------------")

    async def on_disconnect(self):
        await self.session.close()
