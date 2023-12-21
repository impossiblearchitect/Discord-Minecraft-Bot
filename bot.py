import discord
from discord.ext import commands
import mcrcon
import os
import asyncio
# from pyngrok import ngrok
from mcstatus import JavaServer
import time
import json

intents = discord.Intents.all()
intents.typing = True
intents.presences = True
intents.messages = True

def load_credentials():
    with open('config.json') as file:
        #get the credentials from the config.json file
        credentials = json.load(file) 
    return credentials

credentials = load_credentials()

prefix = credentials['prefix'] #command prefix
bot_token = credentials['token'] #bot's private token
ip_channel_id = credentials['channel_for_ip'] #channel id for the ip(?)
chat_channel_id = credentials['channel_for_chat'] #channel id for (synced?) chat
log_channel_id = credentials['channel_for_log'] #channel id for server log
log_path = credentials['path_to_latestlog'] # path to logs/latest.log (the folder or the file?)
rcon_host = credentials['minecraft_ip'] #localhost
rcon_port = credentials['rcon_port'] #25575
ip_port = credentials['ip_port'] #25565
rcon_password = credentials['rcon_password'] #rcon password
server_name = credentials['server_name'] #server name
admin = credentials['admin_role']# the role required to execute the "commands" command
wait_server = credentials['wait_server'] #time to wait for the server (to start?)

filter = ['Thread RCON Client', '[Server thread/INFO]: RCON']# filter RCON lines
max_players_to_show = 10 #maximum number of players that the "players" command can show

bot = commands.Bot(command_prefix=prefix, intents=intents)

bot.remove_command('help')

# nueva_ip = None
progress ={}
current_time={}

async def check_server_and_rcon_connection():
    embed = discord.Embed(title="Bot Status", color=discord.Color.red())

    last_line = await get_last_line(log_path)
    if last_line is not None:
        embed.add_field(name="Last Log Line", value="Obtained last line from log file.")
    else:
        embed.add_field(name="Last Log Line", value="Failed to obtain last line from log file.")

    try:
        server = JavaServer(rcon_host, ip_port)
        status = server.status()
        embed.add_field(name="Server Connection", value="Connection established successfully.")
    except Exception as e:
        embed.add_field(name="Server Connection", value="Failed to establish connection.")
        embed.add_field(name="Error", value=str(e))

    try:
        with mcrcon.MCRcon(rcon_host, rcon_password, rcon_port) as rcon:
            embed.add_field(name="RCON Connection", value="Connection established successfully.")
    except Exception as e:
        embed.add_field(name="RCON Connection", value="Failed to establish connection.")
        embed.add_field(name="Error", value=str(e))

    return embed

async def botstatus(ctx):
    if not any(role.name == admin for role in ctx.author.roles):
        await ctx.send(f"You do not have the necessary permissions to execute this command.")
        return
    embed = await check_server_and_rcon_connection()
    await ctx.send(embed=embed)

def create_embed(server_status: str, player_status: str):
    global server_name
    embed = discord.Embed(title=server_name, color=discord.Color.blue())
    embed.add_field(name="Status", value=server_status, inline=False)
    # embed.add_field(name="IP Address", value=address, inline=False)
    embed.add_field(name="Players", value=player_status, inline=False)
    embed.set_footer(text="Updates every minute")
    return embed


async def check_log():
    await bot.wait_until_ready()
    channel = bot.get_channel(log_channel_id)
    previous_line = ""
    while not bot.is_closed():
        last_line = await get_last_line(log_path)
        if last_line and last_line != previous_line and not word_filter(last_line):
            await channel.send(last_line)
            previous_line = last_line
        await asyncio.sleep(0.5)


async def purge_channel():
    channel = bot.get_channel(log_channel_id)
    deleted = 0
    while True:
        messages = []
        async for message in channel.history(limit=100):
            messages.append(message)
        if not messages:
            print('No more messages to delete.')
            break
        await channel.delete_messages(messages)
        deleted += len(messages)
        print(f'Deleted {deleted} messages.')
        if len(messages) < 100:
            print('No more messages can be deleted due to Discord API limitations, or channel is empty.')
            break
        await asyncio.sleep(1)


async def minecraft_to_discord():
    global chat_channel_id
    await bot.wait_until_ready()
    chat_channel = bot.get_channel(chat_channel_id)

    previous_line = ""
    while not bot.is_closed():
        last_line = await get_last_line(log_path)
        if last_line and last_line != previous_line:
            if "" in last_line and "INFO]:" in last_line and "<" in last_line:
                player_message = last_line.split("<", 1)[1]
                await chat_channel.send(player_message)
            previous_line = last_line
        await asyncio.sleep(0.5)



@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == chat_channel_id:
        username = message.author.name
        content = message.content
        command = f'tellraw @a ["",{{"text":"[Discord]","color":"aqua"}},{{"text":" {username} "}},{{"text":":","color":"gray"}},{{"text":" {content}","color":"white"}}]'
        with mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port) as rcon:
            response = rcon.command(command)
            print(response)

    if bot.user.mentioned_in(message):
        if message.author != bot.user:
            player_count = await get_player_count(rcon_host, ip_port)
            if player_count is None:
                server_status = "offline"
            elif player_count == 0:
                server_status = "idle"
            else:
                server_status = "online"
            # ip = nueva_ip  # Variable global con la dirección IP del servidor
            response = f"Hello {message.author.mention}.\nThe server {server_name} is currently {server_status}" \
                       f"with {player_count} online.\n This bot's prefix is: {prefix}"
            await message.channel.send(response)

    await bot.process_commands(message)




@bot.event
async def on_ready():
    print(f'Bot connected as {bot.user.name}')
    # global nueva_ip
    bot.loop.create_task(check_log())
    bot.loop.create_task(minecraft_to_discord())
    await purge_channel()

    await bot.change_presence(activity=discord.Game(name=f'{prefix}ayuda'))
    
    # ngrok_tunnel = ngrok.connect(ip_port, 'tcp')

    # nueva_ip = ngrok_tunnel.public_url.replace("tcp://", "")

    # print("=== IP Details ===")
    # print(f"IP Address: {nueva_ip}")
    # print(f"Full Public URL: {ngrok_tunnel.public_url}")
    # print(f"Protocol: {ngrok_tunnel.proto}")
    # print(f"========================")

    channel = bot.get_channel(ip_channel_id)

    async for message in channel.history():
        if message.author == bot.user and isinstance(message.embeds, list) and len(message.embeds) > 0:
            await message.delete()

    # await channel.edit(topic=f'Encendiendo servidor -\n IP pública: {nueva_ip}')
    
    create_embed("Connecting to server", "-")

    await asyncio.sleep(wait_server)
    
    player_count = await get_player_count(rcon_host, ip_port)
    if player_count is not None:
        print("Connection established to server.")
    else:
        print("Could not establish connection to server.")
    
    while True:
        player_count = await get_player_count(rcon_host, ip_port)
        if player_count is None:
            description = f"Server offline"
            server_status = "offline"
            player_count = "-"
        elif player_count == 0:
            description = f"Server idle"
            server_status = "idle"
            player_count = "0"
        else:
            description= f"Server online"
            server_status = "online"
            player_count = str(player_count)

        await channel.edit(topic=description)

        message_embed = create_embed(server_status, player_count)

        async for message in channel.history():
            if message.author == bot.user and isinstance(message.embeds, list) and len(message.embeds) > 0:
                await message.edit(embed=message_embed)
                break
        else:
            await channel.send(embed=message_embed)
    
        await asyncio.sleep(60)


# This function is used to prevent spamming commands
# and potentially could be modified to restrict the use
# of some commands to administrators
# It returns True if the command should be ignored.
async def control(ctx,prkey,wait):
    global admin

    if ctx.author.bot:
        return True

    if any(role.name == admin for role in ctx.author.roles):
        return False

    if not prkey in progress or not progress.get(prkey):
        progress[prkey] = True
        current_time[prkey] = time.time()
        return False

    if time.time() - current_time.get(prkey) < wait and progress.get(prkey):
        return True

    progress[prkey]= False
    return False


async def get_player_count(ip, puerto):
    try:
        server = JavaServer(ip, puerto)
        status = server.status()
        return status.players.online
    except Exception as e:
        print(f"Error getting players: {e}")
        return None


async def get_last_line(filename):
    with open(filename, 'rb') as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b'\n':
            f.seek(-2, os.SEEK_CUR)
        last_line = f.readline().decode().strip()
    return last_line


def word_filter(text):
    for word in filter:
        if word.lower() in text.lower():
            return True
    return False



# @bot.command(aliases=['IP', 'Ip', 'server', 'servidor', 'Server', 'Servidor'])
# async def ip(ctx):
#     if await control(ctx, 'ip', 3):
#         return
    # if nueva_ip is not None:
    #     await ctx.send(f'Esta es la IP del servidor: {nueva_ip}')
    # else:
    #     await ctx.send('La IP del servidor aún no está disponible.')


@bot.command(aliases=['players', 'Players', 'Player', 'list' , 'List'])
async def players(ctx):
    if await control(ctx, 'players', 3):
        return
    with mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port) as rcon:
        response = rcon.command('list')
        players = response.split(':')[1].strip().split(', ')

        if len(players) == 1 and players[0] == '':
            await ctx.send("There are no players online.")
            return

        players_remaining = len(players) - max_players_to_show

        if players_remaining > 0:
            players_list = '\n'.join(players[:max_players_to_show])
            players_list += f'\n... and {players_remaining} more.'
        else:
            players_list = '\n'.join(players)

        embed = discord.Embed(title='Players Online', description=players_list, color=discord.Color.blue())
        await ctx.send(embed=embed)

@bot.command(aliases=['help', 'H', 'h', 'Help', 'commands' , 'Commands'])
async def help(ctx):
    if await control(ctx, 'help', 3):
        return
    embed = discord.Embed(title='Comando de Ayuda', color=discord.Color.green())

    commands_info = [
        {'name': 'players', 'description': 'Lists online players.'},
        # {'name': 'command', 'description': 'Runs a command in the server console (server admins only).'},
        {'name': 'botstatus', 'description': 'Displays connection information with the server (server admins only).'},
        {'name': 'help', 'description': 'Display this message.'},
        {'name': 'mention', 'description': 'You can @mention the bot to get the server status.'},
    ]

    for cmd_info in commands_info:
        command_name = cmd_info['name']
        command_description = cmd_info['description']
        embed.add_field(name=command_name, value=command_description, inline=False)

    await ctx.send(embed=embed)

# @bot.command(aliases=['comand', 'Comando', 'Comand', 'Command', 'command', 'execute' , 'Execute' , 'exe' , 'Exe' , 'ejecutar' , 'Ejecutar'])
# async def comando(ctx, *, command):
#     global admin
#     if not any(role.name == admin for role in ctx.author.roles):
#         await ctx.send(f"No tienes los permisos necesarios para ejecutar este comando.")
#         return
#     with mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port) as rcon:
#         response = rcon.command(command)
#         await ctx.send(f'Respuesta de la consola: {response}')

bot.run(bot_token)

