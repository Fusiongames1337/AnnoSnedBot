import discord
import time
import threading
from discord.ext import commands
import logging
import asyncio
import os
import shutil
from dotenv import load_dotenv
import aiosqlite
from difflib import get_close_matches
import sys
import traceback
from itertools import chain
import datetime


#Is this build experimental?
experimentalBuild = False
#Version of the bot
currentVersion = "3.0.0"
#Loading token from .env file. If this file does not exist, nothing will work.
load_dotenv()
#Get token from .env
TOKEN = os.getenv("TOKEN")
#Activity
activity = discord.Activity(name='you', type=discord.ActivityType.watching)
#Determines bot prefix & logging based on build state.
prefix = '!'
if experimentalBuild == True : 
    prefix = '?'
    logging.basicConfig(level=logging.INFO)
else :
    prefix = '!'
    logging.basicConfig(level=logging.INFO)

#This is just my user ID, used for setting up who can & cant use priviliged commands along with a server owner.
creatorID = 163979124820541440
#Can modify command prefix & intents here (and probably a lot of other cool stuff I am not aware of)
bot = commands.Bot(command_prefix=prefix, intents= discord.Intents.all(), owner_id=creatorID, case_insensitive=True, help_command=None, activity=activity)

#General global bot settings

#Database filename
dbName = "database.db"
#Database filepath
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
bot.dbPath = os.path.join(BASE_DIR, dbName)
#No touch
bot.currentVersion = currentVersion
bot.prefix = prefix
bot.experimentalBuild = experimentalBuild

#All extensions that are loaded on boot-up, change these to alter what modules you want (Note: These refer to filenames NOT cognames)
#Note: Without the extension admin_commands, most things will break, so I consider this a must-have. Remove at your own peril.
#Jishaku is a bot-owner only debug cog, requires 'pip install jishaku'.
initial_extensions = ['extensions.admin_commands', 'extensions.misc_commands', 'extensions.matchmaking', 'extensions.tags', 'extensions.setup', 'jishaku']
#Contains all the valid datatypes in settings. If you add a new one here, it will be automatically generated
#upon a new request to retrieve/modify that datatype.
bot.datatypes = ["COMMANDSCHANNEL", "ANNOUNCECHANNEL", "ROLEREACTMSG", "LFGROLE", "LFGREACTIONEMOJI", "KEEP_ON_TOP_CHANNEL", "KEEP_ON_TOP_MSG"]
#These text names are reserved and used for internal internal functions, other ones may get created by users for tags.
bot.reservedTextNames = ["KEEP_ON_TOP_CONTENT"]
#
#Error/warn messages
#
#Note: This contains strings for common error/warn msgs.

#Errors:
bot.errorColor = 0xff0000
bot.errorTimeoutTitle = "🕘 Error: Timed out."
bot.errorTimeoutDesc = "Your request has expired. Execute the command again!"
bot.errorDataTitle = "❌ Error: Invalid data entered."
bot.errorDataDesc = "Operation cancelled."
bot.errorEmojiTitle = "❌ Error: Invalid reaction entered."
bot.errorEmojiDesc = "Operation cancelled."
bot.errorFormatTitle = "❌ Error: Invalid format entered."
bot.errorFormatDesc = "Operation cancelled."
bot.errorCheckFailTitle = "❌ Error: Insufficient permissions."
bot.errorCheckFailDesc = f"Type `{bot.prefix}help` for a list of available commands."
bot.errorCooldownTitle = "🕘 Error: This command is on cooldown."
bot.errorMissingModuleTitle = "❌ Error: Missing module."
bot.errorMissingModuleDesc = "This operation is missing a module."
#Warns:
bot.warnColor = 0xffcc4d
bot.warnDataTitle = "⚠️ Warning: Invalid data entered."
bot.warnDataDesc = "Please check command usage."
bot.warnEmojiTitle = "⚠️ Warning: Invalid reaction entered."
bot.warnEmojiDesc = "Please enter a valid reaction."
bot.warnFormatTitle = "⚠️ Warning: Invalid format entered."
bot.warnFormatDesc = "Please try entering valid data."
#Misc:
bot.embedBlue = 0x009dff
bot.embedGreen = 0x00ff2a
bot.unknownColor = 0xbe1931
bot.miscColor = 0xc2c2c2

print("[INFO]: New Session Started.")


#Loading extensions from the list of extensions defined above
if __name__ == '__main__':
    for extension in initial_extensions:
        try:
            bot.load_extension(extension)
        except Exception as e:
            print(f'[ERROR] Failed to load extension {extension}.', file=sys.stderr)
            traceback.print_exc()

#Simple function that just gets all currently loaded cog/extension names
def checkExtensions():
    extensions = []
    for cogName,cogClass in bot.cogs.items():
        extensions.append(cogName)
    return extensions
        
bot.checkExtensions = checkExtensions()

#Executes when the bot starts & is ready.
@bot.event
async def on_ready():
    print("[INFO]: Initialized as {0.user}".format(bot))
    if bot.experimentalBuild == True :
        print("[WARN]: Experimental mode is enabled.")
        print(f"Extensions loaded: {bot.checkExtensions}")




#
#DBHandler
#
#All functions relating to adding, updating, inserting, or removing from any table in the database
class DBhandler():
    #Deletes a guild specific settings file.
    async def deletesettings(self, guildID):
        #Delete all data relating to this guild.
        async with aiosqlite.connect(bot.dbPath) as db:
            await db.execute("DELETE FROM settings WHERE guild_id = ?", [guildID])
            await db.execute("DELETE FROM priviliged WHERE guild_id = ?", [guildID])
            await db.execute("DELETE FROM stored_text WHERE guild_id = ?", [guildID])
            await db.commit()
            #os.remove(f"{guildID}_settings.cfg")
            print(f"[WARN]: Settings have been reset and tags erased for guild {guildID}.")

    #Returns the priviliged roles for a specific guild as a list.
    async def checkprivs(self, guildID):
        async with aiosqlite.connect(bot.dbPath) as db:
            cursor = await db.execute("SELECT priviliged_role_id FROM priviliged WHERE guild_id = ?", [guildID])
            roleIDs = await cursor.fetchall()
            #Abstracting away the conversion from tuples
            roleIDs = [role[0] for role in roleIDs]
            return roleIDs
    #Inserts a priviliged role
    async def setpriv(self, roleID, guildID):
        async with aiosqlite.connect(bot.dbPath) as db:
            await db.execute("INSERT INTO priviliged (guild_id, priviliged_role_id) VALUES (?, ?)", [guildID, roleID])
            await db.commit()
    #Deletes a priviliged role
    async def delpriv(self, roleID, guildID):
        async with aiosqlite.connect(bot.dbPath) as db:
            await db.execute("DELETE FROM priviliged WHERE guild_id = ? AND priviliged_role_id = ? ", [guildID, roleID])
            await db.commit()
    #Modifies a value in settings relating to a guild
    async def modifysettings(self, datatype, value, guildID):
        if datatype in bot.datatypes :
            #Check if we have values for this guild
            async with aiosqlite.connect(bot.dbPath) as db:
                cursor = await db.execute("SELECT guild_id FROM settings WHERE guild_id = ?", [guildID])
                result = await cursor.fetchone()
                if result != None :
                    #Looking for the datatype
                    cursor = await db.execute("SELECT datatype FROM settings WHERE guild_id = ? AND datatype = ?", [guildID, datatype])
                    result = await cursor.fetchone()
                    #If the datatype does exist, we return the value
                    if result != None :
                        #We update the matching record with our new value
                        await db.execute("UPDATE settings SET guild_id = ?, datatype = ?, value = ? WHERE guild_id = ? AND datatype = ?", [guildID, datatype, value, guildID, datatype])
                        await db.commit()
                        return
                    #If it does not, for example if a new valid datatype is added to the code, we will create it, and assign it the value.
                    else :
                        await db.execute("INSERT INTO settings (guild_id, datatype, value) VALUES (?, ?, ?)", [guildID, datatype, value])
                        await db.commit()
                        return
                #If no data relating to the guild can be found, we will create every datatype for the guild
                #Theoretically not necessary, but it outputs better into displaysettings()
                else :
                    for item in bot.datatypes :
                        #We insert every datatype into the table for this guild.
                        await db.execute("INSERT INTO settings (guild_id, datatype, value) VALUES (?, ?, 0)", [guildID, item])
                    await db.commit()
                    #And then we update the value we wanted to change in the first place.
                    await db.execute("UPDATE settings SET guild_id = ?, datatype = ?, value = ? WHERE guild_id = ? AND datatype = ?", [guildID, datatype, value, guildID, datatype])
                    await db.commit()
                    return

    #Retrieves a setting for a specified guild.
    async def retrievesetting(self, datatype, guildID) :
        if datatype in bot.datatypes :
            #Check if we have values for this guild
            async with aiosqlite.connect(bot.dbPath) as db:
                cursor = await db.execute("SELECT guild_id FROM settings WHERE guild_id = ?", [guildID])
                result = await cursor.fetchone()
                #If we do, we check if the datatype exists
                if result != None :
                    #Looking for the datatype
                    cursor = await db.execute("SELECT datatype FROM settings WHERE guild_id = ? AND datatype = ?", [guildID, datatype])
                    result = await cursor.fetchone()
                    #If the datatype does exist, we return the value
                    if result != None :
                        cursor = await db.execute("SELECT value FROM settings WHERE guild_id = ? AND datatype = ?", [guildID, datatype])
                        #This is necessary as fetchone() returns it as a tuple of one element.
                        value = await cursor.fetchone()
                        return value[0]
                    #If it does not, for example if a new valid datatype is added to the code, we will create it, then return it's value.
                    else :
                        await db.execute("INSERT INTO settings (guild_id, datatype, value) VALUES ?, ?, 0", [guildID, datatype])
                        cursor = await db.execute("SELECT value FROM settings WHERE guild_id = ? AND datatype = ?", [guildID, datatype])
                        value = await cursor.fetchone()
                        return value[0]
                #If no data relating to the guild can be found, we will create every datatype for the guild, and return their value.
                #Theoretically not necessary, but it outputs better into displaysettings()
                else :
                    for item in bot.datatypes :
                        #We insert every datatype into the table for this guild.
                        await db.execute("INSERT INTO settings (guild_id, datatype, value) VALUES (?, ?, 0)", [guildID, item])
                    await db.commit()
                    #And then we return error -1 to signal that there are no settings
                    return -1
        else :
            print(f"[INTERNAL ERROR]: Invalid datatype called in retrievesetting() (Called datatype: {datatype})")

    #Should really be retrieveallsettings() but it is only used in !settings to display them to the users
    async def displaysettings(self, guildID) :
        #Check if there are any values stored related to the guild.
        #If this is true, guild settings exist.
        async with aiosqlite.connect(bot.dbPath) as db:
            result = None
            cursor = await db.execute("SELECT guild_id FROM settings WHERE guild_id = ?", [guildID])
            result = await cursor.fetchone()
            #If we find something, we gather it, return it.
            if result != None :
                #This gets datapairs in a tuple, print it below if you want to see how it looks
                cursor = await db.execute("SELECT datatype, value FROM settings WHERE guild_id = ?", [guildID])
                dbSettings = await cursor.fetchall()
                #print(dbSettings)
                #The array we will return to send in the message
                settings = []
                #Now we just combine them.
                i = 0
                for i in range(len(dbSettings)) :
                    settings.append(f"{dbSettings[i][0]} = {dbSettings[i][1]} \n")
                    i += 1
                return settings
            #If not, we return error code -1, corresponding to no settings.
            else:
                return -1
    #Retrieves a piece of stored text inside table stored_text (Mostly used for tags)
    async def retrievetext(self, textname, guildID) :
        
        #Check if we have values for this guild
        async with aiosqlite.connect(bot.dbPath) as db:
            #Check for the desired text
            cursor = await db.execute("SELECT text_name FROM stored_text WHERE guild_id = ? AND text_name = ?", [guildID, textname])
            result = await cursor.fetchone()
            #If the datatype does exist, we return the value
            if result != None :
                cursor = await db.execute("SELECT text_content FROM stored_text WHERE guild_id = ? AND text_name = ?", [guildID, textname])
                result = await cursor.fetchone()
                #This is necessary as fetchone() returns it as a tuple of one element.
                return result[0]
            #If it does not exist, return None
            else :
                return None
    #Stores a piece of text inside table stored_text for later use
    async def storetext(self, textname, textcontent, guildID):
        #Check if we have values for this guild
        async with aiosqlite.connect(bot.dbPath) as db:
            #Check for the desired text
            cursor = await db.execute("SELECT text_name FROM stored_text WHERE guild_id = ? AND text_name = ?", [guildID, textname])
            result = await cursor.fetchone()
            #Updating value if it exists
            if result != None :
                await db.execute("UPDATE stored_text SET guild_id = ?, text_name = ?, text_content = ? WHERE guild_id = ? AND text_name = ?", [guildID, textname, textcontent, guildID, textname])
                await db.commit()
            #If it does not exist, insert it
            else :
                await db.execute("INSERT INTO stored_text (guild_id, text_name, text_content) VALUES (?, ?, ?)", [guildID, textname, textcontent])
                await db.commit()
    #Deletes a single text entry
    async def deltext(self, textname, guildID):
        async with aiosqlite.connect(bot.dbPath) as db:
            await db.execute("DELETE FROM stored_text WHERE text_name = ? AND guild_id = ?", [textname, guildID])
            await db.commit()
            return
    #Get all tags for a guild (Get all text that is not reserved)
    async def getTags(self, guildID):
        async with aiosqlite.connect(bot.dbPath) as db:

            cursor = await db.execute("SELECT text_name FROM stored_text WHERE guild_id = ?", [guildID])
            results = await cursor.fetchall()
            #Fix for tuples
            results = [result[0] for result in results]
            #Remove reserved stuff
            for result in results :
                if result in bot.reservedTextNames :
                    results.remove(result)
            return results

#The main instance of DBHandler
bot.DBHandler = DBhandler()

    
#Custom help command, shows all commands a user can execute based on their priviliges.
#Also has an alternate mode where it shows information about a specific command, if specified as an argument.
@bot.command(brief="Displays this help message.", description="Displays all available commands you can execute, based on your permission level.", usage=f"{prefix}help [command]", aliases=['halp'])
async def help(ctx, commandname : str=None):
    #This uses a custom instance of dbHandler
    dbHandler = DBhandler()
    #Retrieve all commands except hidden, unless user is priviliged.
    
    #Direct copy of hasPriviliged()
    #If user is priviliged, get all commands, including hidden ones, otherwise just the not hidden ones.

    #Note: checkprivs() returns a list of tuples as roleIDs
    userRoles = [role.id for role in ctx.author.roles]
    privroles = await dbHandler.checkprivs(ctx.guild.id)
    
    #Determine how many commands and associated details we need to retrieve, then retrieve them.
    if any(roleID in userRoles for roleID in privroles) or (ctx.author.id == bot.owner_id or ctx.author.id == ctx.guild.owner_id) :
        cmds = [cmd.name for cmd in bot.commands]
        briefs = [cmd.brief for cmd in bot.commands]
        allAliases = [cmd.aliases for cmd in bot.commands]
    else :
        cmds = [cmd.name for cmd in bot.commands if not cmd.hidden]
        briefs = [cmd.brief for cmd in bot.commands if not cmd.hidden]
        allAliases = [cmd.aliases for cmd in bot.commands if not cmd.hidden]
    i = 0
    #Note: allAliases is a matrix of multiple lists, this will convert it into a singular list
    aliases = list(chain(*allAliases))
    helpFooter=f"Requested by {ctx.author.name}#{ctx.author.discriminator}"
    if commandname == None :
        formattedmsg = []
        i = 0
        formattedmsg.append(f"You can also use `{prefix}help <command>` to get more information about a specific command. \n \n")
        for i in range(len(cmds)) :
            if briefs[i] != None :
                formattedmsg.append(f"`{prefix}{cmds[i]}` - {briefs[i]} \n")
            else :
                formattedmsg.append(f"`{prefix}{cmds[i]}` \n")

        final = "".join(formattedmsg)
        embed=discord.Embed(title="⚙️ __Available commands:__", description=final, color=bot.embedBlue)
        embed.set_footer(text=helpFooter, icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)
        return
    else :
        #Oh no, you found me o_o
        if commandname == "Hyper" :
            embed=discord.Embed(title="❓ I can't...", description=f"I am sorry, but he can't be helped. He is beyond redemption.", color=bot.unknownColor)
            embed.set_footer(text="Requested by a stinky person.", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return
        #If our user is a dumbass and types ?help ?command instead of ?help command, we will remove the prefix from it first
        if commandname.startswith(prefix) :
            #Remove first character
            commandname = commandname[0 : 0 : ] + commandname[0 + 1 : :]
        #If found, we will try to retrieve detailed command information about it, and provide it to the user.
        if commandname in cmds or commandname in aliases :
            command = bot.get_command(commandname)
            if len(command.aliases) > 0 :
                #Add the prefix to the aliases before displaying
                commandaliases = ["`" + prefix + alias + "`" for alias in command.aliases]
                #Then join them together
                commandaliases = ", ".join(commandaliases)
                embed=discord.Embed(title=f"⚙️ Command: {prefix}{command.name}", description=f"{command.description} \n \n**Usage:** `{prefix}{command.usage}` \n**Aliases:** {commandaliases}", color=bot.embedBlue)
                embed.set_footer(text=helpFooter, icon_url=ctx.author.avatar_url)
                await ctx.send(embed=embed)
                return
            else :
                command = bot.get_command(commandname)
                embed=discord.Embed(title=f"⚙️ Command: {prefix}{command.name}", description=f"{command.description} \n \n**Usage:** `{prefix}{command.usage}`", color=bot.embedBlue)
                embed.set_footer(text=helpFooter, icon_url=ctx.author.avatar_url)
                await ctx.send(embed=embed)
                return
        else :
            embed=discord.Embed(title="❓ Unknown command!", description=f"Use `{prefix}help` for a list of available commands.", color=bot.unknownColor)
            embed.set_footer(text=helpFooter, icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return
#
#
#Error handler
#
#
#Generic error handling. Will catch all otherwise not handled errors
@bot.event
async def on_command_error(ctx, error):
    #This gets sent whenever a user has insufficient permissions to execute a command.
    if isinstance(error, commands.CheckFailure):
        embed=discord.Embed(title=bot.errorCheckFailTitle, description=bot.errorCheckFailDesc, color=bot.errorColor)
        embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandNotFound):
        #This is a fancy suggestion thing that will suggest commands that are similar in case of typos.
        #Get original cmd, and convert it into lowercase as to make it case-insensitive
        cmd = ctx.invoked_with.lower()
        #Gets all cmds and aliases
        cmds = [cmd.name for cmd in bot.commands if not cmd.hidden]
        allAliases = [cmd.aliases for cmd in bot.commands if not cmd.hidden]
        aliases = list(chain(*allAliases))
        #Get close matches
        matches = get_close_matches(cmd, cmds)
        aliasmatches = get_close_matches(cmd, aliases)
        #Check if there are any matches, then suggest if yes.
        if len(matches) > 0:
            embed=discord.Embed(title="❓ Unknown command!", description=f"Did you mean `{prefix}{matches[0]}`?", color=bot.unknownColor)
            embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
        elif len(aliasmatches) > 0:
            embed=discord.Embed(title="❓ Unknown command!", description=f"Did you mean `{prefix}{aliasmatches[0]}`?", color=bot.unknownColor)
            embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
        else:
            embed=discord.Embed(title="❓ Unknown command!", description=f"Use `{prefix}help` for a list of available commands.", color=bot.unknownColor)
            embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandOnCooldown):
        embed=discord.Embed(title=bot.errorCooldownTitle, description=f"Please retry in: `{datetime.timedelta(seconds=round(error.retry_after))}`", color=bot.errorColor)
        embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)
    elif isinstance(error, commands.MissingRequiredArgument):
        embed=discord.Embed(title="❌ Missing argument.", description=f"One or more arguments are missing. \n__Hint:__ You can use `{prefix}help {ctx.command.name}` to view command usage.", color=bot.errorColor)
        embed.set_footer(text=f"Requested by {ctx.author.name}#{ctx.author.discriminator}", icon_url=ctx.author.avatar_url)
        await ctx.send(embed=embed)


    else :
        #If no known error has been passed, we will print the exception to console as usual
        #IMPORTANT!!! If you remove this, your command errors will not get output to console.
        print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

#
# Guild Join/Leave behaviours
#
#Triggered when bot joins a new guild
@bot.event
async def on_guild_join(guild):
    #This forces settings to generate for this guild.
    await bot.DBHandler.retrievesetting("COMMANDSCHANNEL", guild.id)
    if guild.system_channel != None :
        embed=discord.Embed(title="Beep Boop!", description=f"I have been summoned to this server. Use `{prefix}help` to see what I can do!", color=0xfec01d)
        embed.set_thumbnail(url=bot.user.avatar_url)
        await guild.system_channel.send(embed=embed)
    print(f"[INFO]: Bot has been added to new guild {guild.id}.")

#Triggered when bot leaves guild, or gets kicked/banned, or guild gets deleted.
@bot.event
async def on_guild_remove(guild):
    #Erase all settings for this guild on removal to keep the db tidy.
    await bot.DBHandler.deletesettings(guild.id)
    print(f"[INFO]: Bot has been removed from guild {guild.id}, correlating data erased.")

#Keep-On-Top message functionality (Requires setup extension to be properly set up)
@bot.event
async def on_message(message):
    #Check if we are in a guild to avoid exceptions
    if message.guild != None:
        topChannelID = await bot.DBHandler.retrievesetting("KEEP_ON_TOP_CHANNEL", message.guild.id)
        if message.channel.id == topChannelID:
            keepOnTopContent = await bot.DBHandler.retrievetext("KEEP_ON_TOP_CONTENT", message.guild.id)
            if keepOnTopContent != message.content :
                #Get rid of previous message
                previousTop = await message.channel.fetch_message(await bot.DBHandler.retrievesetting("KEEP_ON_TOP_MSG", message.guild.id))
                await previousTop.delete()
                #Send new message
                newTop = await message.channel.send(keepOnTopContent)
                #Set the id to keep the ball rolling
                await bot.DBHandler.modifysettings("KEEP_ON_TOP_MSG", newTop.id, newTop.guild.id)
        elif topChannelID == None :
            print("Settings not found.")
        #This is necessary, otherwise bot commands will break because on_message would override them
    await bot.process_commands(message)


#Run bot with token from .env
try :
    bot.run(TOKEN)
except KeyboardInterrupt :
    pass
