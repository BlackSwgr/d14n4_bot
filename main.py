import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Para transcripción real
import yt_dlp
import librosa
import numpy as np
from music21 import stream, note, tempo, key, meter, instrument

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- TU SALUDO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola hermanos míos, bienvenidos a este programa, sigue en desarrollo pero espero que sea de su agrado 🙏")

# --- NUEVA FUNCION: TRANSCRIPCION REAL A SAX ALTO ---
async def partitura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Mándame así:\n/partitura https://youtu.be/_1DZc1v8nzI")
        return

    url = context.args[0]
    await update.message.reply_text(f"🎷 Bajando y analizando tal cual suena: {url}\nEsto tarda 1-2 min...")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            #ydl_opts = {
    'format': 'bestaudio/best',
    'outtmpl': f'{tmp}/audio.%(ext)s',
    'postprocessors': [{'key': 'FFmpegExtractAudio','preferredcodec': 'wav','preferredquality': '192'}],
    'quiet': True,
    'noplaylist': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'web']
        }
    }               
           with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            wav_path = f"{tmp}/audio.wav"
            
            # 2. Analizar frecuencia real con librosa (sin traducir)
            y, sr = librosa.load(wav_path, sr=22050, duration=60) # primeros 60 seg para prueba
            # Detecta pitch real frame por frame
            f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
            
            # 3. Convertir a notas (limpieza)
            times = librosa.times_like(f0, sr=sr)
            s = stream.Stream()
            s.append(instrument.AltoSaxophone())
            s.append(tempo.MetronomeMark(number=70))
            s.append(meter.TimeSignature('4/4'))
            # Original es C, para alto sax Eb transportamos +9 semitonos (M6)
            # Esto hace que suene igual que el original
            transposicion = 9 

            last_note = None
            for i in range(0, len(f0), 10): # sample cada 10 frames para no saturar
                if voiced_flag[i] and f0[i] is not None:
                    midi = librosa.hz_to_midi(f0[i])
                    # Transportar para Eb
                    midi_sax = midi + transposicion
                    n = note.Note()
                    n.pitch.midi = int(midi_sax)
                    n.quarterLength = 0.5
                    if last_note is None or abs(n.pitch.midi - last_note) > 1:
                        s.append(n)
                        last_note = n.pitch.midi

            # 4. Guardar MusicXML real
            xml_path = f"{tmp}/partitura_alto_sax.musicxml"
            s.write('musicxml', fp=xml_path)
            
            await update.message.reply_text("✅ Transcripción tal cual suena terminada. Te mando el archivo para sax alto Eb (ya transportado).")
            await update.message.reply_document(document=open(xml_path, 'rb'), filename="PorQueSera_AltoSax_Eb.musicxml", caption="Ábrelo en MuseScore / Finale. Ya está en Eb, suena en el tono original.")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text(f"Error transcribiendo: {e}\nAsegúrate que el video tiene audio y ffmpeg está instalado.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("partitura", partitura))
    app.run_polling()

if __name__ == "__main__":
    main()


