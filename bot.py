import discord
from discord.ext import commands
import requests
import os
import time
import asyncio
from dotenv import load_dotenv
from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from datetime import datetime
import threading
from asyncio import Queue

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_API_URL = "https://translation.googleapis.com/language/translate/v2"
DEPLOY_HOOK = os.getenv("RENDER_DEPLOY_HOOK_URL")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

lang_channels = {}
message_queue = Queue()

DAILY_CHAR_LIMIT = 100000
usage_today = 0
usage_date = time.strftime("%Y-%m-%d")

def load_lang_channels_from_env():
    mapping = {
        "TRANSLATION_CHANNEL_KO": "ko",
        "TRANSLATION_CHANNEL_EN": "en",
        "TRANSLATION_CHANNEL_AR": "ar",
        "TRANSLATION_CHANNEL_RU": "ru",
    }
    for env_key, lang_code in mapping.items():
        channel_id = os.getenv(env_key)
        if channel_id and channel_id.isdigit():
            lang_channels[int(channel_id)] = lang_code

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

    try:
        response = requests.post(GOOGLE_API_URL, data=params)
        if response.status_code == 200:
            usage_today += request_chars
            return response.json()['data']['translations'][0]['translatedText']
        else:
            print(f"❌ 번역 실패: {response.status_code} - {response.text}")
            return "[번역 실패]"
    except Exception as e:
        print(f"❌ 번역 요청 예외: {e}")
        return "[번역 실패]"

async def health_ping():
    await bot.wait_until_ready()
    channel_id = os.getenv("HEALTH_CHECK_CHANNEL_ID")
    if not channel_id or not channel_id.isdigit():
        return
    channel = bot.get_channel(int(channel_id))
    if not channel:
        print("⚠️ 헬스체크 채널을 찾을 수 없음.")
        return

    while not bot.is_closed():
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            await message_queue.put((channel, f"✅ 봇 정상 작동 중\n⏱️ {now}"))
        except Exception as e:
            print(f"❌ health_ping 예외: {e}")
        await asyncio.sleep(600)  # 10분

def restart_via_hook():
    if DEPLOY_HOOK:
        try:
            requests.post(DEPLOY_HOOK)
            print("🔁 Deploy Hook 호출로 재시작 요청 완료")
        except Exception as e:
            print(f"❌ Deploy Hook 호출 실패: {e}")

def auto_restart_via_hook():
    while True:
        time.sleep(900)  # 15분
        restart_via_hook()

async def message_sender():
    await bot.wait_until_ready()
    while True:
        channel, content = await message_queue.get()
        try:
            if isinstance(content, discord.File):
                await channel.send(file=content)
            else:
                await channel.send(content)
        except discord.HTTPException as e:
            print(f"❌ 메시지 전송 실패: {e}")
        await asyncio.sleep(1)
        message_queue.task_done()

@bot.event
async def on_ready():
    load_lang_channels_from_env()
    await bot.tree.sync()
    print(f"✅ 로그인됨: {bot.user}")
    bot.loop.create_task(health_ping())
    bot.loop.create_task(message_sender())

    health_channel_id = os.getenv("HEALTH_CHECK_CHANNEL_ID")
    if health_channel_id and health_channel_id.isdigit():
        ch = bot.get_channel(int(health_channel_id))
        if ch:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await message_queue.put((ch, f"✅ 번역봇이 다시 시작되었습니다.\n시각: {now}"))

@bot.event
async def on_message(message):
    try:
        await bot.process_commands(message)

        if message.author.bot or message.channel.id not in lang_channels:
            return

        src_lang = lang_channels[message.channel.id]
        sent_to = set()

        for cid, tgt_lang in lang_channels.items():
            if cid == message.channel.id or cid in sent_to:
                continue

            target_channel = bot.get_channel(cid)
            if not target_channel:
                continue

            # 텍스트 번역
            translated = translate(message.content, src_lang, tgt_lang) if message.content else None

            # 이미지 첨부 처리
            files = []
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    files.append(await attachment.to_file())

            if translated:
                await message_queue.put((target_channel, f"[{message.author.display_name}] : {translated}"))

            if files:
                if not translated:
                    await message_queue.put((target_channel, f"[{message.author.display_name}] : 사진"))
                for file in files:
                    await message_queue.put((target_channel, file))

            sent_to.add(cid)

    except Exception as e:
        print(f"❌ on_message 예외: {e}")
        import traceback
        traceback.print_exc()

def run_http_server():
    with TCPServer(("", 8080), SimpleHTTPRequestHandler) as httpd:
        httpd.serve_forever()

# 시작
threading.Thread(target=run_http_server, daemon=True).start()
threading.Thread(target=auto_restart_via_hook, daemon=True).start()
bot.run(TOKEN)
