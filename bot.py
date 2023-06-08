import discord
from discord.ext import commands
import mcrcon
import os
import asyncio
from pyngrok import ngrok
from mcstatus import JavaServer
import time
import json

intents = discord.Intents.all()
intents.typing = True
intents.presences = True
intents.messages = True

def load_credentials():
    with open('config.json') as file:
        credentials = json.load(file)#obtener las credenciales de config.json
    return credentials

credentials = load_credentials()

prefix = credentials['prefix'] #prefix de los comandos
bot_token = credentials['token'] #token privado del bot
ip_channel_id = credentials['channel_for_ip'] #canal de la ip
chat_channel_id = credentials['channel_for_chat'] #canal del chat vinculado
log_channel_id = credentials['channel_for_log'] #canal del registro
log_path = credentials['path_to_latestlog'] #ubicacion de: logs/latest.log
rcon_host = credentials['minecraft_ip'] #localhost
rcon_port = credentials['rcon_port'] #25575
ip_port = credentials['ip_port'] #25565
rcon_password = credentials['rcon_password'] #contraseña del rcon
server_name = credentials['server_name'] #nombre del servidor
admin = credentials['admin_role']# el rol necesario para ejecutar el comando "comando"
wait_server = credentials['wait_server'] #yo pongo 30 segundos pero tal vez 20 sean suficiente

filter = ['Thread RCON Client', '[Server thread/INFO]: RCON']# filter RCON lines
max_players_to_show = 10 #Numero de jugadores maximos que se peuden mostrar en el comando "jugadores"

bot = commands.Bot(command_prefix=prefix, intents=intents)

bot.remove_command('help')

nueva_ip = None
progress ={}
current_time={}

def create_embed(texto1, texto2, texto3):
    global server_name
    embed = discord.Embed(title=server_name, color=discord.Color.blue())
    embed.add_field(name="Estado", value=texto1, inline=False)
    embed.add_field(name="Dirección IP", value=texto2, inline=False)
    embed.add_field(name="Jugadores", value=texto3, inline=False)
    embed.set_footer(text="Se actualiza cada minuto")
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
            print('No se encontraron más mensajes para borrar.')
            break
        await channel.delete_messages(messages)
        deleted += len(messages)
        print(f'Borrados {deleted} mensajes en total')
        if len(messages) < 100:
            print('No se pueden borrar más mensajes debido a las restricciones de Discord, o no hay mas mensajes en el canal.')
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
    await bot.process_commands(message)




@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user.name}}')
    global nueva_ip
    bot.loop.create_task(check_log())
    bot.loop.create_task(minecraft_to_discord())
    await purge_channel()

    await bot.change_presence(activity=discord.Game(name="{prefix}ayuda"))
    
    ngrok_tunnel = ngrok.connect(ip_port, 'tcp')

    nueva_ip = ngrok_tunnel.public_url.replace("tcp://", "")

    print("=== IP Details ===")
    print(f"Dirección IP: {nueva_ip}")
    print(f"URL pública completa: {ngrok_tunnel.public_url}")
    print(f"Protocolo: {ngrok_tunnel.proto}")
    print(f"========================")

    canal = bot.get_channel(ip_channel_id)

    async for mensaje in canal.history():
        if mensaje.author == bot.user and isinstance(mensaje.embeds, list) and len(mensaje.embeds) > 0:
            await mensaje.delete()

    await canal.edit(topic=f'Encendiendo servidor -\n IP pública: {nueva_ip}')
    
    create_embed("Enecndiendo servidor", nueva_ip, "-")

    await asyncio.sleep(wait_server)
    
    jugadores = await get_players(rcon_host, ip_port)
    if jugadores is not None:
        print("Conexión establecida con el servidor")
    else:
        print("No se pudo establecer conexión con el servidor")
    
    while True:
        jugadores = await get_players(rcon_host, ip_port)
        if jugadores is not None:
            descripcion = f'Jugadores: {jugadores} -\nIP pública: {nueva_ip}'
            texto1 = "Online"
            texto2 = f"{nueva_ip}"
            texto3 = f"{jugadores}"
        else:
            descripcion = f'Servidor apagado -\nIP pública: {nueva_ip}'
            texto1 = "Apagado"
            texto2 = f"{nueva_ip}"
            texto3 = "-"

        await canal.edit(topic=descripcion)

        mensaje_embebido = create_embed(texto1, texto2, texto3)

        async for mensaje in canal.history():
            if mensaje.author == bot.user and isinstance(mensaje.embeds, list) and len(mensaje.embeds) > 0:
                await mensaje.edit(embed=mensaje_embebido)
                break
        else:
            await canal.send(embed=mensaje_embebido)
    
        await asyncio.sleep(60)



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


async def get_players(ip, puerto):
    try:
        server = JavaServer(ip, puerto)
        status = server.status()
        return status.players.online
    except Exception as e:
        print(f"Error al obtener los jugadores: {e}")
        return None


async def get_last_line(filename):
    with open(filename, 'rb') as f:
        f.seek(-2, os.SEEK_END)
        while f.read(1) != b'\n':
            f.seek(-2, os.SEEK_CUR)
        last_line = f.readline().decode().strip()
    return last_line


def word_filter(texto):
    for palabra in filter:
        if palabra.lower() in texto.lower():
            return True
    return False



@bot.command(aliases=['IP', 'Ip', 'server', 'servidor', 'Server', 'Servidor'])
async def ip(ctx):
    if await control(ctx, 'ip', 3):
        return
    if nueva_ip is not None:
        await ctx.send(f'Esta es la IP del servidor: {nueva_ip}')
    else:
        await ctx.send('La IP del servidor aún no está disponible.')


@bot.command(aliases=['jugador', 'Jugadores', 'Jugador', 'lista', 'Lista', 'list' , 'List'])
async def jugadores(ctx):
    if await control(ctx, 'jugadores', 3):
        return
    with mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port) as rcon:
        response = rcon.command('list')
        players = response.split(':')[1].strip().split(', ')

        if len(players) == 1 and players[0] == '':
            await ctx.send("No hay jugadores en el servidor actualmente.")
            return

        players_remaining = len(players) - max_players_to_show

        if players_remaining > 0:
            players_list = '\n'.join(players[:max_players_to_show])
            players_list += f'\n... y {players_remaining} más.'
        else:
            players_list = '\n'.join(players)

        embed = discord.Embed(title='Lista de Jugadores', description=players_list, color=discord.Color.blue())
        await ctx.send(embed=embed)

@bot.command(aliases=['ayuda', 'H', 'h', 'Ayuda', 'comandos' , 'Comandos'])
async def help(ctx):
    if await control(ctx, 'help', 3):
        return
    embed = discord.Embed(title='Comando de Ayuda', color=discord.Color.green())

    commands_info = [
        {'name': 'ip', 'description': 'Muestra la IP del servidor.'},
        {'name': 'players', 'description': 'Muestra la lista de jugadores en el servidor.'},
        {'name': 'command', 'description': 'Ejecuta un comando en la consola del servidor (solo para administradores).'},
        {'name': 'help', 'description': 'Muestra este mensaje.'},
    ]

    for cmd_info in commands_info:
        command_name = cmd_info['name']
        command_description = cmd_info['description']
        embed.add_field(name=command_name, value=command_description, inline=False)

    await ctx.send(embed=embed)

@bot.command(aliases=['comand', 'Comando', 'Comand', 'Command', 'command', 'execute' , 'Execute' , 'exe' , 'Exe' , 'ejecutar' , 'Ejecutar'])
async def comando(ctx, *, command):
    global admin
    if not any(role.name == admin for role in ctx.author.roles):
        await ctx.send(f"No tienes los permisos necesarios para ejecutar este comando.")
        return
    with mcrcon.MCRcon(rcon_host, rcon_password, port=rcon_port) as rcon:
        response = rcon.command(command)
        await ctx.send(f'Respuesta de la consola: {response}')

bot.run(bot_token)

