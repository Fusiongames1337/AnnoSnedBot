import argparse
import datetime
import gettext
import logging
import shlex
import re

import aiosqlite
import discord
from discord.ext import commands

async def hasOwner(ctx):
    return await ctx.bot.CommandChecks.hasOwner(ctx)
async def hasPriviliged(ctx):
    return await ctx.bot.CommandChecks.hasPriviliged(ctx)

class Moderation(commands.Cog):
    def __init__(self, bot):
        async def init_table():
            async with bot.pool.acquire() as con:
                await con.execute('''
                CREATE TABLE IF NOT EXISTS public.mod_config
                (
                    guild_id bigint,
                    mute_role_id bigint,
                    PRIMARY KEY (guild_id),
                    FOREIGN KEY (guild_id)
                        REFERENCES global_config (guild_id)
                        ON DELETE CASCADE
                )''')
        bot.loop.run_until_complete(init_table())

        self.bot = bot
        if self.bot.lang == "de":
            de = gettext.translation('moderation', localedir=self.bot.localePath, languages=['de'])
            de.install()
            self._ = de.gettext
        elif self.bot.lang == "en":
            self._ = gettext.gettext
        #Fallback to english
        else :
            logging.error("Invalid language, fallback to English.")
            self._ = gettext.gettext
        self.spam_cd_mapping = commands.CooldownMapping.from_cooldown(8, 8, commands.BucketType.member)
        self.invite_cd_mapping = commands.CooldownMapping.from_cooldown(2, 30, commands.BucketType.member)
        self.invite_mute_cd_mapping = commands.CooldownMapping.from_cooldown(1, 30, commands.BucketType.member)
    

    async def warn(self, ctx, member:discord.Member, moderator:discord.Member, reason:str=None):
        '''
        Warn a member, increasing their warning count and logging it.
        Requires userlog extension for full functionality.
        '''
        db_user = await self.bot.global_config.get_user(member.id, ctx.guild.id)
        warns = db_user.warns
        warns +=1
        new_user = self.bot.global_config.User(user_id = db_user.user_id, guild_id = db_user.guild_id, flags=db_user.flags, warns=warns, is_muted=db_user.is_muted, notes=db_user.notes)
        await self.bot.global_config.update_user(new_user) #Update warns for user by incrementing it
        if reason is None :
            embed=discord.Embed(title="⚠️" + self._("Warning issued"), description=self._("{offender} has been warned by {moderator}.").format(offender=member.mention, moderator=moderator.mention), color=self.bot.warnColor)
            warnembed=discord.Embed(title="⚠️ Warning issued.", description=f"{member.mention} has been warned by {moderator.mention}.\n**Warns:** {warns}\n\n[Jump!]({ctx.message.jump_url})", color=self.bot.warnColor)
        else :
            embed=discord.Embed(title="⚠️" + self._("Warning issued"), description=self._("{offender} has been warned by {moderator}.\n**Reason:** ```{reason}```").format(offender=member.mention, moderator=moderator.mention, reason=reason), color=self.bot.warnColor)
            warnembed=discord.Embed(title="⚠️ Warning issued.", description=f"{member.mention} has been warned by {moderator.mention}.\n**Warns:** {warns}\n**Reason:** ```{reason}```\n[Jump!]({ctx.message.jump_url})", color=self.bot.warnColor)
        try:
            await self.bot.get_cog("Logging").log_elevated(warnembed, ctx.guild.id)
            await ctx.send(embed=embed)
        except AttributeError:
            pass


    #Warn a user & print it to logs, needs logs to be set up
    @commands.group(name="warn", help="Warns a user. Subcommands allow you to clear warnings.", aliases=["bonk"], description="Warns the user and logs it.", usage="warn <user> [reason]", invoke_without_command=True, case_insensitive=True)
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def warn_cmd(self, ctx, offender:discord.Member, *, reason:str=None):
        '''
        Warn command. Person warning must be priviliged.
        '''
        await self.warn(ctx, member=offender, moderator=ctx.author, reason=reason)
    

    @warn_cmd.command(name="clear", help="Clears all warnings from the specified user.", aliases=["clr"])
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def warn_clr(self, ctx, offender:discord.Member, *, reason:str=None):
        '''
        Clears all stored warnings for a specified user.
        '''
        db_user = await self.bot.global_config.get_user(offender.id, ctx.guild.id)
        new_user = self.bot.global_config.User(user_id = db_user.user_id, guild_id = db_user.guild_id, flags=db_user.flags, warns=0, is_muted=db_user.is_muted, notes=db_user.notes)
        await self.bot.global_config.update_user(new_user) #Update warns for user by incrementing it
        if reason is None :
            embed=discord.Embed(title="✅ " + self._("Warnings cleared"), description=self._("{offender}'s warnings have been cleared.").format(offender=offender.mention), color=self.bot.embedGreen)
            warnembed=discord.Embed(title="⚠️ Warnings cleared.", description=f"{offender.mention}'s warnings have been cleared by {ctx.author.mention}.\n\n[Jump!]({ctx.message.jump_url})", color=self.bot.embedGreen)
        else :
            embed=discord.Embed(title="✅ " + self._("Warnings cleared"), description=self._("{offender}'s warnings have been cleared.\n**Reason:** ```{reason}```").format(offender=offender.mention, reason=reason), color=self.bot.embedGreen)
            warnembed=discord.Embed(title="⚠️ Warnings cleared.", description=f"{offender.mention}'s warnings have been cleared by {ctx.author.mention}.\n**Reason:** ```{reason}```\n[Jump!]({ctx.message.jump_url})", color=self.bot.embedGreen)
        try:
            await self.bot.get_cog("Logging").log_elevated(warnembed, ctx.guild.id)
            await ctx.send(embed=embed)
        except AttributeError:
            pass


    async def mute(self, ctx, member:discord.Member, moderator:discord.Member, duration:str=None, reason:str=None):
        '''
        Handles muting a user. If logging is set up, it will log it. Time is converted via the timers extension.
        If duration is provided, it is a tempmute, otherwise permanent. Updates database. Returns converted duration, if any.
        '''
        db_user = await self.bot.global_config.get_user(member.id, ctx.guild.id)
        if db_user.is_muted:
            raise ValueError('This member is already muted.')
        else:
            mute_role_id = 0
            async with self.bot.pool.acquire() as con:
                result = await con.fetch('''SELECT mute_role_id FROM mod_config WHERE guild_id = $1''', ctx.guild.id)
                if len(result) != 0 and result[0]:
                    mute_role_id = result[0].get('mute_role_id')
            mute_role = ctx.guild.get_role(mute_role_id)
            try:
                await member.add_roles(mute_role, reason=reason)
            except:
                raise
            else:
                new_user = self.bot.global_config.User(user_id = db_user.user_id, guild_id = db_user.guild_id, flags=db_user.flags, warns=db_user.warns, is_muted=True, notes=db_user.notes)
                await self.bot.global_config.update_user(new_user)
                dur = None
                if duration:
                    try:                   
                        dur = await self.bot.get_cog("Timers").converttime(duration)
                        await self.bot.get_cog("Timers").create_timer(expires=dur[0], event="tempmute", guild_id=ctx.guild.id, user_id=member.id, channel_id=ctx.channel.id)
                    except AttributeError:
                        raise ModuleNotFoundError('timers extension not found')
                try:
                    if not duration: duration = "Infinite"
                    else: duration = f"{dur[0]} (UTC)"
                    muteembed=discord.Embed(title="🔇 User muted", description=F"**User:** `{member} ({member.id})`\n**Moderator:** `{moderator} ({moderator.id})`\n**Until:** `{duration}`\n**Reason:** ```{reason}```", color=self.bot.errorColor)
                    await self.bot.get_cog("Logging").log_elevated(muteembed, ctx.guild.id)
                except:
                    pass
                if dur:
                    return dur[0] #Return it if needed to display
    

    async def unmute(self, ctx, member:discord.Member, moderator:discord.Member, reason:str=None):
        '''
        Handles unmuting a user, if logging is set up, it will log it. Updates database.
        '''
        db_user = await self.bot.global_config.get_user(member.id, ctx.guild.id)
        if not db_user.is_muted:
            raise ValueError('This member is not muted.')
        else:
            mute_role_id = 0
            async with self.bot.pool.acquire() as con:
                result = await con.fetch('''SELECT mute_role_id FROM mod_config WHERE guild_id = $1''', ctx.guild.id)
                if len(result) != 0 and result[0]:
                    mute_role_id = result[0].get('mute_role_id')
            mute_role = ctx.guild.get_role(mute_role_id)
            try:
                await member.remove_roles(mute_role)
            except:
                raise
            else:
                new_user = self.bot.global_config.User(user_id = db_user.user_id, guild_id = db_user.guild_id, flags=db_user.flags, warns=db_user.warns, is_muted=False, notes=db_user.notes)
                await self.bot.global_config.update_user(new_user)
                try:
                    muteembed=discord.Embed(title="🔉 User unmuted", description=F"**User:** `{member} ({member.id})`\n**Moderator:** `{moderator} ({moderator.id})`\n**Reason:** ```{reason}```", color=self.bot.embedGreen)
                    await self.bot.get_cog("Logging").log_elevated(muteembed, ctx.guild.id)
                except:
                    pass
                

    @commands.Cog.listener()
    async def on_member_join(self, member):
        '''
        If the user was muted previously, we apply
        the mute again.
        TL;DR: Mute-persistence
        '''
        db_user = await self.bot.global_config.get_user(member.id, member.guild.id)
        if db_user.is_muted == True:
            try:
                mute_role_id = 0
                async with self.bot.pool.acquire() as con:
                    result = await con.fetch('''SELECT mute_role_id FROM mod_config WHERE guild_id = $1''', member.guild.id)
                    if len(result) != 0 and result[0]:
                        mute_role_id = result[0].get('mute_role_id')
                mute_role = member.guild.get_role(mute_role_id)
                await member.add_roles(mute_role, reason="User was muted previously.")
            except AttributeError:
                return       


    @commands.command(name="mute", help="Mutes a user.", description="Mutes a user permanently (until unmuted). Logs the event if logging is set up.", usage="mute <user> [reason]")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def mute_cmd(self, ctx, offender:discord.Member, *, reason:str=None):
        '''
        Mutes a member, by assigning the Mute role defined in settings.
        Muter must be priviliged.
        '''
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot mute yourself"), description=self._("You cannot mute your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
        else:
            try:
                await self.mute(ctx, offender, moderator=ctx.author, reason=reason)
            except ValueError as error:
                if str(error) == 'This member is already muted.':
                    embed=discord.Embed(title="❌ " + self._("Already muted"), description=self._("{offender} is already muted.").format(offender=offender.mention), color=self.bot.errorColor)
                    await ctx.send(embed=embed)
            except (AttributeError, discord.Forbidden):
                embed=discord.Embed(title="❌ " + self._("Mute role error"), description=self._("Unable to mute user. Check if you have a mute role configured, and if the bot has permissions to add said role.").format(offender=offender.mention), color=self.bot.errorColor)
                await ctx.send(embed=embed)              
            else:
                if not reason: reason = "No reason specified"
                embed=discord.Embed(title="🔇 " + self._("User muted"), description=self._("**{offender}** has been muted.\n**Reason:** ```{reason}```").format(offender=offender.mention, reason=reason), color=self.bot.embedGreen)
                await ctx.send(embed=embed)


    @commands.command(name="unmute", help="Unmutes a user.", description="Unmutes a user. Logs the event if logging is set up.", usage="unmute <user> [reason]")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def unmute_cmd(self, ctx, offender:discord.Member, *, reason:str=None):
        try:
            await self.unmute(ctx, offender, moderator=ctx.author, reason=reason)
        except ValueError as error:
            if str(error) == 'This member is not muted.':
                embed=discord.Embed(title="❌ " + self._("Not muted"), description=self._("{offender} is not muted.").format(offender=offender.mention), color=self.bot.errorColor)
                await ctx.send(embed=embed)
        except (AttributeError, discord.Forbidden):
            embed=discord.Embed(title="❌ " + self._("Mute role error"), description=self._("Unable to unmute user. Check if you have a mute role configured, and if the bot has permissions to remove said role.").format(offender=offender.mention), color=self.bot.errorColor)
            await ctx.send(embed=embed)              
        else:
            if not reason: reason = "No reason specified"
            embed=discord.Embed(title="🔉 " + self._("User unmuted"), description=self._("**{offender}** has unbeen unmuted.\n**Reason:** ```{reason}```").format(offender=offender.mention, reason=reason), color=self.bot.embedGreen)
            await ctx.send(embed=embed)
    

    @commands.command(help="Temporarily mutes a user.", description="Mutes a user for a specified duration. Logs the event if logging is set up.\n\n**Time formatting:**\n`s` or `second(s)`\n`m` or `minute(s)`\n`h` or `hour(s)`\n`d` or `day(s)`\n`w` or `week(s)`\n`M` or `month(s)`\n`Y` or `year(s)`\n\n**Example:** `tempmute @User -d 5minutes -r 'Being naughty'` or `tempmute @User 5d`\n**Note:** If your arguments contain spaces, you must wrap them in quotation marks.", usage="tempmute <user> -d <duration> -r [reason] OR tempmute <user> <duration>")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def tempmute(self, ctx, offender:discord.Member, *, args):
        '''
        Temporarily mutes a memeber, assigning them a Muted role defined in the settings
        Uses userlog extension to log the event and timers to count the time & unmute on schedule.
        '''
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot mute yourself."), description=self._("You cannot mute your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--duration', '-d')
        parser.add_argument('--reason', '-r')
        try: 
            args = parser.parse_args(shlex.split(str(args)))
            dur = args.duration
            reason = args.reason
        except:
            dur = args
            reason = "No reason provided"

        try:
            muted_until = await self.mute(ctx, offender, moderator=ctx.author, duration=dur, reason=reason)
        except ValueError as error:
            if str(error) == 'This member is already muted.':
                embed=discord.Embed(title="❌ " + self._("Already muted"), description=self._("{offender} is already muted.").format(offender=offender.mention), color=self.bot.errorColor)
                await ctx.send(embed=embed)
            else:
                embed=discord.Embed(title="❌ " + self.bot.errorDataTitle, description=self._("Your entered timeformat is invalid. Type `{prefix}help tempmute` for more information.").format(prefix=ctx.prefix), color=self.bot.errorColor)
                await ctx.send(embed=embed)
        except (AttributeError, discord.Forbidden):
            embed=discord.Embed(title="❌ " + self._("Mute role error"), description=self._("Unable to mute user. Check if you have a mute role configured, and if the bot has permissions to add said role.").format(offender=offender.mention), color=self.bot.errorColor)
            await ctx.send(embed=embed)
        except ModuleNotFoundError:
            embed=discord.Embed(title="❌ " + self._("Muting failed"), description=self._("This function requires an extension that is not enabled.\n**Error:** ```{error}```").format(error=error), color=self.bot.errorColor)
            await ctx.send(embed=embed)    
        else:
            embed=discord.Embed(title="🔇 " + self._("User muted"), description=self._("**{offender}** has been muted until `{duration} (UTC)`.\n**Reason:** ```{reason}```").format(offender=offender.mention, duration=muted_until, reason=reason), color=self.bot.embedGreen)
            await ctx.send(embed=embed)
    

    @commands.Cog.listener()
    async def on_tempmute_timer_complete(self, timer):
        guild = self.bot.get_guild(timer.guild_id)
        db_user = await self.bot.global_config.get_user(timer.user_id, timer.guild_id)
        is_muted = db_user.is_muted
        if not is_muted:
            return
        new_user = self.bot.global_config.User(user_id = db_user.user_id, guild_id = db_user.guild_id, flags=db_user.flags, warns=db_user.warns, is_muted=False, notes=db_user.notes)
        await self.bot.global_config.update_user(new_user) #Update this here so if the user comes back, they are not perma-muted :pepeLaugh:
        if guild.get_member(timer.user_id) is not None: #Check if the user is still in the guild
            mute_role_id = 0
            async with self.bot.pool.acquire() as con:
                result = await con.fetch('SELECT mute_role_id FROM mod_config WHERE guild_id = $1', timer.guild_id)
                if len(result) != 0 and result[0]:
                    mute_role_id = result[0].get('mute_role_id')
            mute_role = guild.get_role(mute_role_id)
            try:
                offender = guild.get_member(timer.user_id)
                await offender.remove_roles(mute_role,  reason="Temporary mute expired.")
                embed=discord.Embed(title="🔉 User unmuted.", description=f"**{offender}** `({offender.id})` has been unmuted because their temporary mute expired.".format(offender=offender.mention), color=self.bot.embedGreen)
                await self.bot.get_cog("Logging").log_elevated(embed, timer.guild_id)
            except (AttributeError, discord.Forbidden):
                return
    

    @commands.command(help="Bans a user.", description="Bans a user with an optional reason. Deletes the last 7 days worth of messages from the user.", usage="ban <user> [reason]")
    @commands.check(hasPriviliged)
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx, offender:discord.Member, *, reason:str=None):
        '''
        Bans a member from the server.
        Banner must be priviliged and have ban_members perms.
        '''
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot ban yourself"), description=self._("You cannot ban your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        if reason:
            raw_reason = reason #Shown to the public
            reason = f"Reason: {reason}\n\nExecuted by {ctx.author} ({ctx.author.id})"
        else:
            raw_reason = reason
            reason = f"No reason provided - Executed by {ctx.author} ({ctx.author.id})"

        embed = discord.Embed(title="🔨 " + self._("You have been banned"), description=self._("You have been banned from **{guild}**.\n**Reason:** ```{raw_reason}```").format(guild=ctx.guild.name, raw_reason=raw_reason),color=self.bot.errorColor)
        await offender.send(embed=embed)

        try:
            await ctx.guild.ban(offender, reason=reason, delete_message_days=7)
            if raw_reason:
                embed = discord.Embed(title="🔨 " + self._("User banned"), description=self._("{offender} has been banned.\n**Reason:** ```{raw_reason}```").format(offender=offender, raw_reason=raw_reason),color=self.bot.errorColor)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title="🔨 " + self._("User banned"), description=self._("{offender} User has been banned.").format(offender=offender),color=self.bot.errorColor)
                await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform the ban, or this user cannot be banned."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.HTTPException:
            embed = discord.Embed(title="❌ " + self._("Ban failed"), description=self._("Ban failed, please try again later."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return


    @commands.command(help="Unbans a user.", description="Unbans a user with an optional reason. Deletes the last 7 days worth of messages from the user.", usage="unban <user> [reason]")
    @commands.check(hasPriviliged)
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx, offender:discord.User, *, reason:str=None):
        '''
        Unbans a member from the server.
        Unbanner must be priviliged and have ban_members perms.
        '''
        if reason:
            raw_reason = reason #Shown to the public
            reason = f"Reason: {reason}\n\nExecuted by {ctx.author} ({ctx.author.id})"
        else:
            raw_reason = reason
            reason = f"No reason provided - Executed by {ctx.author} ({ctx.author.id})"
        try:
            await ctx.guild.unban(offender, reason=reason)
            if raw_reason:
                embed = discord.Embed(title="✅ " + self._("User unbanned"), description=self._("{offender} has been unbanned.\n**Reason:** ```{raw_reason}```").format(offender=offender, raw_reason=raw_reason),color=self.bot.embedGreen)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title="✅ " + self._("User unbanned"), description=self._("{offender} has been unbanned.").format(offender=offender),color=self.bot.embedGreen)
                await ctx.send(embed=embed)
        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform the unban, or this user cannot be unbanned."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.HTTPException:
            embed = discord.Embed(title="❌ " + self._("Unban failed"), description=self._("Unban failed, please try again later."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
    

    @commands.command(help="Temporarily bans a user.", description="Temporarily bans a user for the duration specified. Deletes the last 7 days worth of messages from the user.\n\n**Time formatting:**\n`s` or `second(s)`\n`m` or `minute(s)`\n`h` or `hour(s)`\n`d` or `day(s)`\n`w` or `week(s)`\n`M` or `month(s)`\n`Y` or `year(s)`\n\n**Example:** `tempban @User -d 5minutes -r 'Being naughty'` or `tempban @User 5d`\n**Note:** If your arguments contain spaces, you must wrap them in quotation marks.", usage="tempban <user> -d <duration> -r [reason] OR tempban <user> <duration>")
    @commands.check(hasPriviliged)
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def tempban(self, ctx, offender:discord.Member, *, args):
        '''
        Temporarily bans a member from the server.
        Requires timers extension to work.
        Banner must be priviliged and have ban_members perms.
        '''
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot ban yourself."), description=self._("You cannot ban your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--duration', '-d')
        parser.add_argument('--reason', '-r')
        try: #If args are provided, we use those, otherwise whole arg is converted to time
            args = parser.parse_args(shlex.split(str(args)))
            dur = args.duration
            reason = args.reason
        except:
            dur = args
            reason = "No reason provided"
        try:
            dur = await self.bot.get_cog("Timers").converttime(dur)
            dur = dur[0]
            reason = f"[TEMPBAN] {reason}\nBanned until: {dur}"
        except ValueError:
            embed=discord.Embed(title="❌ " + self.bot.errorDataTitle, description=self._("Your entered timeformat is invalid. Type `{prefix}help tempban` for more information.").format(prefix=ctx.prefix), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            await ctx.message.delete()
        except AttributeError as error:
            embed=discord.Embed(title="❌ " + self._("Tempbanning failed."), description=self._("This function requires an extension that is not enabled.\n**Error:** ```{error}```").format(error=error), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        if reason:
            raw_reason = reason #Shown to the public
            reason = f"{reason}\n\nExecuted by {ctx.author} ({ctx.author.id})"
        else:
            raw_reason = reason
            reason = f"No reason provided - Executed by {ctx.author} ({ctx.author.id})"
        
        embed = discord.Embed(title="🔨 " + self._("You have been banned"), description=self._("You have been banned from **{guild}**.\n**Reason:** ```{raw_reason}```").format(guild=ctx.guild.name, raw_reason=raw_reason),color=self.bot.errorColor)
        await offender.send(embed=embed)

        try:
            await self.bot.get_cog("Timers").create_timer(expires=dur, event="tempban", guild_id=ctx.guild.id, user_id=offender.id, channel_id=ctx.channel.id)
            await ctx.guild.ban(offender, reason=reason, delete_message_days=7)
            if raw_reason:
                embed = discord.Embed(title="🔨 " + self._("User banned"), description=self._("{offender} has been banned.\n**Reason:** ```{raw_reason}```").format(offender=offender, raw_reason=raw_reason),color=self.bot.errorColor)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title="🔨 " + self._("User banned"), description=self._("{offender} has been banned.").format(offender=offender),color=self.bot.errorColor)
                await ctx.send(embed=embed)

        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform the ban, or this user cannot be banned."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.HTTPException:
            embed = discord.Embed(title="❌ " + self._("Tempban failed"), description=self._("Tempban failed, please try again later."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return

    @commands.Cog.listener()
    async def on_tempban_timer_complete(self, timer):
        guild = self.bot.get_guild(timer.guild_id)
        if guild is None:
            return
        try:
            offender = await self.bot.fetch_user(timer.user_id)
            await guild.unban(offender, reason="User unbanned: Tempban expired")
        except:
            return

    @commands.command(help="Softbans a user.", description="Bans a user then immediately unbans them, which means it will erase all messages from the user in the specified range.", usage="softban <user> [days-to-delete] [reason]")
    @commands.check(hasPriviliged)
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def softban(self, ctx, offender:discord.Member, deldays:int=1, *, reason:str=None):
        '''
        Soft-bans a user, by banning and un-banning them.
        Removes messages from the last x days.
        Banner must be priviliged and have kick_members permissions.
        Bot must have ban_members permissions.
        '''
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot soft-ban yourself."), description=self._("You cannot soft-ban your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        if reason:
            raw_reason = reason #Shown to the public
            reason = f"[SOFTBAN] {reason}\n\nExecuted by {ctx.author} ({ctx.author.id})"
        else:
            raw_reason = reason
            reason = f"[SOFTBAN] No reason provided - Executed by {ctx.author} ({ctx.author.id})"

            embed = discord.Embed(title="🔨 " + self._("You have been soft-banned"), description=self._("You have been soft-banned from **{guild}**. You may rejoin.\n**Reason:** ```{raw_reason}```").format(guild=ctx.guild.name, raw_reason=raw_reason),color=self.bot.errorColor)
            await offender.send(embed=embed)

        try:
            deldays = int(deldays)
            await ctx.guild.ban(offender, reason=reason, delete_message_days=7)
            await ctx.guild.unban(offender, reason="Automatic unban by softban command")
            if raw_reason:
                embed = discord.Embed(title="✅ " + self._("User soft-banned"), description=self._("{offender} has been soft-banned.\n**Reason:** {raw_reason}").format(offender=offender, raw_reason=raw_reason),color=self.bot.errorColor)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title="✅ " + self._("User soft-banned"), description=self._("{offender} has been soft-banned.").format(offender=offender),color=self.bot.errorColor)
                await ctx.send(embed=embed)
        except ValueError:
            embed = discord.Embed(title=self.bot.errorDataTitle, description=self._("Invalid format for argument `days-to-delete` See `{prefix}help softban` for command usage.").format(prefix=ctx.prefix),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform the ban, or this user cannot be banned."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.HTTPException:
            embed = discord.Embed(title="❌ " + self._("Ban failed"), description=self._("Ban failed, please try again later."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
    
    @commands.command(help="Kicks a user.", description="Kicks a user with an optional reason. Deletes the last 7 days worth of messages from the user.", usage="kick <user> [reason]")
    @commands.check(hasPriviliged)
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx, offender:discord.Member, *, reason:str=None):
        if offender.id == ctx.author.id:
            embed=discord.Embed(title="❌ " + self._("You cannot kick yourself."), description=self._("You cannot kick your own account."), color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        if reason != None:
            raw_reason = reason #Shown to the public
            reason = f"Reason: {reason}\n\nExecuted by {ctx.author} ({ctx.author.id})"
        else:
            raw_reason = reason
            reason = f"No reason provided - Executed by {ctx.author} ({ctx.author.id})"
        
        embed = discord.Embed(title="🚪👈 " + self._("You have been kicked"), description=self._("You have been kicked from **{guild}**.\n**Reason:** ```{raw_reason}```").format(guild=ctx.guild.name, raw_reason=raw_reason),color=self.bot.errorColor)
        await offender.send(embed=embed)

        try:
            await ctx.guild.kick(offender, reason=reason)
            if raw_reason:
                embed = discord.Embed(title="✅ " + self._("User kicked"), description=self._("{offender} has been kicked.\n**Reason:** ```{raw_reason}```").format(offender=offender, raw_reason=raw_reason),color=self.bot.embedGreen)
                await ctx.send(embed=embed)
            else:
                embed = discord.Embed(title="✅ " + self._("User kicked"), description=self._("{offender} has been kicked.").format(offender=offender),color=self.bot.embedGreen)
                await ctx.send(embed=embed)

        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform the kick, or this user cannot be kicked."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        except discord.HTTPException:
            embed = discord.Embed(title="❌ " + self._("Kick failed"), description=self._("Kick failed, please try again later."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
    
    @commands.command(aliases=["bulkdelete", "bulkdel"], help="Deletes multiple messages at once.", description="Deletes up to 100 messages at once. Defaults to 5 messages. You can optionally specify a user whose messages will be purged.", usage="purge [limit] [user]")
    @commands.check(hasPriviliged)
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def purge(self, ctx, limit=5, member:discord.Member=None):
        if limit > 100:
            embed = discord.Embed(title="❌ " + self._("Limit too high"), description=self._("You cannot remove more than **100** messages."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
        try:
            if member:
                def check(message):
                    return message.author.id == member.id
                
                purged = await ctx.channel.purge(limit=limit, check=check)
            else:
                purged = await ctx.channel.purge(limit=limit)
            
            embed = discord.Embed(title="🗑️ " + self._("Messages purged"), description=self._("**{count}** messages have been deleted.").format(count=len(purged)), color=self.bot.errorColor)
            await ctx.send(embed=embed, delete_after=60.0)
        except discord.Forbidden:
            embed = discord.Embed(title="❌ " + self._("Bot has insufficient permissions"), description=self._("The bot has insufficient permissions to perform message deletion, or this user cannot have his messages removed."),color=self.bot.errorColor)
            await ctx.send(embed=embed)
            return
    
    @commands.Cog.listener()
    async def on_message(self, message):
        '''
        Auto-Moderation
        '''
        if message.guild is None:
            return
        bucket = self.spam_cd_mapping.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after: #If user exceeded spam limits
            db_user = await self.bot.global_config.get_user(message.author.id, message.guild.id)
            ctx = await self.bot.get_context(message)
            if not db_user.is_muted and not await hasPriviliged(ctx) and not message.author.bot:
                try:
                    await self.mute(ctx, message.author, moderator=ctx.guild.me, duration="15min", reason="Automatic mute for spam")
                except:
                    pass
                else:
                    embed=discord.Embed(title="🔇 " + self._("User muted"), description=self._("**{offender}** has been auto-muted for **15** minutes due to spamming.").format(offender=message.author.mention), color=self.bot.errorColor)
                    embed.set_footer(text=self._("If you believe this was a mistake, contact a moderator."))
                    await message.channel.send(embed=embed)
        else:
            invite_regex = re.compile(r"(?:https?://)?discord(?:app)?\.(?:com/invite|gg)/[a-zA-Z0-9]+/?")
            matches = invite_regex.findall(message.content)
            ctx = await self.bot.get_context(message)
            if matches and not await hasPriviliged(ctx):
                bucket = self.invite_cd_mapping.get_bucket(message)
                invite_rt = bucket.update_rate_limit()
                try:
                    await message.delete() #If we cannot delete the message, we will just ignore any further automod actions
                except:
                    pass
                else:
                    if invite_rt: #If invite ratelimited
                        mute_bucket = self.invite_mute_cd_mapping.get_bucket(message)
                        invite_mute_rt = mute_bucket.update_rate_limit()
                        if invite_mute_rt: #If user has been warned previously
                            try:
                                await self.mute(ctx, message.author, moderator=ctx.guild.me, duration="15min", reason="Automatic mute for sending discord invite links")
                            except:
                                pass
                            else:
                                embed=discord.Embed(title="🔇 " + self._("User muted"), description=self._("**{offender}** has been auto-muted for **15** minutes due to sending invite links.").format(offender=message.author.mention), color=self.bot.errorColor)
                                embed.set_footer(text=self._("If you believe this was a mistake, contact a moderator."))
                                await message.channel.send(embed=embed)
                        else: #Warn user for repeat offenses
                            await self.warn(ctx, message.author, ctx.guild.me, reason="Trying to send Discord invite links")

    

def setup(bot):
    logging.info("Adding cog: Moderation...")
    bot.add_cog(Moderation(bot))
