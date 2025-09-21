import asyncio
import logging
import os
import yt_dlp
import aiohttp
import aiofiles
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped, VideoPiped
from pytgcalls.exceptions import GroupCallNotFound, NoActiveGroupCall
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram import F
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pyrogram import Client, filters
from pyrogram.types import Message
import time
import youtube_search
import requests
from urllib.parse import urlparse

# Bot Token - Railway'de environment variable olarak ayarlayın
BOT_TOKEN = os.getenv("BOT_TOKEN", "8066679823:AAH_wO60kY1FF_DslNWgAyj7xG8DG_oYSNE")

# UserBot bilgileri
API_ID = 23909960
API_HASH = "20640a09707010d0f9766096804baaf2"
SESSION = "1BJWap1sBu15a_XS4H3rCasu9c16VJvRh3ybemCMVdJLp0drDTvI0ntpScG-tZPufGFfiNKIKXixjeZRCCjhjQMt5fi5aDiB_WoYfIlKJEIvhY-dHRkkEkXIwfF8XiBLbgytIDKiGM-PJIiR8DqdCmg5KGSssFU_-zAHQ5s33XFtomM61JEtUCSYdTGr9f13elgdhUws0z_EIsOeNHfXqpDL6vFIiOpBRvIHxN_BV0I5kOR5uDgDKIP1Ufi59JM90AviRarqtl3oI2Go42u07oXTaw5doM15LsdYum6G_eZeyO3DY0wl8mOXBZPp7alI7ANmPFHSmex_OyaCgwo0lH3dbwJgZPUI="

# Logging ayarları
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Bot ve Dispatcher
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# UserBot Client
app = Client(
    "userbot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION
)

# PyTgCalls - Sesli sohbet için
call_py = PyTgCalls(app)

# States
class MusicStates(StatesGroup):
    playing = State()
    in_voice_chat = State()

# Global değişkenler
current_chat_id = None
is_playing = False
is_in_voice_chat = False
current_song = None
download_folder = "downloads"

# Downloads klasörünü oluştur
os.makedirs(download_folder, exist_ok=True)

# YouTube indirme ayarları
ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
    'extractaudio': True,
    'audioformat': 'mp3',
    'quiet': True,
    'no_warnings': True,
}

# Ana menü keyboard
def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="🎵 Müzik Çal", callback_data="music_menu"),
        InlineKeyboardButton(text="🎥 Video Çal", callback_data="video_menu"),
        InlineKeyboardButton(text="🔊 Sesli Sohbet", callback_data="voice_menu"),
        InlineKeyboardButton(text="📊 Durum", callback_data="status")
    )
    builder.adjust(2)
    return builder.as_markup()

def get_music_keyboard():
    builder = InlineKeyboardBuilder()
    if is_playing:
        builder.add(InlineKeyboardButton(text="⏹️ Durdur", callback_data="stop_music"))
    builder.add(InlineKeyboardButton(text="🔙 Ana Menü", callback_data="main_menu"))
    builder.adjust(1)
    return builder.as_markup()

def get_voice_keyboard():
    builder = InlineKeyboardBuilder()
    if is_in_voice_chat:
        builder.add(InlineKeyboardButton(text="🔇 Sesli Sohbetten Çık", callback_data="leave_voice"))
    else:
        builder.add(InlineKeyboardButton(text="🔊 Sesli Sohbete Gir", callback_data="join_voice"))
    
    builder.add(InlineKeyboardButton(text="🔙 Ana Menü", callback_data="main_menu"))
    builder.adjust(1)
    return builder.as_markup()

# YouTube'dan şarkı ara
async def search_youtube(query):
    try:
        results = youtube_search.YoutubeSearch(query, max_results=1).to_dict()
        if results:
            video_id = results[0]['id']
            return f"https://www.youtube.com/watch?v={video_id}"
        return None
    except Exception as e:
        logger.error(f"YouTube arama hatası: {e}")
        return None

# Müzik indir
async def download_music(url):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            # Dosya uzantısını mp3'e çevir
            if not filename.endswith('.mp3'):
                base = os.path.splitext(filename)[0]
                filename = f"{base}.mp3"
            return filename, info.get('title', 'Bilinmeyen')
    except Exception as e:
        logger.error(f"İndirme hatası: {e}")
        return None, None

# Komutlar
@router.message(CommandStart())
async def start_command(message: types.Message):
    welcome_text = """
🤖 **Telegram Müzik Bot'a Hoş Geldiniz!** 🎵

Bu bot ile şunları yapabilirsiniz:
🎵 Müzik çalabilirsiniz (Gerçek sesli sohbette!)
🎥 Video izleyebilirsiniz  
🔊 Sesli sohbete katılabilirsiniz
📊 Bot durumunu kontrol edebilirsiniz

**Komutlar:**
• `/play <şarkı adı/link>` - Müzik çalar
• `/vplay <video link>` - Video açar
• `/gir` - Sesli sohbete girer
• `/cik` - Sesli sohbetten çıkar
• `/son` - Müziği durdurur
• `/ping` - Bot pingini kontrol eder

⚠️ **Not:** Müzik çalmak için önce sesli sohbete katılmalısınız!

Aşağıdaki menüden seçim yapabilirsiniz! 👇
    """
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

@router.message(Command("ping"))
async def ping_command(message: types.Message):
    start_time = time.time()
    sent_message = await message.answer("🏓 Pong!")
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)
    
    await sent_message.edit_text(
        f"🏓 **Pong!**\n⚡ Ping: `{ping_time}ms`\n🤖 Bot Durumu: {'🔊 Sesli sohbette' if is_in_voice_chat else '💤 Beklemede'}",
        parse_mode="Markdown"
    )

@router.message(Command("play"))
async def play_command(message: types.Message):
    global current_chat_id, is_playing, current_song
    
    if not message.text or len(message.text.split()) < 2:
        await message.answer("❌ Lütfen şarkı adı veya link girin!\n🎵 Örnek: `/play imagine dragons bones`", parse_mode="Markdown")
        return
    
    if not is_in_voice_chat:
        await message.answer("❌ **Önce sesli sohbete katılmalısınız!**\n🔊 `/gir` komutunu kullanın.", parse_mode="Markdown")
        return
    
    query = " ".join(message.text.split()[1:])
    current_chat_id = message.chat.id
    
    loading_msg = await message.answer("🔍 **Aranıyor ve indiriliyor...** 🎵\n⏳ Bu biraz zaman alabilir...", parse_mode="Markdown")
    
    try:
        # URL kontrolü
        if query.startswith(('http://', 'https://', 'www.')):
            url = query
        else:
            # YouTube'da ara
            url = await search_youtube(query)
            if not url:
                await loading_msg.edit_text("❌ **Şarkı bulunamadı!** Farklı anahtar kelimeler deneyin.", parse_mode="Markdown")
                return
        
        # Müziği indir
        filepath, title = await download_music(url)
        if not filepath or not os.path.exists(filepath):
            await loading_msg.edit_text("❌ **İndirme hatası!** Lütfen farklı bir şarkı deneyin.", parse_mode="Markdown")
            return
        
        # Sesli sohbette çal
        try:
            await call_py.join_group_call(
                current_chat_id,
                AudioPiped(filepath)
            )
            is_playing = True
            current_song = title
            
            await loading_msg.edit_text(
                f"🎵 **Şu an çalıyor:**\n📀 `{title}`\n\n✅ **Başarıyla başlatıldı!**",
                reply_markup=get_music_keyboard(),
                parse_mode="Markdown"
            )
            
        except Exception as e:
            logger.error(f"Sesli sohbet çalma hatası: {e}")
            await loading_msg.edit_text("❌ **Sesli sohbette çalma hatası!** Lütfen tekrar deneyin.", parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Müzik çalma hatası: {e}")
        await loading_msg.edit_text("❌ **Hata!** Müzik çalınamadı. Lütfen tekrar deneyin.", parse_mode="Markdown")

@router.message(Command("vplay"))
async def vplay_command(message: types.Message):
    global current_chat_id
    
    if not message.text or len(message.text.split()) < 2:
        await message.answer("❌ Lütfen video link'i girin!\n🎥 Örnek: `/vplay https://youtube.com/watch?v=...`", parse_mode="Markdown")
        return
    
    if not is_in_voice_chat:
        await message.answer("❌ **Önce sesli sohbete katılmalısınız!**\n🔊 `/gir` komutunu kullanın.", parse_mode="Markdown")
        return
    
    video_link = message.text.split()[1]
    current_chat_id = message.chat.id
    
    loading_msg = await message.answer("🔍 **Video indiriliyor...** 🎥\n⏳ Bu biraz zaman alabilir...", parse_mode="Markdown")
    
    try:
        # Video indir
        video_ydl_opts = {
            'format': 'best[height<=720]',
            'outtmpl': f'{download_folder}/%(title)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(video_ydl_opts) as ydl:
            info = ydl.extract_info(video_link, download=True)
            filepath = ydl.prepare_filename(info)
            title = info.get('title', 'Bilinmeyen Video')
        
        # Sesli sohbette video oynat
        await call_py.join_group_call(
            current_chat_id,
            VideoPiped(filepath)
        )
        
        await loading_msg.edit_text(
            f"🎥 **Video oynatılıyor:**\n📺 `{title}`\n\n✅ **Başarıyla başlatıldı!**",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Video oynatma hatası: {e}")
        await loading_msg.edit_text("❌ **Hata!** Video oynatılamadı.", parse_mode="Markdown")

@router.message(Command("gir"))
async def join_voice_command(message: types.Message):
    global current_chat_id, is_in_voice_chat
    
    current_chat_id = message.chat.id
    
    if is_in_voice_chat:
        await message.answer("✅ **Zaten sesli sohbetteyim!**", parse_mode="Markdown")
        return
    
    loading_msg = await message.answer("🔊 **Sesli sohbete katılıyorum...** ⏳", parse_mode="Markdown")
    
    try:
        # Boş bir audio stream ile sesli sohbete katıl
        await call_py.join_group_call(
            current_chat_id,
            AudioPiped("http://duramecho.com/Misc/SilentCd/SilentCd20sec.mp3")
        )
        
        is_in_voice_chat = True
        
        await loading_msg.edit_text(
            "🔊 **Sesli sohbete katıldım!** ✅\n\n🎵 Artık müzik çalabilirsiniz!\n🎥 Video da oynatabilirsiniz!",
            reply_markup=get_voice_keyboard(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Sesli sohbet katılma hatası: {e}")
        await loading_msg.edit_text("❌ **Hata!** Sesli sohbete katılamadım.\n\n🔍 **Sebep:** Sesli sohbet açık olmayabilir.", parse_mode="Markdown")

@router.message(Command("cik"))
async def leave_voice_command(message: types.Message):
    global current_chat_id, is_playing, is_in_voice_chat, current_song
    
    if not is_in_voice_chat:
        await message.answer("❌ **Zaten sesli sohbette değilim!**", parse_mode="Markdown")
        return
    
    try:
        await call_py.leave_group_call(current_chat_id)
        
        is_playing = False
        is_in_voice_chat = False
        current_song = None
        
        await message.answer(
            "🔇 **Sesli sohbetten çıktım!** ✅\n\n👋 Görüşürüz!",
            reply_markup=get_voice_keyboard(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Sesli sohbet çıkma hatası: {e}")
        await message.answer("❌ **Hata!** Sesli sohbetten çıkamadım.", parse_mode="Markdown")

@router.message(Command("son"))
async def stop_command(message: types.Message):
    global is_playing, current_song
    
    if not is_playing:
        await message.answer("❌ **Şu anda çalan müzik yok!**", parse_mode="Markdown")
        return
    
    try:
        await call_py.leave_group_call(current_chat_id)
        is_playing = False
        current_song = None
        
        await message.answer(
            "⏹️ **Müzik durduruldu!** ✅\n\n😊 Teşekkürler!",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Müzik durdurma hatası: {e}")
        await message.answer("❌ **Hata!** Müzik durdurulamadı.", parse_mode="Markdown")

# Callback handlers
@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🏠 **Ana Menü**\n\nLütfen bir seçenek seçin:",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "music_menu")
async def music_menu_callback(callback: CallbackQuery):
    music_text = "🎵 **Müzik Menüsü**\n\n"
    
    if current_song and is_playing:
        music_text += f"📀 **Şu an çalıyor:** `{current_song}`\n\n"
    
    music_text += "Müzik çalmak için `/play <şarkı adı>` komutunu kullanın!"
    
    if not is_in_voice_chat:
        music_text += "\n\n⚠️ **Önce sesli sohbete katılmalısınız!**"
    
    await callback.message.edit_text(
        music_text,
        reply_markup=get_music_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "voice_menu")
async def voice_menu_callback(callback: CallbackQuery):
    voice_text = "🔊 **Sesli Sohbet Menüsü**\n\n"
    voice_text += f"Durum: {'🔊 Bağlı' if is_in_voice_chat else '❌ Bağlı değil'}\n\n"
    voice_text += "Sesli sohbet işlemlerini buradan kontrol edebilirsiniz:"
    
    await callback.message.edit_text(
        voice_text,
        reply_markup=get_voice_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "status")
async def status_callback(callback: CallbackQuery):
    status_text = f"""
📊 **Bot Durumu**

🤖 **Bot Durumu:** ✅ Aktif
🔊 **Sesli Sohbet:** {'✅ Bağlı' if is_in_voice_chat else '❌ Bağlı değil'}
🎵 **Müzik Durumu:** {'🎵 Çalıyor' if is_playing else '⏹️ Durdu'}
📱 **Chat ID:** {current_chat_id if current_chat_id else 'Yok'}
📀 **Şu anki şarkı:** {current_song if current_song else 'Yok'}

⚡ **Özellikler:**
✅ Gerçek müzik çalma
✅ Video oynatma (sesli sohbette)
✅ Sesli sohbet katılım/çıkış
✅ YouTube müzik/video desteği
✅ Ping kontrolü

🔧 **Sistem:**
📁 Downloads: {len(os.listdir(download_folder))} dosya
    """
    
    await callback.message.edit_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Yenile", callback_data="status")],
            [InlineKeyboardButton(text="🔙 Ana Menü", callback_data="main_menu")]
        ]),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "stop_music")
async def stop_music_callback(callback: CallbackQuery):
    global is_playing, current_song
    
    try:
        await call_py.leave_group_call(current_chat_id)
        is_playing = False
        current_song = None
        
        await callback.message.edit_text(
            "⏹️ **Müzik durduruldu!** ✅\n\n😊 Başka bir şarkı çalmak ister misiniz?",
            reply_markup=get_music_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("🎵 Müzik durduruldu!")
        
    except Exception as e:
        logger.error(f"Müzik durdurma hatası: {e}")
        await callback.answer("❌ Hata oluştu!", show_alert=True)

@router.callback_query(F.data == "join_voice")
async def join_voice_callback(callback: CallbackQuery):
    global current_chat_id, is_in_voice_chat
    
    current_chat_id = callback.message.chat.id
    
    if is_in_voice_chat:
        await callback.answer("✅ Zaten sesli sohbetteyim!")
        return
    
    try:
        await call_py.join_group_call(
            current_chat_id,
            AudioPiped("http://duramecho.com/Misc/SilentCd/SilentCd20sec.mp3")
        )
        
        is_in_voice_chat = True
        
        await callback.message.edit_text(
            "🔊 **Sesli sohbete katıldım!** ✅\n\n🎵 Artık müzik çalabilirsiniz!",
            reply_markup=get_voice_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("🔊 Sesli sohbete katıldım!")
        
    except Exception as e:
        logger.error(f"Sesli sohbet katılma hatası: {e}")
        await callback.answer("❌ Sesli sohbete katılamadım!", show_alert=True)

@router.callback_query(F.data == "leave_voice")
async def leave_voice_callback(callback: CallbackQuery):
    global current_chat_id, is_playing, is_in_voice_chat, current_song
    
    try:
        await call_py.leave_group_call(current_chat_id)
        
        is_playing = False
        is_in_voice_chat = False
        current_song = None
        
        await callback.message.edit_text(
            "🔇 **Sesli sohbetten çıktım!** ✅\n\n👋 Görüşürüz!",
            reply_markup=get_voice_keyboard(),
            parse_mode="Markdown"
        )
        await callback.answer("🔇 Sesli sohbetten çıktım!")
        
    except Exception as e:
        logger.error(f"Sesli sohbet çıkma hatası: {e}")
        await callback.answer("❌ Hata oluştu!", show_alert=True)

# PyTgCalls event handlers
@call_py.on_stream_end()
async def stream_end_handler(_, update):
    global is_playing, current_song
    logger.info("Müzik/video bitti")
    is_playing = False
    current_song = None

@call_py.on_kicked()
async def kicked_handler(_, chat_id):
    global is_in_voice_chat, is_playing, current_song
    logger.info(f"Sesli sohbetten atıldık: {chat_id}")
    is_in_voice_chat = False
    is_playing = False
    current_song = None

@call_py.on_left()
async def left_handler(_, chat_id):
    global is_in_voice_chat, is_playing, current_song
    logger.info(f"Sesli sohbetten çıktık: {chat_id}")
    is_in_voice_chat = False
    is_playing = False
    current_song = None

# Ana fonksiyon
async def main():
    try:
        # Router'ı dispatcher'a ekle
        dp.include_router(router)
        
        # UserBot ve PyTgCalls'u başlat
        await app.start()
        await call_py.start()
        logger.info("🤖 UserBot ve PyTgCalls başlatıldı!")
        
        # Bot'u başlat
        logger.info("🚀 Bot başlatılıyor...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Bot başlatma hatası: {e}")
    finally:
        await call_py.stop()
        await app.stop()

if __name__ == "__main__":
    print("🚀 Telegram Müzik Bot başlatılıyor...")
    print("🔊 Gerçek sesli sohbet desteği ile!")
    asyncio.run(main())