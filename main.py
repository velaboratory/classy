
import asyncio
import json
import discord
import os
from datetime import datetime
from dateutil import parser
import time
import pytz
import random
from discord.ext import commands
import sqlite3
import pandas as pd
try:
    import google.generativeai as genai
except ImportError:
    genai = None
    print("google-generativeai library not found. AI features will be disabled.")
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import io
except ImportError:
    plt = None
    print("matplotlib library not found. Charts will be disabled.")

config = json.loads(open("config.json").read())
classes = config["classes"]
perms = discord.Permissions(8)
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!',intents=intents)
queues = {} # channel_id -> list of members
queue_messages = {} # channel_id -> discord.Message

async def update_queue_display(channel_id):
    if channel_id not in queue_messages:
        return
    
    message = queue_messages[channel_id]
    q = queues.get(channel_id, [])
    
    msg = "**Current Queue:**\n"
    if not q:
        msg += "The queue is empty."
    else:
        for i, member in enumerate(q):
            msg += f"{i+1}. {member.display_name}\n"
            
    try:
        await message.edit(content=msg)
    except (discord.NotFound, discord.HTTPException):
        if channel_id in queue_messages:
            del queue_messages[channel_id]

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

@bot.tree.command(name="checkin", description="Check in to the current class")
async def checkin(interaction: discord.Interaction):
    channel = interaction.channel
    member = interaction.user
    period = get_period(channel.name)
    if period:
        if member.name not in period["checked_in"]:
            with db_connection() as con:
                nick = member.nick if hasattr(member, "nick") and member.nick else member.name
                df = pd.DataFrame({"course":[channel.name],"member":[nick],"discord_id":[member.name],"time":[datetime.now().strftime("%Y-%m-%d %H:%M:%S")],"index":[0]})
                df.to_sql("checkins",con,index=False,if_exists='append')
            period["checked_in"].append(member.name)
            await interaction.response.send_message("You are checked in", ephemeral=True)
        else:
            await interaction.response.send_message("You were already checked in", ephemeral=True)
        
    else:
        await interaction.response.send_message("The period is not active", ephemeral=True)

@bot.tree.command(name="attendance", description="View attendance")
async def attendance(interaction: discord.Interaction):
    channel = interaction.channel
    member = interaction.user

    if hasattr(member, "roles") and discord.utils.get(member.roles, name="Admin"): 
        with db_connection() as con:
            df = pd.read_sql("select distinct member from checkins where course=? and date(time)=?",con,params=(channel.name,datetime.now().strftime("%Y-%m-%d")))
            await interaction.response.send_message(f"```{df.to_string(index=False)}```", ephemeral=True)
    else:
        with db_connection() as con:
            df = pd.read_sql("select date from checkins where course=? and discord_id=?",con,params=(channel.name,member.name))
            await interaction.response.send_message(f"```{df.to_string(index=False)}```", ephemeral=True)

class PollView(discord.ui.View):
    def __init__(self, question: str, options: list[str], author: discord.Member):
        super().__init__(timeout=None)
        self.question = question
        self.options = options
        self.author = author
        self.votes = {} 

        for i, option in enumerate(options):
            button = discord.ui.Button(label=option, style=discord.ButtonStyle.primary, custom_id=f"poll_btn_{i}")
            button.callback = self.create_callback(i, option)
            self.add_item(button)
        
        end_btn = discord.ui.Button(label="End Poll", style=discord.ButtonStyle.danger, row=4, custom_id="poll_end")
        end_btn.callback = self.end_poll_callback
        self.add_item(end_btn)

    def create_callback(self, index, label):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id in self.votes:
                await interaction.response.send_message("You have already voted.", ephemeral=True)
                return
            self.votes[interaction.user.id] = index
            await interaction.response.send_message(f"Vote recorded for: {label}", ephemeral=True)
        return callback

    async def end_poll_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the poll creator can end this poll.", ephemeral=True)
            return

        counts = {i: 0 for i in range(len(self.options))}
        for v in self.votes.values():
            counts[v] += 1
        
        res = f"**Poll Ended: {self.question}**\n"
        for i, opt in enumerate(self.options):
            res += f"{opt}: {counts[i]}\n"
        
        for child in self.children:
            child.disabled = True
        
        file = None
        if plt:
            try:
                plt.figure(figsize=(6, 4))
                plt.bar(self.options, [counts[i] for i in range(len(self.options))])
                plt.title(self.question)
                plt.ylabel("Votes")
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format='png')
                buf.seek(0)
                file = discord.File(buf, filename='poll_chart.png')
                plt.close()
            except Exception as e:
                print(f"Chart error: {e}")

        if file:
            await interaction.response.edit_message(content=res, embed=None, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(content=res, embed=None, view=self)
        
        details = "**Detailed Votes:**\n"
        results_data = []
        for uid, v_idx in self.votes.items():
            u = interaction.guild.get_member(uid)
            name = u.display_name if u else str(uid)
            username = u.name if u else "Unknown"
            details += f"{name} ({username}) -> {self.options[v_idx]}\n"
            results_data.append({"name": name, "username": username, "vote": self.options[v_idx], "id": uid})

        if not os.path.exists("polls"):
            os.makedirs("polls")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_question = "".join(x for x in self.question if x.isalnum())[:20]
        filename = f"polls/{timestamp}_{safe_question}.csv"
        pd.DataFrame(results_data).to_csv(filename, index=False)
        details += f"\nResults saved to `{filename}`"
        
        await interaction.followup.send(details, ephemeral=True)

class PollAnswerModal(discord.ui.Modal):
    def __init__(self, view_ref):
        super().__init__(title="Submit Answer")
        self.view_ref = view_ref
        self.answer = discord.ui.TextInput(label="Your Answer", style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id in self.view_ref.answers:
             await interaction.response.send_message("You have updated your answer.", ephemeral=True)
        else:
             await interaction.response.send_message("Answer recorded.", ephemeral=True)
        self.view_ref.answers[interaction.user.id] = self.answer.value

class OpenPollView(discord.ui.View):
    def __init__(self, question: str, author: discord.Member):
        super().__init__(timeout=None)
        self.question = question
        self.author = author
        self.answers = {} # id -> text

    @discord.ui.button(label="Answer Poll", style=discord.ButtonStyle.success, custom_id="open_poll_answer")
    async def answer_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PollAnswerModal(self))

    @discord.ui.button(label="End Poll", style=discord.ButtonStyle.danger, custom_id="open_poll_end")
    async def end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the poll creator can end this poll.", ephemeral=True)
            return
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        results_data = []
        txt_responses = []
        
        for uid, ans in self.answers.items():
            u = interaction.guild.get_member(uid)
            name = u.display_name if u else str(uid)
            username = u.name if u else "Unknown"
            results_data.append({"name": name, "username": username, "answer": ans, "id": uid})
            txt_responses.append(ans)

        if not os.path.exists("polls"):
            os.makedirs("polls")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_question = "".join(x for x in self.question if x.isalnum())[:20]
        filename = f"polls/{timestamp}_{safe_question}_open.csv"
        pd.DataFrame(results_data).to_csv(filename, index=False)
        
        summary_text = "No API key provided or library missing."
        if genai and "gemini_api_key" in config:
            try:
                genai.configure(api_key=config["gemini_api_key"])
                model = genai.GenerativeModel('gemini-3-flash-preview')
                prompt = f"Summarize the following responses to the question: '{self.question}'\n\nResponses:\n" + "\n".join([f"- {r}" for r in txt_responses])
                response = await asyncio.to_thread(model.generate_content, prompt)
                summary_text = response.text
            except Exception as e:
                summary_text = f"Error generating summary: {e}"

        final_content = f"**Poll Ended: {self.question}**\n\n**Summary:**\n{summary_text}"
        if len(final_content) > 2000:
            final_content = final_content[:1990] + "..."
        await interaction.message.edit(content=final_content, embed=None, view=self)
        await interaction.followup.send(f"Detailed responses saved to `{filename}`", ephemeral=True)

@bot.tree.command(name="poll", description="Create a poll")
@discord.app_commands.describe(question="The question to ask", options="Comma separated list of options (e.g. Yes,No)", open_ended="Set to True for text answers")
async def poll(interaction: discord.Interaction, question: str, options: str = None, open_ended: bool = False):
    if not (hasattr(interaction.user, "roles") and discord.utils.get(interaction.user.roles, name="Admin")):
        await interaction.response.send_message("You do not have permission to create a poll.", ephemeral=True)
        return

    if open_ended:
        view = OpenPollView(question, interaction.user)
        embed = discord.Embed(title=question, description="Click the button below to answer.", color=0x00ff00)
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed, view=view)
        return

    if options:
        opts = [opt.strip() for opt in options.split(",") if opt.strip()]
    else:
        opts = ["Yes", "No"]

    if not opts:
        await interaction.response.send_message("Invalid options provided.", ephemeral=True)
        return
    if len(opts) > 20:
        await interaction.response.send_message("You can only have up to 20 options.", ephemeral=True)
        return

    view = PollView(question, opts, interaction.user)
    embed = discord.Embed(title=question, description="Vote by clicking the buttons below.", color=0x00ff00)
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed, view=view)

class RegisterModal(discord.ui.Modal):
    def __init__(self, class_info):
        super().__init__(title=f"Register for {class_info['name']}")
        self.class_info = class_info
        
        self.full_name = discord.ui.TextInput(label="Full Name", placeholder="John Doe", required=True)
        self.add_item(self.full_name)

        if class_info["password"]:
            self.password = discord.ui.TextInput(label="Class Password", placeholder="Enter password", required=True)
            self.add_item(self.password)
        else:
            self.password = None

    async def on_submit(self, interaction: discord.Interaction):
        if self.password and self.password.value != self.class_info["password"]:
            await interaction.response.send_message("Invalid password provided.", ephemeral=True)
            return
        
        guild = bot.guilds[0]
        member = guild.get_member(interaction.user.id)
        role = discord.utils.get(guild.roles, name=self.class_info["role"])
        
        if not role:
             await interaction.response.send_message(f"Role {self.class_info['role']} not found.", ephemeral=True)
             return

        try:
            await member.add_roles(role)
            await member.edit(nick=self.full_name.value)
            await interaction.response.send_message(f"Successfully registered for {self.class_info['name']}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Registered, but could not update nickname/role: {e}", ephemeral=True)

class RegisterSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=c["name"], value=str(i)) for i, c in enumerate(classes)]
        super().__init__(placeholder="Select a class...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RegisterModal(classes[int(self.values[0])]))

@bot.tree.command(name="register", description="Register for a class")
async def register(interaction: discord.Interaction):
    await interaction.response.send_message("Please select a class:", view=discord.ui.View().add_item(RegisterSelect()), ephemeral=True)

class AskView(discord.ui.View):
    def __init__(self, author: discord.Member):
        super().__init__(timeout=None)
        self.author = author
    
    @discord.ui.button(label="Reveal Author (Admin)", style=discord.ButtonStyle.secondary, custom_id="ask_reveal")
    async def reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if hasattr(interaction.user, "roles") and discord.utils.get(interaction.user.roles, name="Admin"):
            await interaction.response.send_message(f"Asked by: {self.author.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("Only admins can reveal the author.", ephemeral=True)

@bot.tree.command(name="ask", description="Ask a question anonymously")
async def ask(interaction: discord.Interaction, question: str):
    embed = discord.Embed(title="Anonymous Question", description=question, color=0xFFA500)
    await interaction.channel.send(embed=embed, view=AskView(interaction.user))
    await interaction.response.send_message("Question sent anonymously.", ephemeral=True)

class QueueGroup(discord.app_commands.Group):
    def __init__(self):
        super().__init__(name="queue", description="Manage the class queue")

    @discord.app_commands.command(name="join", description="Join the queue")
    async def join(self, interaction: discord.Interaction):
        if interaction.channel_id not in queues:
            queues[interaction.channel_id] = []
        
        q = queues[interaction.channel_id]
        if any(u.id == interaction.user.id for u in q):
            await interaction.response.send_message("You are already in the queue.", ephemeral=True)
            return
        
        q.append(interaction.user)
        await interaction.response.send_message(f"Joined the queue. Position: {len(q)}", ephemeral=True)
        await update_queue_display(interaction.channel_id)

    @discord.app_commands.command(name="leave", description="Leave the queue")
    async def leave(self, interaction: discord.Interaction):
        q = queues.get(interaction.channel_id, [])
        
        original_len = len(q)
        queues[interaction.channel_id] = [u for u in q if u.id != interaction.user.id]
        
        if len(queues[interaction.channel_id]) < original_len:
            await interaction.response.send_message("You have left the queue.", ephemeral=True)
            await update_queue_display(interaction.channel_id)
        else:
            await interaction.response.send_message("You are not in the queue.", ephemeral=True)

    @discord.app_commands.command(name="list", description="View the current queue")
    async def list_queue(self, interaction: discord.Interaction):
        q = queues.get(interaction.channel_id, [])
        
        msg = "**Current Queue:**\n"
        if not q:
            msg += "The queue is empty."
        else:
            for i, member in enumerate(q):
                msg += f"{i+1}. {member.display_name}\n"
        
        if interaction.channel_id in queue_messages:
            try: await queue_messages[interaction.channel_id].delete()
            except: pass
        await interaction.response.send_message(msg)
        queue_messages[interaction.channel_id] = await interaction.original_response()

    @discord.app_commands.command(name="next", description="Call the next student (Admin only)")
    async def next_student(self, interaction: discord.Interaction):
        if not (hasattr(interaction.user, "roles") and discord.utils.get(interaction.user.roles, name="Admin")):
            await interaction.response.send_message("Only admins can use this.", ephemeral=True)
            return

        q = queues.get(interaction.channel_id, [])
        if not q:
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        
        member = q.pop(0)
        await interaction.response.send_message(f"Next up: {member.mention}")
        await update_queue_display(interaction.channel_id)

    @discord.app_commands.command(name="clear", description="Clear the queue (Admin only)")
    async def clear(self, interaction: discord.Interaction):
        if not (hasattr(interaction.user, "roles") and discord.utils.get(interaction.user.roles, name="Admin")):
            await interaction.response.send_message("Only admins can use this.", ephemeral=True)
            return
        
        queues[interaction.channel_id] = []
        await interaction.response.send_message("Queue cleared.")
        await update_queue_display(interaction.channel_id)

bot.tree.add_command(QueueGroup())

@bot.tree.command(name="coldcall", description="Pick a random student who is checked in")
async def coldcall(interaction: discord.Interaction):
    if not (hasattr(interaction.user, "roles") and discord.utils.get(interaction.user.roles, name="Admin")):
        await interaction.response.send_message("Only admins can use this.", ephemeral=True)
        return
    
    channel = interaction.channel
    with db_connection() as con:
        df = pd.read_sql("select distinct member from checkins where course=? and date(time)=?", con, params=(channel.name, datetime.now().strftime("%Y-%m-%d")))
    
    if df.empty:
        await interaction.response.send_message("No students are checked in yet.", ephemeral=True)
    else:
        student = df.sample().iloc[0]['member']
        await interaction.response.send_message(f"🎲 Random Pick: **{student}**")

@bot.event
async def on_ready():
    print('We have logged in as {0.user}'.format(bot))
    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()
    if not hasattr(bot, "schedule_started"):
        bot.loop.create_task(check_schedule())
        bot.schedule_started = True

@bot.event
async def on_message(message: discord.Message):

    is_dm = type(message.channel) is discord.DMChannel
    if not is_dm:
        await bot.process_commands(message)
    if message.author == bot.user:  #from the discord bot.   Probably should ignore
        return
        

@bot.event
async def on_member_join(member: discord.Member):

    await member.send(f"Welcome to the server.  If you would like to register for a course, please use the `/register` command in the server.")

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
                role = discord.utils.get(bot.guilds[0].roles,name=cl["role"])
                await channel.send(f"{role.mention} time to check in.")
                            

bot.run(config["key"])
