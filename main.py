import os, logging, tempfile, numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def audio_a_partitura(wav_path, out_xml_path, titulo, letra_texto):
    y, sr = librosa.load(wav_path, sr=22050, duration=90)
    try:
        tv, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(tv[0]) if isinstance(tv, np.ndarray) else int(tv)
    except:
        bpm = 151

    palabras = letra_texto.split()
    
    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'))
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","")
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))

    transposicion = 21
    notas = []
    last_midi = None
    for i in range(0, len(f0), 25):
        if i < len(voiced_flag) and voiced_flag[i] and f0[i]:
            midi = int(librosa.hz_to_midi(f0[i])) + transposicion
            if 50 <= midi <= 85 and (last_midi is None or abs(midi-last_midi)>2):
                n = note.Note()
                n.pitch.midi = midi
                n.quarterLength = 1.0
                notas.append(n)
                last_midi = midi

    for idx, n in enumerate(notas):
        if idx < len(palabras):
            n.addLyric(palabras[idx])
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas)

async def handle_audio(update, context):
    file = await update.message.effective_attachment.get_file()
    with tempfile.TemporaryDirectory() as tmp:
        in_path = f"{tmp}/input"
        await file.download_to_drive(in_path)
        context.user_data['audio_path'] = in_path
        context.user_data['titulo'] = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
        await update.message.reply_text(f"🎷 Audio recibido: {context.user_data['titulo']}\n\nAhora PÉGAME la letra completa tal cual (en portugués, sin traducir) en un solo mensaje y te genero la partitura con cada palabra debajo de su nota.")

async def handle_lyrics(update, context):
    if 'audio_path' not in context.user_data:
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    await update.message.reply_text(f"Recibí letra de {len(letra.split())} palabras, generando partitura...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            import shutil
            in_path = f"{tmp}/input"
            shutil.copy(context.user_data['audio_path'], in_path)
            out_xml = f"{tmp}/out.musicxml"
            num = audio_a_partitura(in_path, out_xml, titulo, letra)
            await update.message.reply_document(document=open(out_xml, 'rb'), filename=f"{titulo.replace('.mp3','')}_CON_LETRA.musicxml", caption=f"✅ {num} notas con letra original debajo")
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update, context):
    await update.message.reply_text("1. Manda el mp3\n2. Luego pega la letra completa")

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()
if __name__=="__main__": main()


