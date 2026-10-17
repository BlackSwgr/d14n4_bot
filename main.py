import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
import librosa
from music21 import stream, note, tempo, meter, instrument

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola hermanos míos, bienvenidos 🙏\n\n"
        "1. /partitura + link YouTube\n"
        "2. O mándame un AUDIO/MP3 directo y te saco la partitura para sax alto Eb"
    )

def audio_a_partitura(wav_path, out_xml_path):
    y, sr = librosa.load(wav_path, sr=22050, duration=60)
    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
    s = stream.Stream()
    s.append(instrument.AltoSaxophone())
    s.append(tempo.MetronomeMark(number=75))
    s.append(meter.TimeSignature('4/4'))
    transposicion = 9
    last_midi = None
    for i in range(0, len(f0), 15):
        if i < len(voiced_flag) and voiced_flag[i] and f0[i]:
            midi = int(librosa.hz_to_midi(f0[i])) + transposicion
            if last_midi is None or abs(midi - last_midi) > 1:
                n = note.Note()
                n.pitch.midi = midi
                n.quarterLength = 0.75
                s.append(n)
                last_midi = midi
    s.write('musicxml', fp=out_xml_path)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎷 Recibí tu audio, analizando tal cual suena... 1 min")
    try:
        file = await update.message.effective_attachment.get_file()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = f"{tmp}/input"
            out_xml = f"{tmp}/partitura.musicxml"
            await file.download_to_drive(in_path)
            # Si es ogg/mp3 lo convierte librosa igual
            audio_a_partitura(in_path, out_xml)
            await update.message.reply_document(
                document=open(out_xml, 'rb'),
                filename="partitura_sax_alto_Eb.musicxml",
                caption="✅ Aquí está tu partitura para sax alto Eb, tal cual suena"
            )
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error: {e}")

async def partitura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa: /partitura https://youtu.be/...")
        return
    url = context.args[0]
    await update.message.reply_text(f"🎷 Bajando de YouTube: {url}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{tmp}/audio.%(ext)s',
                'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'wav','preferredquality': '192'}],
                'quiet': True,
                'noplaylist': True,
                'extractor_args': {'youtube': {'player_client': ['android']}},
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            wav_path = f"{tmp}/audio.wav"
            xml_path = f"{tmp}/partitura.musicxml"
            audio_a_partitura(wav_path, xml_path)
            await update.message.reply_document(document=open(xml_path, 'rb'), filename="partitura_sax_alto_Eb.musicxml")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error transcribiendo: {e}\nPrueba mejor mandándome el audio directo.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("partitura", partitura))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()

