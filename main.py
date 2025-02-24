import discord
from discord.ext import commands
import os, sys
from dotenv import load_dotenv
import yt_dlp
import asyncio

load_dotenv()
DISCORD_TOKEN = os.getenv("discord_token")

if not os.path.exists("audios"):
    os.makedirs("audios")

intents = discord.Intents().all()
bot = commands.Bot(command_prefix='!', intents=intents)

yt_dlp.utils.bug_reports_message = lambda: ''

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': 'audios/%(title)s.%(ext)s', 
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
now_playing = {}  
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

def after_play(ctx, guild_id, filename):
    try:
        os.remove(filename)
    except:
        print("è rotto")

    fut = asyncio.run_coroutine_threadsafe(play_next(ctx, guild_id), bot.loop)
    try:
        fut.result()
    except Exception as e:
        print(e)

@bot.command(name='play', help='')
async def play(ctx, *, url=None):
    if not ctx.message.author.voice:
        await ctx.send(f"{ctx.message.author.name} non è connesso nella chat vocale")
        return

    channel = ctx.message.author.voice.channel
    voice_client = ctx.guild.voice_client

    if voice_client:
        if voice_client.channel.id != channel.id:
            await voice_client.move_to(channel)
    else:
        await channel.connect()

    try:
        guild_id = ctx.guild.id
        queue = queues.get(guild_id, [])

        if url is None:
            await ctx.send("Non hai scritto niente.")
            return

        if "youtube.com" in url or "youtu.be" in url:
            video_url = url
        else:
            video_search = ytdl.extract_info(f"ytsearch:{url}", download=False)
            if video_search and 'entries' in video_search and video_search['entries']:
                video_info = video_search['entries'][0]
                video_url = video_info['webpage_url']
            else:
                await ctx.send("Non ho trovato il video su YouTube, cerca qualcos'altro")
                return

        if not ctx.guild.voice_client.is_playing():
            async with ctx.typing():
                filename, title = await YTDLSource.from_url(video_url, loop=bot.loop)
                now_playing[guild_id] = video_url
                ctx.guild.voice_client.play(
                    discord.FFmpegPCMAudio(executable="ffmpeg", source=filename),
                    after=lambda e, filename=filename: after_play(ctx, guild_id, filename)
                )
                await ctx.send(f'**:notes: Adesso sto riproducendo:** *{title}*')
        else:
            queue.append(video_url)
            await ctx.send("Canzone aggiunta nella queue! Usa il comando !queue per vedere la tua richiesta")

        queues[guild_id] = queue

    except Exception as e:
        print(e)
        await ctx.send("Il bot non va")

async def play_next(ctx, guild_id):
    queue = queues.get(guild_id, [])
    if not queue:
        now_playing[guild_id] = None
        return

    voice_channel = ctx.guild.voice_client
    track = queue.pop(0)
    now_playing[guild_id] = track
    async with ctx.typing():
        filename, title = await YTDLSource.from_url(track, loop=bot.loop)
        voice_channel.play(
            discord.FFmpegPCMAudio(executable="ffmpeg", source=filename),
            after=lambda e, filename=filename: after_play(ctx, guild_id, filename)
        )
        await ctx.send(f'**:notes: Adesso sto riproducendo:** {title}')

    queues[guild_id] = queue

@bot.command(name='skip', help='')
async def skip(ctx):
    voice_client = ctx.guild.voice_client

    if not voice_client or not voice_client.is_playing():
        await ctx.send('Nessuna canzone è in riproduzione.')
        return

    guild_id = ctx.guild.id
    queue = queues.get(guild_id, [])

    voice_client.stop()  

    if queue:  
        await ctx.send('**Traccia skippata! Passo alla prossima...**')
        await play_next(ctx, guild_id)
    else:
        await ctx.send('**Traccia skippata!** Non ci sono più canzoni in coda.')

@bot.command(name='queue', help='')
async def show_queue(ctx):
    guild_id = ctx.guild.id
    queue = queues.get(guild_id, [])
    current = now_playing.get(guild_id)
    
    message_parts = []
    if current:
        message_parts.append(f"**In riproduzione:**\n {current}")
    if queue:
        queue_info = "\n".join([f"{index + 1}. {song}" for index, song in enumerate(queue)])
        message_parts.append(f"**Queue:**\n{queue_info}")

    if message_parts:
        await ctx.send("\n".join(message_parts))
    else:
        await ctx.send('Non ci sono tracce nella queue di questo server!')

@bot.command(name='stop', help='')
async def stop(ctx):
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        guild_id = ctx.guild.id
        queue = queues.get(guild_id, [])
        queue.clear()
        queues[guild_id] = queue
        now_playing[guild_id] = None
        await ctx.send('Ho fermato la musica e pulito la queue, uscirò dalla VC.')
        await voice_client.disconnect()
    else:
        await ctx.send('Nessuna canzone è in riproduzione')



@bot.event
async def on_voice_state_update(member, before, after):
    voice_client = member.guild.voice_client
    if not voice_client:
        return

    if len(voice_client.channel.members) == 1:
        guild_id = member.guild.id

        if voice_client.is_playing():
            voice_client.stop()

        queues[guild_id] = []
        now_playing[guild_id] = None

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
