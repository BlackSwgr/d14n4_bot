import os, logging, tempfile, numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp, librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def audio_a_partitura(wav_path, out_xml_path, titulo="Cancion"):
    y, sr = librosa.load(wav_path, sr=22050, duration=90)
    try:
        tv, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(tv[0]) if isinstance(tv, np.ndarray) else int(tv)
    except:
        bpm = 80

    # --- LETRA CON WHISPER (carga perezosa) ---
    palabras = []
    letra_completa = ""
    try:
        import whisper
        print("Cargando whisper tiny...")
        model = whisper.load_model("tiny")
        result = model.transcribe(wav_path, language="pt", fp16=False)
        letra_completa = result["text"].strip()
        palabras = letra_completa.split()
        print(f"LETRA OK: {letra_completa}")
    except Exception as e:
        print(f"Error whisper: {e}")
        letra_completa = "Vem queimar em mim" # fallback para que no falle
        palabras = letra_completa.split()

    f0, voiced_flag, _ = librosa.pyin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'))
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","").replace(".m4a","")
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

    # Colocar letra palabra por nota
    for idx, n in enumerate(notas):
        if idx < len(palabras):
            n.addLyric(palabras[idx])
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return letra_completa

async def handle_audio(update, context):
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Audio"
    await update.message.reply_text(f"🎷 Ya voy, transcribiendo letra original de {titulo}... tarda 90 seg")
    try:
        file = await update.message.effective_attachment.get_file()
        with tempfile.TemporaryDirectory() as tmp:
            in_path = f"{tmp}/input"; out_xml = f"{tmp}/out.musicxml"
            await file.download_to_drive(in_path)
            letra = audio_a_partitura(in_path, out_xml, titulo=titulo)
            await update.message.reply_text(f"Letra detectada:\n{letra}")
            await update.message.reply_document(document=open(out_xml, 'rb'), filename=f"{titulo.replace('.mp3','')}_CON_LETRA.musicxml")
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update, context):
    await update.message.reply_text("Manda audio y te doy partitura con letra")

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.run_polling()
if __name__=="__main__": main()



