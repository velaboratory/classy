
import asyncio
import json
import discord
from datetime import datetime, timedelta
from dateutil import parser
import time
import pytz
from discord.ext import commands
import sqlite3
import pandas as pd

config = json.loads(open("config.json").read())
classes = config["classes"]
perms = discord.Permissions(8)
intents = discord.Intents.default()
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix='!',intents=intents)

def db_connection():
    return sqlite3.connect("classes.db")

def get_period(channel: str): #if the period is active, it'll return the period, otherwise it'll return None
    for cl in classes:

        if cl["channel"] != channel: continue #this is not the channel you are looking for (probably should have used a dictionary)

        lt = datetime.now().astimezone(tz=pytz.timezone(cl["tz"]))
        dayname = lt.strftime("%A").lower()
        current_day = lt.date()
        start_day = parser.parse(cl["start_date"]).date()
        end_day = parser.parse(cl["end_date"]).date()
        exceptions = [parser.parse(d).date() for d in cl["exceptions"]]
        if (current_day < start_day) or (current_day > end_day) or (current_day in exceptions): continue

        #check the periods
        for period in cl["periods"]:
            start_time = datetime.strptime(period["start"],"%I:%M %p").time()
            end_time = datetime.strptime(period['end'],"%I:%M %p").time()
            if (period["day"] == dayname) and (lt.time() >= start_time) and (lt.time() < end_time):
                return period
    return None

def get_end_of_period(channel: str): #if the period was active, and then is not active, it'll return the period, otherwise it'll return None
    for cl in classes:

        if cl["channel"] != channel: continue #this is not the channel you are looking for (probably should have used a dictionary)

        lt = datetime.now().astimezone(tz=pytz.timezone(cl["tz"]))
        dayname = lt.strftime("%A").lower()
        current_day = lt.date()
        start_day = parser.parse(cl["start_date"]).date()
        end_day = parser.parse(cl["end_date"]).date()
        exceptions = [parser.parse(d).date() for d in cl["exceptions"]]
        if (current_day < start_day) or (current_day > end_day) or (current_day in exceptions): continue

        #check the periods
        for period in cl["periods"]:
            start_time = datetime.strptime(period["start"],"%I:%M %p").time()
            end_time = (datetime.strptime(period['end'],"%I:%M %p") - timedelta(minutes=5)).time() #5 minutes before end
            if (period["day"] == dayname) and (lt.hour == end_time.hour) and (lt.minute == end_time.minute):
                return period
    return None

@bot.command()
async def checkin(ctx: commands.Context):
    #get the channel
    channel = ctx.channel
    member = ctx.author
    await ctx.message.delete()
    period = get_period(ctx.channel.name)
    if period:
        if member.name not in period["checked_in"]:
            with db_connection() as con:
                df = pd.DataFrame({"course":[ctx.channel.name],"member":[member.nick],"discord_id":[member.name],"time":[datetime.now().strftime("%Y-%m-%d %H:%M:%S")],"index":[0]})
                df.to_sql("checkins",con,index=False,if_exists='append')
            period["checked_in"].append(member.name)
            await member.send("You are checked in")
        else:
            await member.send("You were already checked in")
        
    else:
        await member.send("The period is not active")

@bot.command()
async def attendance(ctx: commands.Context):
    #get the channel
    channel = ctx.channel
    member: discord.Member = ctx.author
    await ctx.message.delete()

    if discord.utils.get(member.roles, name="Instructor"): 
        with db_connection() as con:
            df = pd.read_sql("select distinct member from checkins where course=? and date(time)=?",con,params=(ctx.channel.name,datetime.now().strftime("%Y-%m-%d")))
            await member.send(df.to_string(index=False))
    else:
        with db_connection() as con:
            df = pd.read_sql("select time from checkins where course=? and discord_id=?",con,params=(channel.name,member.name))
            await member.send(df.to_string(index=False))

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))

@bot.event
async def on_message(message: discord.Message):

    is_dm = type(message.channel) is discord.DMChannel
    if not is_dm:
        await bot.process_commands(message)
    if message.author == bot.user:  #from the discord bot.   Probably should ignore
        return
    if message.content.lower() == 'register':
        
        menu = [f"{num+1} : {cl['name']}" for num,cl in enumerate(classes) ]
        await message.author.send("Please enter 'register' followed by the number of the course you wish to join, followed by the password (if any), followed by your full name,  e.g. register 1 PASSWORD Kyle Johnsen\n" + "\n".join(menu))
    if message.content.lower().startswith('register ') and is_dm:
        parts = message.content.split(' ')
        choice = int(parts[1])-1
        cl = classes[choice]
        name_parts = parts[2:]
        if cl["password"] != "":
            password = parts[2]
            print(password,cl["password"])
            if password != cl["password"]:
                await message.author.send("Invalid password")
                return
            name_parts = parts[3:]
        name = " ".join(name_parts)
        if name.strip() == "":
            await message.author.send("Invalid name, please use your full name")
            return
        
        guild = bot.guilds[0]
        role = discord.utils.get(guild.roles,name=cl["role"])
        member = guild.get_member(message.author.id)
        await member.add_roles(role)
        await member.send(f"Added role: {cl['role']}.  You should now be able to see the course channel.")
        await member.edit(nick=name)
        

@bot.event
async def on_member_join(member: discord.Member):

    await member.send(f"Welcome to the server.  If you would like to register for a course, type 'register'")

async def check_schedule(): # we need to check the schedule to determine if we should remind users to login
    while True:
        await asyncio.sleep(5) 
        t = datetime.now(tz=pytz.utc)

        for cl in classes:
            
            lt = t.astimezone(tz=pytz.timezone(cl["tz"]))
            current_day = lt.date()
            period = get_period(cl["channel"])
            if period == None: continue
            if ("last_sent" not in period) or (period["last_sent"].date() != current_day):
                period["last_sent"] = lt
                #now send the message as a reminder to login
                channel = discord.utils.get(bot.guilds[0].channels,name=cl["channel"])
                period["checked_in"] = [] #cheap way to get rid of the checked_in list
                period["sent_end_of_day"] = False #need to send the end of day
                role = discord.utils.get(bot.guilds[0].roles,name=cl["role"])
                await channel.send(f"{role.mention} time to check in (!checkin)")
            period = get_end_of_period(cl["channel"])
            if period == None: continue
            if ("last_sent" in period) and (period["last_sent"].date() == current_day) and (("sent_end_of_day" not in period) or (not period["sent_end_of_day"])):
                period["sent_end_of_day"] = True
                role = discord.utils.get(bot.guilds[0].roles,name=cl["role"])
                await channel.send(f"{role.mention} last chance to check in (!checkin)")
                
                

bot.loop.create_task(check_schedule())
bot.run(config["key"])