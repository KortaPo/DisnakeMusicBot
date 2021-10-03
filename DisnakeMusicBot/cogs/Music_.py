from youtubesearchpython.__future__ import ChannelsSearch, VideosSearch
import asyncio
import math
import re
import time
import disnake
import humanize
import youtube_dl as ydl
from bot_utils.menus import MenuPages
from disnake.ext import commands
from jishaku.functools import executor_function
from bot_utils.MusicPlayer import VoiceState, YoutubeSource, Song, VoiceError
from bot_utils.checks import is_properly_connected, invoker_or_admin, is_in_same_channel
from bot_utils.paginator import Paginator


@executor_function
def youtube(query, download=False):
    ytdl = ydl.YoutubeDL(
        {"format": "bestaudio/best", "restrictfilenames": True, "noplaylist": True, "nocheckcertificate": True,
         "ignoreerrors": True, "logtostderr": False, "quiet": True, "no_warnings": True, "default_search": "auto",
         "source_address": "0.0.0.0"})
    info = ytdl.extract_info(query, download=download)
    del ytdl
    return info


class Music(commands.Cog):
    """Your friendly Music Bot."""

    def __init__(self, bot):
        self.bot = bot
        self.voice_states = {}

    async def paginate(self, paginator):
        return MenuPages(paginator)

    def get_voice_state(self, ctx: commands.Context):
        state = self.voice_states.get(ctx.guild.id)
        if not state:
            state = VoiceState(self.bot, ctx)
            self.voice_states[ctx.guild.id] = state

        return state

    def cog_unload(self):
        for state in self.voice_states.values():
            self.bot.loop.create_task(state.stop())

    def cog_check(self, ctx: commands.Context):
        if not ctx.guild:
            raise commands.NoPrivateMessage(f"{self.bot.icons['redtick']} This command can't be used in DM channels.")

        return True

    async def cog_before_invoke(self, ctx: commands.Context):
        ctx.voice_state = self.get_voice_state(ctx)

    async def cog_command_error(self, ctx: commands.Context, error: AttributeError):
        if isinstance(error, AttributeError):
            raise commands.errors.CommandError(f"{self.bot.icons['redtick']} You are not "
                                               f"connected to any voice channel")

    @commands.group(invoke_without_command=True, aliases=["yt"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def youtube(self, ctx, *, query):
        if re.search(r"^(https?\:\/\/)?((www\.)?youtube\.com|youtu\.?be)\/.+$", query):
            async with ctx.typing():
                query = (await youtube(query))["title"]

        async with ctx.typing():
            videos = (await (VideosSearch(query, limit=15)).next())["result"]

        if len(videos) == 0:
            return await ctx.reply("I could not find a video with that query", mention_author=False)

        embeds = []

        for video in videos:
            url = "https://www.youtube.com/watch?v=" + video["id"]
            channel_url = "https://www.youtube.com/channel/" + video["channel"]["id"]
            em = disnake.Embed(title=video["title"], url=url, color=disnake.Colour.random())
            em.add_field(name="Channel", value=f"[{video['channel']['name']}]({channel_url})", inline=True)
            em.add_field(name="Duration", value=video['duration'], inline=True)
            em.add_field(name="Views", value=video['viewCount']["text"])
            em.set_footer(
                text=f"Use the reactions for downloading • Page: {int(videos.index(video)) + 1}/{len(videos)}")
            em.set_thumbnail(url=video["thumbnails"][0]["url"])
            embeds.append(em)

        msg = await ctx.reply(embed=embeds[0], mention_author=False)

        page = 0

        reactions = [self.bot.icons["fulleft"], self.bot.icons["left"], self.bot.icons["right"],
                     self.bot.icons["fullright"], self.bot.icons["stop"]]

        for r in reactions:
            await msg.add_reaction(r)

        while True:
            try:
                done, pending = await asyncio.wait([
                    self.bot.wait_for("reaction_add", check=lambda reaction, user: str(
                        reaction.emoji) in reactions and user == ctx.author and reaction.message == msg, timeout=30),
                    self.bot.wait_for("reaction_remove", check=lambda reaction, user: str(
                        reaction.emoji) in reactions and user == ctx.author and reaction.message == msg, timeout=30)
                ], return_when=asyncio.FIRST_COMPLETED)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return

            try:
                reaction, user = done.pop().result()
            except (asyncio.TimeoutError, asyncio.CancelledError):
                return

            for future in pending:
                future.cancel()

            if str(reaction.emoji) == reactions[0]:
                if len(videos) != 1:
                    page = 0
                    await msg.edit(embed=embeds[page])

            elif str(reaction.emoji) == reactions[1]:
                if page != 0:
                    page -= 1
                    await msg.edit(embed=embeds[page])

            elif str(reaction.emoji) == reactions[2]:
                if len(videos) != 1:
                    page += 1
                    await msg.edit(embed=embeds[page])

            elif str(reaction.emoji) == reactions[3]:
                if page != len(videos):
                    page = len(videos) - 1
                    await msg.edit(embed=embeds[page])

            elif str(reaction.emoji) == reactions[4]:
                await msg.delete()
                break

    @youtube.command(aliases=["c"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def channel(self, ctx, *, query):
        async with ctx.typing():
            channels = (await (ChannelsSearch(query, limit=15, region="US")).next())["result"]

        if len(channels) == 0:
            return await ctx.reply(
                embed=disnake.Embed(title="Channel", description="I could not find a channel with that query.",
                                    color=disnake.Colour.random()))

        embeds = []

        for channel in channels:
            url = "https://www.youtube.com/channel/" + channel["id"]
            if not channel['thumbnails'][0]['url'].startswith("https:"):
                thumbnail = f"https:{channel['thumbnails'][0]['url']}"
            else:
                thumbnail = channel['thumbnails'][0]['url']
            if channel["descriptionSnippet"] is not None:
                em = disnake.Embed(title=channel["title"],
                                   description=" ".join(text["text"] for text in channel["descriptionSnippet"]),
                                   url=url, color=disnake.Colour.random())
            else:
                em = disnake.Embed(title=channel["title"], url=url, color=disnake.Colour.random())
            em.add_field(name="Videos",
                         value="".join(channel['videoCount'] if channel['videoCount'] is not None else "0"),
                         inline=True)
            em.add_field(name="Subscribers",
                         value="".join(channel['subscribers'] if channel['subscribers'] is not None else "0"),
                         inline=True)
            em.set_thumbnail(url=thumbnail)
            embeds.append(em)

        pag = await self.paginate(Paginator(embeds, per_page=1))
        await pag.start(ctx)

    @commands.command(aliases=['spot'])
    async def spotify(self, ctx, *, user: disnake.Member):
        if user is None:
            user = ctx.author
        else:
            try:
                user = await commands.MemberConverter().convert(ctx, str(user))
            except BaseException:
                raise disnake.ext.commands.MemberNotFound(str(user))
        activities = user.activities
        try:
            act = [
                activity for activity in activities if isinstance(
                    activity, disnake.Spotify)][0]
        except IndexError:
            return await ctx.send('No spotify was detected')
        start = humanize.naturaltime(disnake.utils.utcnow() - act.created_at)
        print(start)
        name = act.title
        art = " ".join(act.artists)
        album = act.album
        duration = round(((act.end - act.start).total_seconds() / 60), 2)
        min_sec = time.strftime("%M:%S", time.gmtime((act.end - act.start).total_seconds()))
        current = round(
            ((disnake.utils.utcnow() - act.start).total_seconds() / 60), 2)
        min_sec_current = time.strftime("%M:%S", time.gmtime(
            (disnake.utils.utcnow() - act.start).total_seconds()))
        embed = disnake.Embed(color=ctx.guild.me.color)
        embed.set_author(
            name=user.display_name,
            icon_url='https://netsbar.com/wp-content/uploads/2018/10/Spotify_Icon.png')
        embed.description = f"Listening To  [**{name}**] (https://open.spotify.com/track/{act.track_id})"
        embed.add_field(name="Artist", value=art, inline=True)
        embed.add_field(name="Album", value=album, inline=True)
        embed.set_thumbnail(url=act.album_cover_url)
        embed.add_field(name="Started Listening", value=start, inline=True)
        percent = int((current / duration) * 25)
        perbar = f"`{min_sec_current}`| {(percent - 1) * '─'}⚪️{(25 - percent) * '─'} | `{min_sec}`"
        embed.add_field(name="Progress", value=perbar)
        await ctx.send(embed=embed)

    @commands.command(aliases=['Latency'], name='Ping')
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def ping(self, ctx):
        msg = await ctx.send("Gathering Information...")
        times = []
        counter = 0
        embed = disnake.Embed(colour=disnake.Colour.random())
        for _ in range(3):
            counter += 1
            start = time.perf_counter()
            await msg.edit(content=f"Trying Ping{('.' * counter)} {counter}/3")
            end = time.perf_counter()
            speed = round((end - start) * 1000)
            times.append(speed)
            if speed < 160:
                embed.add_field(name=f"Ping {counter}:", value=f"🟢 | {speed}ms", inline=True)
            elif speed > 170:
                embed.add_field(name=f"Ping {counter}:", value=f"🟡 | {speed}ms", inline=True)
            else:
                embed.add_field(name=f"Ping {counter}:", value=f"🔴 | {speed}ms", inline=True)

        embed.add_field(name="Bot Latency", value=f"{round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Normal Speed",
                        value=f"{round((round(sum(times)) + round(self.bot.latency * 1000)) / 4)}ms")

        embed.set_footer(text=f"Total estimated elapsed time: {round(sum(times))}ms")
        embed.set_author(name=ctx.me.display_name, icon_url=ctx.me.avatar)

        await msg.edit(content=f":ping_pong: **{round((round(sum(times)) + round(self.bot.latency * 1000)) / 4)}ms**",
                       embed=embed)

    @commands.command(help="Make me join in a VC", aliases=["j", "summon"], invoke_without_subcommand=True)
    async def join(self, ctx: commands.Context):

        destination = ctx.author.voice.channel
        if ctx.voice_state.voice:
            await ctx.voice_state.voice.move_to(destination)

        ctx.voice_state.voice = await destination.connect()

        em = disnake.Embed(title=f":zzz: Joined in {destination}", color=disnake.Colour.random())
        em.set_footer(text=f"Requested by {ctx.author.name}")
        await ctx.send(embed=em)

    @commands.command(help="Make me leave a VC", aliases=["disconnect", "dc", "fuckoff"])
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def leave(self, ctx: commands.Context):

        dest = ctx.author.voice.channel
        await ctx.voice_state.stop()
        del self.voice_states[ctx.guild.id]
        em = disnake.Embed(title=f":zzz: Disconnected from {dest}", color=disnake.Colour.random())
        em.set_footer(icon_url=ctx.author.avatar.url, text=f"Requested by {ctx.author}")
        await ctx.send(embed=em)

    @commands.command(help="Set the player volume", aliases=["vol"])
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def volume(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        await ctx.send(f"Enter a volume below between 1 -- 150")
        try:
            message = await self.bot.wait_for("message", timeout=20, check=lambda
                m: m.author == ctx.author and m.channel == ctx.channel and m.content.isnumeric())
            volume = int(message.content)
            if volume > 150:
                return await ctx.send(
                    embed=disnake.Embed(description=f"{self.bot.icons['info']} Volume must be between "
                                                    f"**0 and 150**", color=disnake.Colour.random()))
            ctx.voice_state.volume = volume / 150
            em = disnake.Embed(title=f"Volume set at the **`{volume}%`**", color=disnake.Colour.random())
            em.set_footer(icon_url=ctx.author.avatar.url, text=f"Regulated by {ctx.author}")
            await ctx.send(embed=em)
        except asyncio.TimeoutError:
            await ctx.send(
                embed=disnake.Embed(description=f"{self.bot.icons['redtick']} You didn't provide volume in time",
                                    color=disnake.Colour.blurple()))

    @commands.Cog.listener(name="on_voice_state_update")  # If there is no member currently joined in vc with the bot,
    # the bot will auto leave.
    async def auto_leave(self, member, before, after):
        if member.guild.voice_client is not None and member.guild.me.voice is not None:
            if before.channel is not None and after.channel is None:
                if before.channel == member.guild.me.voice.channel:
                    if [m for m in member.guild.me.voice.channel.members if not m.bot] == [] and len(
                            [m for m in member.guild.me.voice.channel.members if not m.bot]) == 0:
                        await asyncio.sleep(15)
                        if [m for m in member.guild.me.voice.channel.members if not m.bot] == [] and len(
                                [m for m in member.guild.me.voice.channel.members if not m.bot]) == 0:
                            await member.guild.voice_client.disconnect()
                            await member.guild.voice_state.stop()
                            try:
                                member.voice_state.controller.stop()
                                await member.voice_state.controller.message.delete()
                            except:
                                pass
                            del self.voice_states[member.guild.id]

    @commands.command(help="See the actual song in playing", aliases=['np', 'nowplaying', 'current', 'playing'])
    @is_properly_connected()
    async def now(self, ctx: commands.Context):

        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{self.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))

        await ctx.send(embed=ctx.voice_state.current.create_embed())

    @commands.command(help="Save the current song playing in your dms.", aliases=['whatmusic'])
    @is_properly_connected()
    async def save(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        try:
            await ctx.author.send(content="The song that is being played.",
                                  embed=ctx.voice_state.current.create_embed())
        except disnake.Forbidden:
            return await ctx.send(
                embed=disnake.Embed(description=f"{self.bot.icons['redtick']} I am not able to dm you."))

    @commands.command(help='Pause the actual player')
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def pause(self, ctx):
        server = ctx.message.guild
        voice_channel = server.voice_client
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        voice_channel.pause()
        message = await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                     description=f"{self.bot.icons['greentick']} Alright "
                                                                 f"I paused the current playing music."))
        await message.add_reaction('⏯')

    @commands.command(help="Resume the paused player")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def resume(self, ctx):
        server = ctx.message.guild
        voice_channel = server.voice_client
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        voice_channel.resume()
        message = await ctx.send(embed=disnake.Embed(description=f"{self.bot.icons['info']} Resumed player."))
        await message.add_reaction('⏯')

    @commands.command(help="Stop the current player.")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def stop(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        em = disnake.Embed(title=f":zzz: Alright, I'll stop the current song.", color=disnake.Colour.random())
        em.set_footer(text=f"Stopped by {ctx.author.name}", icon_url=f"{ctx.author.avatar.url}")
        await ctx.send(embed=em)
        voice = disnake.utils.get(self.bot.voice_clients, guild=ctx.guild)
        voice.stop()

    @commands.command(name='loop', help="Loops the current playing song.")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def loop(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))

        if ctx.voice_state.loop is False:
            ctx.voice_state.loop = True
            message = await ctx.send(
                embed=disnake.Embed(description=f"{self.bot.icons['info']} Looped the current track."
                                    , color=disnake.Colour.random()))
            await message.add_reaction(f"{self.bot.icons['greentick']}")
            return
        if ctx.voice_state.loop is True:
            ctx.voice_state.loop = False
            message = await ctx.send(
                embed=disnake.Embed(description=f"{self.bot.icons['info']} Un-looped the current track."
                                    , color=disnake.Colour.random()))
            await message.add_reaction(f"{self.bot.icons['greentick']}")
            return

    @commands.command(help="Skip the current song")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def skip(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))

        voter = ctx.message.author
        if voter == ctx.voice_state.current.requester:
            await ctx.message.add_reaction('⏭')
            ctx.voice_state.skip()

        elif voter.id != ctx.voice_state.current.requester:
            if ctx.voice_state.current.requester not in ctx.author.voice.channel.members:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()

        elif voter.id not in ctx.voice_state.skip_votes:
            ctx.voice_state.skip_votes.add(voter.id)
            total_votes = len(ctx.voice_state.skip_votes)

            if total_votes >= 3:
                await ctx.message.add_reaction('⏭')
                ctx.voice_state.skip()
            else:
                await ctx.send(f'Skip vote added, currently at **{total_votes}/3**')

        else:
            await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                               description=f"{self.bot.icons['info']} You have already voted to skip "
                                                           f"this song."))

    @commands.command(help="Forcefully Skip the current song", aliases=['fs'])
    @invoker_or_admin()
    @is_properly_connected()
    @is_in_same_channel()
    async def fskip(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))
        ctx.voice_state.skip()
        await ctx.send(
            embed=disnake.Embed(description=f"{self.bot.icons['headphones']} You have forcefully skipped this song.",
                                color=disnake.Colour.random()))

    @commands.command(help="See the song queue", aliases=["q"])
    @is_properly_connected()
    async def queue(self, ctx: commands.Context, *, page: int = 1):

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                      description=f"{self.bot.icons['info']} The queue is empty."))

        items_per_page = 10
        pages = math.ceil(len(ctx.voice_state.songs) / items_per_page)

        start = (page - 1) * items_per_page
        end = start + items_per_page

        queue = ''
        embeds = []
        for i, song in enumerate(ctx.voice_state.songs[start:end], start=start):

            queue += f"`{i + 1}.` [**{song.source.title}**]({song.source.url})\n`{song.source.duration}`\n\n"
            embed = disnake.Embed(color=disnake.Colour.random(),
                                  description=f"**{len(ctx.voice_state.songs)} Tracks in Queue**").set_footer(
                text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url)

        embed.add_field(name="\u200b", value=f"{queue}", inline=False)
        embeds.append(embed)

        queue_menu = await self.paginate(Paginator(embeds, per_page=1))
        await queue_menu.start(ctx)

    @commands.command(name='shuffle', help="Shuffle the queue")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def shuffle(self, ctx: commands.Context):
        if not ctx.voice_state.is_playing:
            return await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} Not playing any "
                                                                  f"music right now... "
                                                      , colour=disnake.Colour.random()))

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                      description=f"{self.bot.icons['info']} Please add songs in "
                                                                  f"queue to shuffle"))

        ctx.voice_state.songs.shuffle()
        message = await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                     description=f"{self.bot.icons['greentick']} Songs Shuffled."))
        await message.add_reaction(f"{self.bot.icons['greentick']}")

    @commands.command(help="Remove a song from the queue")
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def remove(self, ctx: commands.Context, index: int):
        if len(ctx.voice_state.songs) == 0:
            return await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                      description=f"{self.bot.icons['info']} The queue is empty."))

        ctx.voice_state.songs.remove(index - 1)
        message = await ctx.send(embed=disnake.Embed(description=f"{self.bot.icons['info']} Removed song."))
        await message.add_reaction(f"{self.bot.icons['greentick']}")

    @commands.command(help="Clear the queue", aliases=["cq"])
    @is_properly_connected()
    @invoker_or_admin()
    @is_in_same_channel()
    async def clearqueue(self, ctx: commands.Context):

        if len(ctx.voice_state.songs) == 0:
            return await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                                      description=f"{self.bot.icons['info']} The queue is empty."))

        ctx.voice_state.songs.clear()
        message = await ctx.send(embed=disnake.Embed(description=f"{self.bot.icons['info']} Cleared the queue."))
        await message.add_reaction(f"{self.bot.icons['greentick']}")

    @commands.command(help="Play a song in a VC", aliases=['p'])
    async def play(self, ctx: commands.Context, *, search: str):

        if not ctx.voice_state.voice:
            await ctx.invoke(self.join)

        async with ctx.typing():
            try:
                source = await YoutubeSource.song_source(ctx, search, loop=self.bot.loop)

            except YoutubeSource as e:
                return await ctx.send(embed=disnake.Embed(
                    description=f"{self.bot.icons['redtick']} Error occurred while playing this track."))
            else:
                song = Song(source)

                await ctx.voice_state.songs.put(song)
                await ctx.send(f"{self.bot.icons['headphones']} Enqueued {str(source)}")

    @join.before_invoke
    @play.before_invoke
    async def proper_voice_state(self, ctx: commands.Context):
        """A check that checks if author has joined a voice channel before invoking join/play command."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise commands.CommandError(f"{self.bot.icons['redtick']} You are not connected to any voice channel.")

        if ctx.voice_client:
            if ctx.voice_client.channel != ctx.author.voice.channel:
                raise commands.CommandError(f"{self.bot.icons['info']} I have already joined voice channel.")


def setup(bot):
    bot.add_cog(Music(bot))
