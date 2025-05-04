import discord
from discord.ext import commands
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_API_URL = "https://translation.googleapis.com/language/translate/v2"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

lang_channels = {}

DAILY_CHAR_LIMIT = 100000
usage_today = 0
usage_date = time.strftime("%Y-%m-%d")

def translate(text, source_lang, target_lang):
    global usage_today, usage_date
    today = time.strftime("%Y-%m-%d")
    if today != usage_date:
        usage_today = 0
        usage_date = today

    request_chars = len(text)
    if usage_today + request_chars > DAILY_CHAR_LIMIT:
        return "[번역 중단] 오늘의 번역 한도를 초과했습니다."

    params = {
        'q': text,
        'source': source_lang,
        'target': target_lang,
        'format': 'text',
        'key': GOOGLE_API_KEY
    }

    response = requests.post(GOOGLE_API_URL, data=params)
    if response.status_code == 200:
        usage_today += request_chars
        return response.json()['data']['translations'][0]['translatedText']
    else:
        print(f"❌ 번역 실패: {response.status_code} - {response.text}")
        return "[번역 실패]"

@bot.event
async def on_ready():
    synced = await bot.tree.sync()
    print(f"✅ 로그인됨: {bot.user} | 슬래시 명령어 {len(synced)}개 동기화 완료")

@bot.tree.command(name="지정", description="현재 채널을 특정 언어로 등록합니다.")
async def 지정(interaction: discord.Interaction, 언어코드: str):
    lang_channels[interaction.channel.id] = 언어코드
    await interaction.response.send_message(f"✅ 이 채널이 `{언어코드}` 언어로 등록되었습니다.", ephemeral=True)

@bot.tree.command(name="해제", description="현재 채널의 언어 번역 설정을 해제합니다.")
async def 해제(interaction: discord.Interaction):
    if interaction.channel.id in lang_channels:
        del lang_channels[interaction.channel.id]
        await interaction.response.send_message("🗑️ 이 채널의 번역 설정이 해제되었습니다.", ephemeral=True)
    else:
        await interaction.response.send_message("⚠️ 이 채널은 번역 설정이 없습니다.", ephemeral=True)

@bot.tree.command(name="설정확인", description="현재 설정된 번역 채널 목록을 확인합니다.")
async def 설정확인(interaction: discord.Interaction):
    if not lang_channels:
        await interaction.response.send_message("⚠️ 등록된 채널이 없습니다.", ephemeral=True)
        return

    msg = "📌 등록된 언어 채널 목록:\n"
    for cid, lang in lang_channels.items():
        ch = bot.get_channel(cid)
        if ch:
            msg += f"- {ch.name} ({lang})\n"
        else:
            msg += f"- Unknown Channel ID {cid} ({lang})\n"
    await interaction.response.send_message(msg, ephemeral=True)

@bot.event
async def on_message(message):
    await bot.process_commands(message)
    
    if message.author.bot or message.channel.id not in lang_channels:
        return

    src_lang = lang_channels[message.channel.id]
    for cid, tgt_lang in lang_channels.items():
        if cid == message.channel.id:
            continue

        translated = translate(message.content, src_lang, tgt_lang)
        if translated:
            target_channel = bot.get_channel(cid)
            await target_channel.send(f"[{message.author.display_name}] : {translated}")

bot.run(TOKEN)
