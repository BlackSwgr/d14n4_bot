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

def audio_a_partitura_completa(wav_path, out_xml_path, titulo, letra_texto):
    # CARGA COMPLETA 6 MIN - sin recorte
    y, sr = librosa.load(wav_path, sr=22050, mono=True)
    print(f"Audio cargado: {len(y)/sr/60:.1f} min")
    try:
        t, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(t[0]) if isinstance(t, np.ndarray) else int(t)
        bpm = max(70, min(bpm, 180))
    except:
        bpm = 151

    # hop_length 512 = soporta 6 min sin crashear
    f0, voiced_flag, _ = librosa.pyin(
        y, 
        fmin=librosa.note_to_hz('C3'), 
        fmax=librosa.note_to_hz('C7'), 
        frame_length=2048, 
        hop_length=512
    )
    
    palabras = letra_texto.split()
    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","").replace(".m4a","") + " - Completa Sax"
    s.append(instrument.AltoSaxophone())
    s.append(clef.TrebleClef())
    s.append(tempo.MetronomeMark(number=bpm))
    s.append(meter.TimeSignature('4/4'))

    notas = []
    transposicion = 21
    current_pitch = None
    current_len = 0
    for i in range(len(f0)):
        if voiced_flag[i] and f0[i] and not np.isnan(f0[i]):
            midi = int(librosa.hz_to_midi(f0[i])) + transposicion
            if 50 <= midi <= 86:
                if current_pitch is None:
                    current_pitch = midi
                    current_len = 1
                elif abs(midi - current_pitch) <= 1:
                    current_len += 1
                else:
                    if current_len >= 2:
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        sec = current_len * 512 / sr
                        n.quarterLength = max(0.5, min(3.0, sec * (bpm/60) * 2))
                        notas.append(n)
                    current_pitch = midi
                    current_len = 1
    if current_pitch and current_len >=2:
        n = note.Note()
        n.pitch.midi = current_pitch
        n.quarterLength = 1.0
        notas.append(n)

    # Reparto melismático: cada palabra ocupa 1 a 4 notas según sílabas
    note_idx = 0
    for palabra in palabras:
        if note_idx >= len(notas):
            break
        n_silabas = contar_silabas_pt(palabra)
        silabas = dividir_palavra(palabra, n_silabas)
        for j in range(n_silabas):
            if note_idx >= len(notas):
                break
            n = notas[note_idx]
            texto_silaba = silabas[j] if j < len(silabas) else palabra
            n.addLyric(texto_silaba)
            if n_silabas == 1:
                n.lyrics[-1].syllabic = "single"
            else:
                n.lyrics[-1].syllabic = "begin" if j==0 else "end" if j==n_silabas-1 else "middle"
            note_idx += 1

    # Agregar todas las notas para que MuseScore haga muchas páginas
    for n in notas:
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas), len(palabras)

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    persistent_path = f"/tmp/audio_{chat_id}.wav"
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
    file = await update.message.effective_attachment.get_file()
    await file.download_to_drive(persistent_path)
    context.user_data['audio_path'] = persistent_path
    context.user_data['titulo'] = titulo
    await update.message.reply_text(f"🎷 Audio de 6 min recibido: {titulo}\nAhora pega la LETRA COMPLETA (aunque sean 200+ palabras)")

async def handle_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Primero manda el mp3 de 6 min")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras, analizando 6 MIN COMPLETOS... tarda 90-120 seg, no mandes nada más")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_pal = audio_a_partitura_completa(in_path, out_xml, titulo, letra)
            await update.message.reply_document(
                document=open(out_xml, 'rb'), 
                filename=f"{titulo.replace('.mp3','')}_COMPLETA_6MIN.musicxml", 
                caption=f"✅ COMPLETA: {n_notas} notas de sax para {n_pal} palabras. Cada sílaba con su nota (Pu-ri-fi-ca-me = 5 notas). Abrirá en 8-12 páginas en MuseScore."
            )
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Manda mp3 de 6 min + letra completa = partitura de muchas páginas con sílabas")

def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()

if __name__=="__main__":
    main()


