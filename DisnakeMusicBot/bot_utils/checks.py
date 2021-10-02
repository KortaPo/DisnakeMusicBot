from __future__ import annotations
import disnake
from disnake.ext import commands


def is_properly_connected():  # A decorator that checks, if the bot and author has connected properly or not
    async def predicate(ctx: commands.Context):

        if ctx.author.voice.channel != ctx.guild.me.voice.channel:
            await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                               description=f"{ctx.bot.icons['redtick']} You are not "
                                                           f"aren't in my voice channel."))
            return False

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send(embed=disnake.Embed(color=disnake.Colour.random(),
                                               description=f"{ctx.bot.icons['redtick']} You are not "
                                                           f"connected to any voice channel."))
            return False

        return True

    return commands.check(predicate)


def invoker_or_admin():  # a decorator that checks the command Invoker is the same command Invoker who invoked the
    # commands previously.
    async def predicate(ctx: commands.Context):
        if ctx.author.guild_permissions.kick_members is True or ctx.voice_state.invoker == ctx.author:
            return True
        await ctx.send(embed=disnake.Embed(description=f"{ctx.bot.icons['redtick']} You do not have the "
                                                       "permission "
                                                       "to run this command... "
                                           , colour=disnake.Colour.random()))
        return False

    return commands.check(predicate)
