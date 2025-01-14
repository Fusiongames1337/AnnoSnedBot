import argparse
import asyncio
import gettext
import logging
import os
import random
import shlex
from pathlib import Path

import aiohttp
import discord
import psutil
from discord.ext import commands


async def hasOwner(ctx):
    return await ctx.bot.CommandChecks.hasOwner(ctx)
async def hasPriviliged(ctx):
    return await ctx.bot.CommandChecks.hasPriviliged(ctx)


class MiscCommands(commands.Cog, name="Miscellaneous Commands"):
    def __init__(self, bot):
        self.bot = bot
        if self.bot.lang == "de":
            de = gettext.translation('misc_commands', localedir=self.bot.localePath, languages=['de'])
            de.install()
            self._ = de.gettext
        elif self.bot.lang == "en":
            self._ = gettext.gettext
        #Fallback to english
        else :
            logging.error("Invalid language, fallback to English.")
            self._ = gettext.gettext
        psutil.cpu_percent(interval=1) #We need to do this here so that subsequent CPU % calls will be non-blocking

    @commands.command(help="Displays a user's avatar.", description="Displays a user's avatar for your viewing (or stealing) pleasure.", usage=f"avatar <userID|userMention|userName>")
    @commands.cooldown(1, 30, type=commands.BucketType.member)
    @commands.guild_only()
    async def avatar(self, ctx, member : discord.Member) :
        embed=discord.Embed(title=self._("{member_name}'s avatar:").format(member_name=member.name), color=member.colour)
        embed.set_image(url=member.avatar_url)
        embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
        await ctx.channel.send(embed=embed)

        #Gets the ping of the bot.
    @commands.command(help="Displays bot ping.", description="Displays the current ping of the bot in miliseconds. Takes no arguments.", usage="ping")
    @commands.guild_only()
    async def ping(self, ctx):
        embed=discord.Embed(title="🏓 Pong!", description=self._("Latency: `{latency}ms`").format(latency=round(self.bot.latency * 1000)), color=self.bot.miscColor)
        embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
        await ctx.channel.send(embed=embed)

    #A more fun way to get the ping.
    @commands.command(hidden = True, help="A better way to get the ping.", description="Why? because yes. Displays the current ping of the bot in miliseconds. Takes no arguments.", usage=f"LEROY")
    @commands.guild_only()
    async def leroy(self, ctx):
        embed=discord.Embed(title="JEEEEENKINS!", description=f"... Oh my god he just ran in. 👀 `{round(self.bot.latency * 1000)}ms`", color =self.bot.miscColor)
        embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
        await ctx.channel.send(embed=embed)
    
    @commands.command(help="Generates an embed with the given parameters.", description="Generates an embed, and displays it according to the parameters specified. Uses shell-like arguments. Valid parameters:\n\n`--title` or `-t` (Required) Sets embed title\n`--desc` or `-d` (Required) Sets embed description\n`--color` or `-c` Sets embed color (line on the left side)\n`--thumbnail_url` or `-tu` Sets thumbnail to the specified image URL\n`--image_url` or `-iu` Sets the image field to the specified image URL\n`--footer` or `-f` Sets the footer text", usage="embed <args>")
    @commands.cooldown(1, 60, type=commands.BucketType.member)
    @commands.guild_only()
    async def embed(self, ctx, *, args):
        
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--title', '-t')
        parser.add_argument('--desc', '-d')
        parser.add_argument('--footer', '-f')
        parser.add_argument('--thumbnail_url', '-tu')
        parser.add_argument('--image_url', '-iu')
        parser.add_argument('--color', '-c')
        try: 
            args = parser.parse_args(shlex.split(str(args)))
        except Exception as e:
            embed = discord.Embed(title="❌ " + self._("Failed parsing arguments"), description=self._("**Exception:** ```{exception}```").format(exception=str(e)), color=self.bot.errorColor)
            embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return
        except SystemExit as s:
            embed = discord.Embed(title="❌ " + self._("Failed parsing arguments"), description=self._("**Exception:** ```SystemExit: {exception}```\n**Note:** If you are trying to pass multiple words as an argument, wrap them in quotation marks.").format(exception=str(s)), color=self.bot.errorColor)
            embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return
        if args.title == None or args.desc == None:
            embed = discord.Embed(title="❌ " + self._("Missing required argument"), description=self._("You are missing a required argument. Please check `{prefix}help embed` for command usage.").format(prefix=ctx.prefix), color=self.bot.errorColor)
            embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return
        if args.color:
            try:
                color = await commands.ColorConverter().convert(ctx, args.color)
                genEmbed = discord.Embed(title=f"{args.title}", description=f"{args.desc}", color=color)
            except commands.BadArgument:
                embed = discord.Embed(title="❌ " + self._("Invalid color"), description=self._("For valid colors, see the [discord.py API reference](https://discordpy.readthedocs.io/en/latest/api.html#discord.Colour)"), color=self.bot.errorColor)
                embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
                await ctx.send(embed=embed)
                return
        else:
            genEmbed = discord.Embed(title=f"{args.title}", description=f"{args.desc}")
        if args.footer:
            genEmbed.set_footer(text=f"{args.footer}")
        if args.thumbnail_url:
            genEmbed.set_thumbnail(url=f"{args.thumbnail_url}")
        if args.image_url:
            genEmbed.set_image(url=f"{args.image_url}")
        try:
            await ctx.send(embed=genEmbed)
        except discord.HTTPException as e:
            embed = discord.Embed(title="❌ " + self._("Failed parsing arguments."), description=self._("**Exception:** ```{exception}```").format(exception=str(e)), color=self.bot.errorColor)
            embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return

    #Shows bot version, creator, etc..
    @commands.command(help="Displays information about the bot.", description="Displays information about the bot. Takes no arguments.", usage="about", aliases=["info"])
    @commands.guild_only()
    async def about(self, ctx):
        embed=discord.Embed(title=f"ℹ️ About {self.bot.user.name}", description=f"**Version:** {self.bot.current_version} \n**Language:** {self.bot.lang} \n**Made by:** Hyper#0001 \n**GitHub:** https://github.com/HyperGH/AnnoSnedBot", color=self.bot.embedBlue)
        embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
        embed.set_thumbnail(url=self.bot.user.avatar_url)
        embed.add_field(name="CPU utilization", value=f"`{round(psutil.cpu_percent(interval=None))}%`")
        embed.add_field(name="Memory utilization", value=f"`{round(psutil.virtual_memory().used / 1048576)}MB`")
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 1000)}ms`")
        await ctx.channel.send(embed=embed)

    #Retrieves info about the current guild for the end-user
    @commands.command(help="Get information about the server.", description="Provides detailed information about this server.", usage="serverinfo")
    @commands.guild_only()
    @commands.cooldown(1, 60, type=commands.BucketType.member)
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed=discord.Embed(title="ℹ️ " + self._("Server information"), description=self._("**Name:** `{guild_name}`\n**ID:** `{guild_id}`\n**Owner:** `{owner}`\n**Created at:** `{creation_date}`\n**Member count:** `{member_count}`\n**Region:** `{region}`\n**Filesize limit:** `{filecap}`\n**Nitro Boost count:** `{premium_sub_count}`\n**Nitro Boost level:** `{premium_tier}`").format(guild_name=guild.name, guild_id=guild.id, owner=guild.owner, creation_date=guild.created_at, member_count=guild.member_count, region=guild.region, filecap=f"{guild.filesize_limit/1048576}MB", premium_sub_count=guild.premium_subscription_count, premium_tier=guild.premium_tier), color=self.bot.embedBlue)
        embed.set_footer(text=self.bot.requestFooter.format(user_name=ctx.author.name, discrim=ctx.author.discriminator), icon_url=ctx.author.avatar_url)
        embed.set_thumbnail(url=guild.icon_url)
        if guild.discovery_splash_url: #If the server has a discovery splash/invite background, we put it as an embed image for extra fancyTM
            embed.set_image(url=guild.discovery_splash_url)
        await ctx.send(embed=embed)
    
    @commands.command(help = "Displays the amount of warnings for a user.", description="Displays the amount of warnings issued to a user. If user is not specified, it will default to self.", usage="warns [user]")
    @commands.guild_only()
    async def warns(self, ctx, user:discord.Member=None):
        if user is None:
            user = ctx.author
        extensions = self.bot.checkExtensions
        if "Moderation" not in extensions :
            embed=discord.Embed(title=self.bot.errorMissingModuleTitle, description="This command requires the extension `moderation` to be active.", color=self.bot.errorColor)
            await ctx.channel.send(embed=embed)
            return
        db_user = await self.bot.global_config.get_user(user.id, ctx.guild.id)
        warns = db_user.warns
        embed = discord.Embed(title=self._("{user}'s warnings").format(user=user), description=self._("**Warnings:** `{warns}`").format(warns=warns), color=self.bot.warnColor)
        embed.set_thumbnail(url=user.avatar_url)
        await ctx.send(embed=embed)

def setup(bot):
    logging.info("Adding cog: MiscCommands...")
    bot.add_cog(MiscCommands(bot))
