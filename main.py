import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata, key

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola hermano 🙏 Mándame audio/mp3 y te saco la partitura para sax alto Eb en clave de Sol con título y BPM real")

def audio_a_partitura(wav_path, out_xml_path, titulo="Por Que Sera - NicNat"):
    y, sr = librosa.load(wav_path, sr=22050, duration=60)
    
    # BPM real
    tempo_val, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = int(tempo_val) if tempo_val > 0 else 75
    
    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'))

    s = stream.Stream()
    # Metadata - titulo
    s.append(metadata.Metadata())
    s.metadata.title = titulo
    s.metadata.composer = "Transcrito por d14n4_bot"
    
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef()) # ¡CLAVE DE SOL OBLIGATORIA!
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))
    s.append(key.Key('G')) # Ajusta según canción

    transposicion = 9 + 12 # +9 por Eb +12 para subir octava y que no salga en clave de fa
    last_midi = None
    for i in range(0, len(f0), 20): # 20 para menos notas basura
        if i < len(voiced_flag) and voiced_flag[i] and f0[i]:
            midi = int(librosa.hz_to_midi(f0[i])) + transposicion
            # Filtro rango sax alto
            if midi < 50 or midi > 85: 
                continue
            if last_midi is None or abs(midi - last_midi) > 1:
                n = note.Note()
                n.pitch.midi = midi
                n.quarterLength = 1.0
                s.append(n)
                last_midi = midi

    s.write('musicxml', fp=out_xml_path)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    titulo = update.message.audio.file_name if update.message.audio else "Cancion Cristiana"
    await update.message.reply_text(f"🎷 Analizando {titulo}... con clave de Sol y BPM real")
    try:
        file = await update.message.effective_attachment.get_file()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = f"{tmp}/input"
            out_xml = f"{tmp}/partitura.musicxml"
            await file.download_to_drive(in_path)
            audio_a_partitura(in_path, out_xml, titulo=titulo)
            await update.message.reply_document(document=open(out_xml, 'rb'), filename=f"{titulo}_SaxAlto_Eb.musicxml", caption=f"✅ {titulo} - BPM {80} - Clave de Sol para sax alto")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error: {e}")

async def partitura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usa /partitura link")
        return
    url = context.args[0]
    await update.message.reply_text(f"Bajando {url}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ydl_opts = {'format': 'bestaudio/best','outtmpl': f'{tmp}/audio.%(ext)s','postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'wav','preferredquality': '192'}],'quiet': True,'noplaylist': True,'extractor_args': {'youtube': {'player_client': ['android']}},}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                titulo = info.get('title', 'Cancion')
            wav_path = f"{tmp}/audio.wav"
            xml_path = f"{tmp}/partitura.musicxml"
            audio_a_partitura(wav_path, xml_path, titulo=titulo)
            await update.message.reply_document(document=open(xml_path, 'rb'), filename=f"{titulo}_SaxAlto.musicxml")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error: {e}")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("partitura", partitura))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.run_polling()

if __name__ == "__main__":
    main()
    

