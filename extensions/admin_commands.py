import discord
from discord.ext import commands
import asyncio


async def hasOwner(ctx):
    return ctx.author.id == ctx.bot.owner_id or ctx.author.id == ctx.guild.owner_id

#Check performed to see if the user has priviliged access.
async def hasPriviliged(ctx):
    #Gets a list of all the roles the user has, then gets the ID from that.
    userRoles = [x.id for x in ctx.author.roles]
    #Also get privliged roles, then compare
    privroles = [role[0] for role in await ctx.bot.DBHandler.checkprivs(ctx.guild.id)]
    #Check if any of the roles in user's roles are contained in the priviliged roles.
    return any(role in userRoles for role in privroles) or (ctx.author.id == ctx.bot.owner_id or ctx.author.id == ctx.guild.owner_id)

class AdminCommands(commands.Cog, name="Admin Commands"):
    def __init__(self, bot):
        self.bot = bot

    #Returns basically all information we know about a given member of this guild.
    @commands.command(hidden=True, brief="Get information about a user.", description="Provides information about a specified user in the guild.", usage=f"whois <userID|userMention|userName>")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def whois(self, ctx, member : discord.Member) :
        rolelist = [role.name for role in member.roles]
        roleformatted = ", ".join(rolelist)
        embed=discord.Embed(title=f"User information: {member.name}", description=f"Username: `{member.name}` \nNickname: `{member.display_name}` \nUser ID: `{member.id}` \nStatus: `{member.raw_status}` \nBot: `{member.bot}` \nAccount creation date: `{member.created_at}` \nJoin date: `{member.joined_at}` \nRoles: `{roleformatted}`", color=member.colour)
        embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
        embed.set_thumbnail(url=member.avatar_url)
        await ctx.channel.send(embed=embed)
    @whois.error
    async def whois_error(self, ctx, error):
        if isinstance(error, discord.ext.commands.errors.MemberNotFound) :
            embed=discord.Embed(title="❌ Unable to find user.", description="Please check if you typed everything correctly, then try again.", color=self.bot.errorColor)
            await ctx.send(embed=embed)

    #Command used for deleting a guild settings file
    @commands.command(hidden=True, brief="Resets all settings for this guild.", description = "Resets all settings for this guild. Will also erase all tags. Irreversible.", usage="resetsettings")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def resetsettings(self, ctx):
        embed = discord.Embed(title="Are you sure you want to reset all settings?", description="This will also erase any created tags.\n**This action is __irreversible__ and may break things!**", color=self.bot.errorColor)
        msg = await ctx.channel.send(embed=embed)
        await msg.add_reaction("✅")
        await msg.add_reaction("❌")
        def check(payload):
            return payload.message_id == msg.id and payload.user_id == ctx.author.id
        try:
            payload = await self.bot.wait_for('raw_reaction_add', timeout=10.0,check=check)
            if str(payload.emoji) == "✅":
                def check2(payload):
                    return payload.channel.id == msg.channel.id and payload.author == ctx.author
                embed=discord.Embed(title="Confirmation", description="Please type in the name of the server to confirm deletion.", color=self.bot.errorColor)
                await ctx.channel.send(embed=embed)
                payload = await self.bot.wait_for('message', timeout=20.0, check=check2)
                if payload.content == ctx.guild.name :
                    await self.bot.DBHandler.deletesettings(ctx.guild.id)
                    embed=discord.Embed(title="✅ Settings reset.", description="Goodbye cruel world! 😢", color=self.bot.errorColor)
                    await ctx.channel.send(embed=embed)
                else :
                    embed=discord.Embed(title="❌ Error: Invalid name.", description="Settings deletion cancelled.", color=self.bot.errorColor)
                    await ctx.channel.send(embed=embed)
            elif str(payload.emoji) == "❌" :
                embed=discord.Embed(title="❌ Cancelled.", description="Settings reset cancelled by user.", color=self.bot.errorColor)
                await ctx.channel.send(embed=embed)
            else :
                embed=discord.Embed(title=self.bot.errorEmojiTitle, description="Settings deletion cancelled.", color=self.bot.errorColor)
                await ctx.channel.send(embed=embed)
        except asyncio.TimeoutError:
            embed=discord.Embed(title=self.bot.errorTimeoutTitle, description="Settings deletion cancelled.")
            await ctx.channel.send(embed=embed)


    #Display the current settings for this guild.
    @commands.command(hidden=True, brief="Displays settings.", description="Displays the settings for the current guild.", usage="settings")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def settings(self, ctx):
        settingsdata = await self.bot.DBHandler.displaysettings(ctx.guild.id)
        if settingsdata == -1 :
            await ctx.channel.send("**Error:** No settings for this guild.")
        else :
            formatteddata = "".join(settingsdata)
            embed=discord.Embed(title=f"⚙️ Settings for this guild:    ({ctx.guild.id})", description=f"```{formatteddata}```", color=self.bot.embedBlue)
            await ctx.channel.send(embed=embed)


    #Modify a value in the settings, use with care or it will break things
    @commands.command(hidden=True, brief=f"Modifies a setting value. Recommended to use setup instead.", description=f"Modifies a single value in the settings, improper use can and will break things! Use setup instead.", usage="modify <datatype> <value>")
    @commands.check(hasPriviliged)
    @commands.guild_only()
    async def modify(self, ctx, datatype, value) :
        if datatype not in self.bot.datatypes :
            embed=discord.Embed(title="❌ Error: Invalid datatype.", description="Please enter a valid datatype.", color=self.bot.errorColor)
            await ctx.channel.send(embed=embed)
            return
        try:
            int(value)
            await self.bot.DBHandler.modifysettings(datatype, int(value), ctx.guild.id)
            embed=discord.Embed(title="Data modified.", description=f"**{datatype}** is now set to **{value}** for guild **{ctx.guild.id}**.", color=self.bot.embedBlue)
            await ctx.channel.send(embed=embed)
        except ValueError:
            embed=discord.Embed(title="❌ Error: Invalid value.", description="Please enter a valid value.", color=self.bot.errorColor)
            await ctx.channel.send(embed=embed)
            return
        except:
            embed=discord.Embed(title="❌ Error: Unknown error encountered.", description="Please check database settings.", color=self.bot.errorColor)
            await ctx.channel.send(embed=embed)
            return

def setup(bot):
    print("[INFO] Adding cog: AdminCommands...")
    bot.add_cog(AdminCommands(bot))