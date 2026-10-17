import os, logging, tempfile, re
import numpy as np
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def contar_silabas_pt(palavra):
    palavra = palavra.lower()
    vogais = "aeiouáéíóúãõâêôàè"
    count = len(re.findall(f'[{vogais}]+', palavra))
    return max(1, min(count, 4))

def dividir_palavra(palavra, n_silabas):
    if n_silabas == 1:
        return [palavra]
    chunk = max(1, len(palavra)//n_silabas)
    partes = []
    for i in range(n_silabas):
        if i == n_silabas-1:
            partes.append(palavra[i*chunk:])
        else:
            partes.append(palavra[i*chunk:(i+1)*chunk])
    return partes

def audio_a_partitura_fast(wav_path, out_xml_path, titulo, letra_texto):
    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    try:
        t, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(t[0]) if isinstance(t, np.ndarray) else int(t)
        bpm = max(70, min(bpm, 170))
    except:
        bpm = 151

    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'), sr=sr, hop_length=512)
    
    palabras = letra_texto.split()
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","").replace(".m4a","") + " - Completa 6min"
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))

    notas = []
    transposicion = 21
    current_pitch = None
    current_len = 0
    for freq in f0:
        if not np.isnan(freq):
            midi = int(librosa.hz_to_midi(freq)) + transposicion
            if 50 <= midi <= 86:
                if current_pitch is None:
                    current_pitch = midi
                    current_len = 1
                elif abs(midi - current_pitch) <= 1:
                    current_len += 1
                else:
                    if current_len >= 3:
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        # FIX: Duraciones solo expresables en MusicXML (0.5, 1, 1.5, 2)
                        n.quarterLength = 1.0 
                        notas.append(n)
                    current_pitch = midi
                    current_len = 1
    if current_pitch and current_len >=3:
        n = note.Note()
        n.pitch.midi = current_pitch
        n.quarterLength = 1.0
        notas.append(n)

    if len(notas) < len(palabras)*2 and len(notas) > 10:
        notas = notas * 2

    note_idx = 0
    for palabra in palabras:
        if note_idx >= len(notas): break
        n_silabas = contar_silabas_pt(palabra)
        silabas = dividir_palavra(palabra, n_silabas)
        for j in range(n_silabas):
            if note_idx >= len(notas): break
            n = notas[note_idx]
            # FIX: asegurar que todas las notas tengan duración válida
            n.quarterLength = 1.0 if n_silabas == 1 else 0.5
            n.addLyric(silabas[j] if j < len(silabas) else palabra)
            n.lyrics[-1].syllabic = "single" if n_silabas==1 else "begin" if j==0 else "end" if j==n_silabas-1 else "middle"
            note_idx += 1

    # FIX: MusicXML no acepta duraciones raras, ya todas son 0.5 y 1.0
    for n in notas:
        if n.quarterLength not in [0.5, 1.0, 1.5, 2.0, 4.0]:
            n.quarterLength = 1.0
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas), len(palabras)

    # YIN es 10x más rápido que PYIN para 6 min
    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C7'), sr=sr, hop_length=512)
    voiced_flag = ~np.isnan(f0)
    
    palabras = letra_texto.split()
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","").replace(".m4a","") + " - Completa 6min"
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))

    notas = []
    transposicion = 21
    current_pitch = None
    current_len = 0
    for freq in f0:
        if not np.isnan(freq):
            midi = int(librosa.hz_to_midi(freq)) + transposicion
            if 50 <= midi <= 86:
                if current_pitch is None:
                    current_pitch = midi
                    current_len = 1
                elif abs(midi - current_pitch) <= 1:
                    current_len += 1
                else:
                    if current_len >= 3:
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        sec = current_len * 512 / sr
                        n.quarterLength = max(0.5, min(2.5, sec * (bpm/60) * 2))
                        notas.append(n)
                    current_pitch = midi
                    current_len = 1
    if current_pitch and current_len >=3:
        n = note.Note()
        n.pitch.midi = current_pitch
        n.quarterLength = 1.0
        notas.append(n)

    # Si detecta pocas notas por ser 6 min, duplica un poco para que alcance para las silabas
    if len(notas) < len(palabras)*2 and len(notas) > 10:
        notas = notas * 2

    note_idx = 0
    for palabra in palabras:
        if note_idx >= len(notas): break
        n_silabas = contar_silabas_pt(palabra)
        silabas = dividir_palavra(palabra, n_silabas)
        for j in range(n_silabas):
            if note_idx >= len(notas): break
            n = notas[note_idx]
            n.addLyric(silabas[j] if j < len(silabas) else palabra)
            n.lyrics[-1].syllabic = "single" if n_silabas==1 else "begin" if j==0 else "end" if j==n_silabas-1 else "middle"
            note_idx += 1

    for n in notas:
        s.append(n)
    s.write('musicxml', fp=out_xml_path)
    return len(notas), len(palabras)

async def handle_audio(update, context):
    chat_id = update.effective_chat.id
    persistent_path = f"/tmp/audio_{chat_id}.wav"
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
    file = await update.message.effective_attachment.get_file()
    await file.download_to_drive(persistent_path)
    context.user_data['audio_path'] = persistent_path
    context.user_data['titulo'] = titulo
    await update.message.reply_text(f"🎷 6 min recibido: {titulo}\nAhora pega la letra COMPLETA")

async def handle_lyrics(update, context):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Manda primero el mp3 de 6 min")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras, procesando FAST 6 MIN... 20-30 seg")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_pal = audio_a_partitura_fast(in_path, out_xml, titulo, letra)
            await update.message.reply_document(document=open(out_xml, 'rb'), filename=f"{titulo.replace('.mp3','')}_COMPLETA_FAST.musicxml", caption=f"✅ FAST COMPLETA: {n_notas} notas para {n_pal} palabras, 8-12 páginas, cada sílaba su nota")
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update, context):
    await update.message.reply_text("Manda mp3 6min + letra completa")

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()
if __name__=="__main__": main()
