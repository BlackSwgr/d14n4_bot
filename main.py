import os, logging, tempfile
import numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def audio_a_partitura_limpia(wav_path, out_xml_path, titulo, letra_texto):
    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    duracion_real = len(y) / sr
    print(f"DURACION REAL: {duracion_real/60:.2f} min - {duracion_real:.1f} seg")
    
    try:
        t, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(t[0]) if isinstance(t, np.ndarray) else int(t)
        bpm = max(75, min(bpm, 160))
    except:
        bpm = 88

    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C6'), sr=sr, hop_length=1024)
    
    palabras = letra_texto.split()
    print(f"Palabras: {len(palabras)} para {duracion_real:.1f}s")

    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","").replace(".m4a","") + f" - {int(duracion_real//60)}:{int(duracion_real%60):02d}"
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))

    def nota_sin_alteracion(midi):
        blancas = [0,2,4,5,7,9,11]
        octava = midi // 12
        pc = midi % 12
        pc_limpio = min(blancas, key=lambda x: abs(x-pc))
        return octava*12 + pc_limpio

    notas_detectadas = []
    current_pitch = None
    current_len = 0
    transposicion = 21
    for freq in f0:
        if not np.isnan(freq):
            midi = nota_sin_alteracion(int(librosa.hz_to_midi(freq)) + transposicion)
            if 50 <= midi <= 86:
                if current_pitch is None:
                    current_pitch = midi
                    current_len = 1
                elif abs(midi - current_pitch) <= 2:
                    current_len += 1
                else:
                    if current_len >= 6:
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        n.quarterLength = 1.0
                        notas_detectadas.append(n)
                    current_pitch = midi
                    current_len = 1
    if current_pitch and current_len >= 6:
        n = note.Note()
        n.pitch.midi = current_pitch
        n.quarterLength = 1.0
        notas_detectadas.append(n)

    total_notas = len(notas_detectadas)
    total_palabras = len(palabras)
    print(f"Notas detectadas en {duracion_real:.1f}s: {total_notas}")

    if total_notas == 0:
        notas_detectadas = [note.Note() for _ in range(total_palabras)]
        for nn in notas_detectadas:
            nn.pitch.midi = 65
            nn.quarterLength = 1.0
        total_notas = len(notas_detectadas)

    paso = total_notas / total_palabras if total_palabras > 0 else 1

    notas_finales = []
    palabra_idx = 0
    
    for i, n_detect in enumerate(notas_detectadas):
        nueva = note.Note()
        nueva.pitch.midi = n_detect.pitch.midi
        nueva.quarterLength = 1.0
        
        posicion_esperada = int(palabra_idx * paso)
        if i >= posicion_esperada and palabra_idx < total_palabras:
            nueva.addLyric(palabras[palabra_idx])
            nueva.lyrics[0].syllabic = "single"
            palabra_idx += 1
        
        notas_finales.append(nueva)

    for n in notas_finales:
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas_finales), len(palabras), duracion_real

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    persistent_path = f"/tmp/audio_{chat_id}.wav"
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
    file = await update.message.effective_attachment.get_file()
    await file.download_to_drive(persistent_path)
    context.user_data['audio_path'] = persistent_path
    context.user_data['titulo'] = titulo
    await update.message.reply_text(f"🎷 Recibido: {titulo}\nAhora pega las 244 palabras en orden como se canta")

async def handle_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Manda primero el mp3 de 4:11")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras, procesando {len(letra.split())} palabras en duración REAL... 20 seg")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_pal, dur = audio_a_partitura_limpia(in_path, out_xml, titulo, letra)
            await update.message.reply_document(
                document=open(out_xml, 'rb'), 
                filename=f"{titulo.replace('.mp3','')}_{int(dur//60)}m{int(dur%60)}s_{n_pal}palabras.musicxml", 
                caption=f"✅ {dur/60:.1f} min REALES (no 6 min): {n_notas} notas para {n_pal} palabras. 1 palabra = 1 nota, sin #/b."
            )
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Manda mp3 + letra completa cronológica")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()

if __name__ == "__main__":
    main()
    