import os, logging, tempfile, numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def audio_a_partitura(wav_path, out_xml_path, titulo="Cancion"):
    y, sr = librosa.load(wav_path, sr=22050, duration=60)
    try:
        tv, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(tv[0]) if isinstance(tv, np.ndarray) else int(tv)
    except:
        bpm = 75
    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'))
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))
    transposicion = 21
    last_midi = None
    for i in range(0, len(f0), 20):
        if i < len(voiced_flag) and voiced_flag[i] and f0[i]:
            midi = int(librosa.hz_to_midi(f0[i])) + transposicion
            if 50 <= midi <= 85 and (last_midi is None or abs(midi-last_midi)>1):
                n = note.Note()
                n.pitch.midi = midi
                n.quarterLength = 1.0
                s.append(n)
                last_midi = midi
    s.write('musicxml', fp=out_xml_path)

async def start(update, context):
    await update.message.reply_text("Manda audio/mp3 y te doy partitura en Clave de Sol para sax alto Eb")

async def handle_audio(update, context):
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Audio"
    await update.message.reply_text(f"🎷 Analizando {titulo}... clave de Sol")
    try:
        file = await update.message.effective_attachment.get_file()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = f"{tmp}/input"; out_xml = f"{tmp}/out.musicxml"
            await file.download_to_drive(in_path)
            audio_a_partitura(in_path, out_xml, titulo=titulo)
            await update.message.reply_document(document=open(out_xml, 'rb'), filename=f"{titulo}_SaxAlto_Eb.musicxml")
    except Exception as e:
        logging.error(e); await update.message.reply_text(f"Error: {e}")

async def partitura(update, context):
    if not context.args: await update.message.reply_text("Usa /partitura link"); return
    url=context.args[0]; await update.message.reply_text(f"Bajando {url}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ydl_opts={'format':'bestaudio/best','outtmpl':f'{tmp}/audio.%(ext)s','postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'wav','preferredquality':'192'}],'quiet':True,'noplaylist':True,'extractor_args':{'youtube':{'player_client':['android']}},}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info=ydl.extract_info(url, download=True); titulo=info.get('title','Cancion')
            audio_a_partitura(f"{tmp}/audio.wav", f"{tmp}/out.musicxml", titulo=titulo)
            await update.message.reply_document(document=open(f"{tmp}/out.musicxml",'rb'), filename=f"{titulo}.musicxml")
    except Exception as e:
        logging.error(e); await update.message.reply_text(f"Error: {e}")

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("partitura", partitura))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.run_polling()
if __name__=="__main__": main()



