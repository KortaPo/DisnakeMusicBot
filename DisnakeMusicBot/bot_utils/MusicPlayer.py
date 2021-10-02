import asyncio
import copy
import functools
import itertools
import random
import disnake
import humanize
import youtube_dl as ydl
from async_timeout import timeout
from bot_utils.menus import Menu, MenuPages, button
from disnake.ext import commands

ydl.utils.bug_reports_message = lambda: ''
"""Shutting up annoying errors"""


class VoiceError(Exception):
    """Error raised when something fails while playing audio"""
    pass


class YoutubeSourceError(Exception):
    """Error raised when youtube_dl cannot find the requested video from youtube"""
    pass


class YoutubeSource(disnake.PCMVolumeTransformer):
    """Main Class that searches for youtube videos and creates an audio source"""
    YoutubeOptions = {
        'format': 'bestaudio/best',
        'extractaudio': True,
        'audioformat': 'mp3',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': True,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn',
    }

    ytdl = ydl.YoutubeDL(YoutubeOptions)

    def __init__(self, ctx: commands.Context, source: disnake.FFmpegPCMAudio, *, data: dict, volume: float = 0.5):
        super().__init__(source, volume)

        self.requester = ctx.author
        self.channel = ctx.channel
        self.data = data
        self.uploader = data.get('uploader')
        self.uploader_url = data.get('uploader_url')
        date = data.get('upload_date')
        self.upload_date = date[6:8] + '.' + date[4:6] + '.' + date[0:4]
        self.title = data.get('title')
        self.thumbnail = data.get('thumbnail')
        self.description = data.get('description')
        self.duration = self.parse_duration(int(data.get('duration')))
        self.tags = data.get('tags')
        self.url = data.get('webpage_url')
        self.views = data.get('view_count')
        self.likes = data.get('like_count')
        self.dislikes = data.get('dislike_count')
        self.stream_url = data.get('url')

    def __str__(self):
        return f"**`{self.title}`** by **`{self.uploader}`**"

    @classmethod
    async def song_source(cls, ctx: commands.Context, search: str, *, loop: asyncio.BaseEventLoop = None):
        loop = loop or asyncio.get_event_loop()

        partial = functools.partial(cls.ytdl.extract_info, search, download=False, process=False)
        data = await loop.run_in_executor(None, partial)

        if data is None:
            raise YoutubeSourceError(f"Couldn't find anything that matches `{search}`")

        if 'entries' not in data:
            process_info = data
        else:
            process_info = None
            for entry in data['entries']:
                if entry:
                    process_info = entry
                    break

            if process_info is None:
                raise YoutubeSourceError(f"Couldn't find anything that matches `{search}`")

        webpage_url = process_info['webpage_url']
        partial = functools.partial(cls.ytdl.extract_info, webpage_url, download=False)
        processed_info = await loop.run_in_executor(None, partial)

        if processed_info is None:
            raise YoutubeSourceError(f"Couldn't fetch `{search}`")

        if 'entries' not in processed_info:
            info = processed_info
        else:
            info = None
            while info is None:
                try:
                    info = processed_info['entries'].pop(0)
                except IndexError:
                    raise YoutubeSourceError(f"Couldn't retrieve any matches for `{webpage_url}`")

        return cls(ctx, disnake.FFmpegPCMAudio(info['url'], **cls.FFMPEG_OPTIONS), data=info)

    @staticmethod
    def parse_duration(duration: int):
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)

        duration = []
        if days > 0:
            duration.append(f"{days} days")
        if hours > 0:
            duration.append(f"{hours} hours")
        if minutes > 0:
            duration.append(f"{minutes} minutes")
        if seconds > 0:
            duration.append(f"{seconds} seconds")
        else:
            duration.append("Live Stream")

        return ', '.join(duration)


class Song:
    __slots__ = ('source', 'requester')

    def __init__(self, source: YoutubeSource):
        self.source = source
        self.requester = source.requester

    def create_embed(self):
        em = (disnake.Embed(description=f"```yaml\n{self.source.title}\n```", color=disnake.Color.blurple())
              .add_field(name='Duration', value=f"`{self.source.duration}`", inline=True)
              .add_field(name=' Requested by', value=self.requester.mention, inline=True)
              .add_field(name='Artist',
                         value=f"[{self.source.uploader}]({self.source.uploader_url})")
              .add_field(name="Total Views",
                         value=f"`{humanize.intword(self.source.views)}`")
              .add_field(name="Total Likes",
                         value=f"`{humanize.intword(self.source.likes)}`")
              .add_field(name="Total Dislikes",
                         value=f"`{humanize.intword(self.source.dislikes)}`")
              .set_thumbnail(url=self.source.thumbnail)
              .add_field(name='Volume', value=f'**`{self.source.volume}%`**')
              .set_footer(text=f"Requested by {self.requester.name}",
                          icon_url=f"{self.requester.avatar.url}"))

        return em


class Queue(asyncio.Queue):
    """Custom Queue Class"""

    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(itertools.islice(self._queue, item.start, item.stop, item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]


class InteractiveSongMenu(Menu):
    """Interactive song menu class."""

    def __init__(self, *, embed: disnake.Embed, player):
        super().__init__(timeout=None)

        self.embed = embed
        self.player = player

    def update_context(self, payload: disnake.RawReactionActionEvent):
        """Update our context with the user who reacted."""
        ctx = copy.copy(self.ctx)
        ctx.author = payload.member

        return ctx

    def reaction_check(self, payload: disnake.RawReactionActionEvent):
        if payload.event_type == 'REACTION_REMOVE':
            return False

        if not payload.member:
            return False
        if payload.member.bot:
            return False
        if payload.message_id != self.message.id:
            return False
        if payload.member not in self.bot.get_channel(int(self.player.channel.id)).members:
            return False

        return payload.emoji in self.buttons

    async def send_initial_message(self, ctx: commands.Context, channel: disnake.TextChannel) -> disnake.Message:
        return await channel.send(embed=self.embed)

    @button(emoji='\u25B6')
    async def resume_command(self, payload: disnake.RawReactionActionEvent):
        """Resume button."""
        ctx = self.update_context(payload)

        command = self.bot.get_command('resume')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='\u23F8')
    async def pause_command(self, payload: disnake.RawReactionActionEvent):
        """Pause button"""
        ctx = self.update_context(payload)

        command = self.bot.get_command('pause')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='\u23F9')
    async def stop_command(self, payload: disnake.RawReactionActionEvent):
        """Stop button."""
        ctx = self.update_context(payload)

        command = self.bot.get_command('stop')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='\u23ED')
    async def skip_command(self, payload: disnake.RawReactionActionEvent):
        """Skip button."""
        ctx = self.update_context(payload)

        command = self.bot.get_command('skip')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='\U0001F500')
    async def shuffle_command(self, payload: disnake.RawReactionActionEvent):
        """Shuffle button."""
        ctx = self.update_context(payload)

        command = self.bot.get_command('shuffle')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='🔊')
    async def volume(self, payload: disnake.RawReactionActionEvent):
        """Volume button"""
        ctx = self.update_context(payload)

        command = self.bot.get_command('vol')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='🔁')
    async def loop(self, payload: disnake.RawReactionActionEvent):
        """Loop button"""
        ctx = self.update_context(payload)

        command = self.bot.get_command('loop')
        ctx.command = command

        await self.bot.invoke(ctx)

    @button(emoji='\U0001F1F6')
    async def queue_command(self, payload: disnake.RawReactionActionEvent):
        """Player queue button."""
        ctx = self.update_context(payload)

        command = self.bot.get_command('queue')
        ctx.command = command

        await self.bot.invoke(ctx)


class VoiceState:
    """Custom VoiceState Class"""

    def __init__(self, bot, ctx: commands.Context):
        self.bot = bot
        self._ctx = ctx
        self.channel = ctx.channel
        self.invoker = ctx.author
        self.current = None
        self.updating = False
        self.waiting = False
        self.voice = None
        self.next = asyncio.Event()
        self.songs = Queue()
        self.player_menu = None

        self._loop = False
        self.volume = 0.5
        self.skip_votes = set()

        self.audio_player = bot.loop.create_task(self.audio_player_task())

    def __del__(self):
        self.audio_player.cancel()

    @property
    def loop(self):
        return self._loop

    @loop.setter
    def loop(self, value: bool = False):
        self._loop = value

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value: float):
        self._volume = value

    @property
    def is_playing(self):
        return self.voice and self.current

    async def is_menu_available(self) -> bool:
        """Method which checks whether the song should be remade or updated."""
        try:
            async for message in self._ctx.channel.history(limit=5):
                if message.id == self.player_menu.message.id:
                    return True
        except (disnake.HTTPException, AttributeError):
            return False

        return False

    async def audio_player_task(self):
        """Task that searches and plays audio"""
        while True:
            self.next.clear()

            if not self.loop:
                try:
                    async with timeout(180):  # 3 minutes
                        self.current = await self.songs.get()
                except asyncio.TimeoutError:  # if no music playing for 3 minutes, stop the player
                    self.bot.loop.create_task(self.stop())
                    return

            self.current.source.volume = self.volume
            self.voice.play(self.current.source, after=self.play_next_song)

            if self.updating:
                return

            self.updating = True

            if not self.player_menu:
                self.player_menu = InteractiveSongMenu(embed=self.current.create_embed(), player=self._ctx)
                await self.player_menu.start(self._ctx)

            elif not await self.is_menu_available():
                try:
                    await self.player_menu.message.delete()
                except disnake.HTTPException:
                    pass

                self.player_menu.stop()

                self.player_menu = InteractiveSongMenu(embed=self.current.create_embed(), player=self._ctx)
                await self.player_menu.start(self._ctx)

            else:
                embed = self.current.create_embed()
                await self.player_menu.message.edit(embed=embed)
            self.updating = False
            await self.next.wait()

    def play_next_song(self, error=None):
        if error:
            raise VoiceError(str(error))

        self.next.set()

    def skip(self):
        self.skip_votes.clear()

        if self.is_playing:
            self.voice.stop()

    async def stop(self):
        self.songs.clear()
        self.player_menu.stop()
        await self.player_menu.message.clear_reactions()

        if self.voice:
            await self.voice.disconnect()
            self.voice = None
