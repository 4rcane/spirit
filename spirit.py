from discord.ext import commands
from database import DBase
from datetime import datetime
import json
import discord
import asyncio
import re

bot = commands.Bot(command_prefix='!')

@bot.group(pass_context=True)
async def event(ctx):

    if ctx.invoked_subcommand is None:
        return await bot.say(ctx.message.author.mention
                             + ": Invalid event command passed. "
                             + "Use '!event help' to view available commands.")

async def events_channel(ctx):

    event_channel = None
    if ctx.message.channel.name != "upcoming-events":
        for channel in ctx.message.server.channels:
            if channel.name == "upcoming-events":
                event_channel = channel
                break
        if event_channel is None:
            event_channel = await bot.create_channel(ctx.message.server, "upcoming-events")
        await bot.say(ctx.message.author.mention + ": That command can only be used in the "
                      + event_channel.mention + " channel.")
        return False
    else:
        return True

@event.command(pass_context=True)
async def create(ctx):

    if not await events_channel(ctx):
        return

    await bot.say(ctx.message.author.mention + ": Enter event title")
    msg = await bot.wait_for_message(author=ctx.message.author)
    title = msg.content

    await bot.say(ctx.message.author.mention
                  + ": Enter event description (type 'none' for no description)")
    msg = await bot.wait_for_message(author=ctx.message.author)
    description = ''
    if msg.content.upper() != 'NONE':
        description = msg.content

    start_time = None
    while not start_time:
        await bot.say(ctx.message.author.mention + ": Enter event time (YYYY-MM-DD HH:MM AM/PM)")
        msg = await bot.wait_for_message(author=ctx.message.author)
        start_time_str = msg.content
        start_time_format = '%Y-%m-%d %I:%M %p'
        try:
            start_time = datetime.strptime(start_time_str, start_time_format)
        except ValueError:
            await bot.say(ctx.message.author.mention + ": Invalid event time!")

    await bot.say(ctx.message.author.mention + ": Enter the time zone (PST, EST, etc.)")
    msg = await bot.wait_for_message(author=ctx.message.author)
    time_zone = msg.content.upper()

    with DBase() as db:
        db.create_event(title, start_time, time_zone, ctx.message.server.id, description)
    await bot.say(ctx.message.author.mention
                  + ": Event has been created! "
                  + "The list of upcoming events will be updated momentarily.")
    await asyncio.sleep(5)
    await list_events(ctx)


async def list_events(ctx):

    events = None
    with DBase() as db:
        events = db.get_events(ctx.message.server.id)
    if len(events) != 0:
        await bot.purge_from(ctx.message.channel, limit=999, check=check_delete)
        for row in events:
            embed_msg = discord.Embed(color=discord.Colour(3381759))
            embed_msg.set_footer(text="Use '!event delete "
                                       + str(row[0]) + "' to remove this event")
            embed_msg.title = row[1]
            if row[2]:
                embed_msg.description = row[2]
            embed_msg.add_field(name="Time", value=str(row[3]) + row[4], inline=False)
            embed_msg.add_field(name="Accepted", value=row[5])
            embed_msg.add_field(name="Declined", value=row[6])
            msg = await bot.say(embed=embed_msg)
            await bot.add_reaction(msg, "\N{WHITE HEAVY CHECK MARK}")
            await bot.add_reaction(msg, "\N{CROSS MARK}")

def check_delete(m):
    return True;

@bot.event
async def on_reaction_add(reaction, user):

    # If reaction is indicating event attendance,
    # update the database and remove the reaction
    channel_name = reaction.message.channel.name
    author = reaction.message.author
    num_embeds = len(reaction.message.embeds)
    if (channel_name == "upcoming-events"
            and author == bot.user
            and num_embeds is not 0
            and user is not author):
        username = user.name
        footer = reaction.message.embeds[0]['footer']['text']
        event_id = re.search('\d+', footer).group()
        attending = None
        if reaction.emoji == "\N{WHITE HEAVY CHECK MARK}":
            attending = 1
        elif reaction.emoji == "\N{CROSS MARK}":
            attending = 0
        else:
            await asyncio.sleep(1)
            return await bot.remove_reaction(reaction.message, reaction.emoji, user)
        with DBase() as db:
            db.update_attendance(username, event_id, attending)

        # Update contents of event message
        event = None
        with DBase() as db:
            event = db.get_event(event_id)
        embed_msg = discord.Embed(color=discord.Colour(3381759))
        embed_msg.set_footer(text="Use '!event delete " + event_id + "' to remove this event")
        embed_msg.title = event[0][0]
        if event[0][1]:
            embed_msg.description = event[0][1]
        embed_msg.add_field(name="Time", value=str(event[0][2]) + event[0][3], inline=False)
        embed_msg.add_field(name="Accepted", value=event[0][4])
        embed_msg.add_field(name="Declined", value=event[0][5])
        await bot.edit_message(reaction.message, embed=embed_msg)

        # Remove reaction
        await asyncio.sleep(0.5)
        await bot.remove_reaction(reaction.message, reaction.emoji, user)


@bot.command(pass_context=True)
async def role(ctx, role="None"):

    if ctx.message.channel.is_private:
        return await bot.say(ctx.message.author.mention
                             + ": That command is not supported in a direct message.")

    user = str(ctx.message.author)
    role = role.lower().title()
    server_id = ctx.message.server.id
    msg_res = None
    if role == "Titan" or role == "Warlock" or role == "Hunter":
        with DBase() as db:
            db.update_roster(user, role, server_id)
        msg_res = await bot.say(ctx.message.author.mention
                                + ": Your role has been updated!")
    else:
        msg_res = await bot.say(ctx.message.author.mention
                                + ": Oops! Role must be one of: Titan, Hunter, Warlock")

    await asyncio.sleep(5)
    await bot.delete_message(msg_res)
    await bot.delete_message(ctx.message)


@bot.command(pass_context=True)
async def roster(ctx):

    if ctx.message.channel.is_private:
        return await bot.say(ctx.message.author.mention
                             + ": That command is not supported in a direct message.")

    with DBase() as db:
        roster = db.get_roster(ctx.message.server.id)
        if len(roster) != 0:
            message = "```\n"
            for row in roster:
                message += row[0].split("#")[0]
                spaces = 17 - len(row[0].split("#")[0])
                for _ in range (0, spaces):
                    message += " "
                message += row[1] + "\n"
            message += "```"
            embed_msg = discord.Embed(title="Destiny 2 Pre Launch Roster",
                                      description=message, color=discord.Colour(3381759))
            await bot.say(embed=embed_msg)
        else:
            msg_res = await bot.say(ctx.message.author.mention
                                    + ": No roles have been assigned yet. "
                                    + "Use !role to select a role.")
            await asyncio.sleep(5)
            await bot.delete_message(msg_res)
            await bot.delete_message(ctx.message)


@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')


def load_credentials():
    with open('credentials.json') as f:
        return json.load(f)


if __name__ == '__main__':
    credentials = load_credentials()
    token = credentials['token']
    bot.run(token)