import os, logging, tempfile
import numpy as np
from collections import Counter
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata, expressions

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def audio_a_partitura_completa(wav_path, out_xml_path, titulo, letra_texto):
    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    duracion_real = len(y) / sr
    
    try:
        t, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(t[0]) if isinstance(t, np.ndarray) else int(t)
        bpm = max(75, min(bpm, 140))
    except:
        bpm = 88

    # Calculamos cuántos compases debe tener REALMENTE 4:11
    compases_reales = int((duracion_real * bpm / 60) / 4)
    print(f"DURACION REAL {duracion_real:.1f}s = {compases_reales} compases a {bpm} BPM")

    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C6'), sr=sr, hop_length=512) # hop más fino = más notas
    
    # VERSOS Y CORO: si mandas la letra con saltos de línea, los respeto. Si no, la parto cada 8 palabras
    if "\n" in letra_texto:
        versos_raw = [v.strip() for v in letra_texto.split("\n") if v.strip()]
    else:
        palabras_temp = letra_texto.split()
        versos_raw = [" ".join(palabras_temp[i:i+8]) for i in range(0, len(palabras_temp), 8)]

    # Detectar coro: el verso que más se repite
    conteo = Counter([v.lower() for v in versos_raw])
    coro_texto = conteo.most_common(1)[0][0] if conteo else ""

    palabras = letra_texto.split()

    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","") + f" - {int(duracion_real//60)}:{int(duracion_real%60):02d} - Completa"
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
                    current_pitch = midi; current_len = 1
                elif abs(midi - current_pitch) <= 2:
                    current_len += 1
                else:
                    if current_len >= 3: # BAJAMOS A 3 para tener más notas y llenar los 90 compases
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        # duración real según cuanto duró esa nota
                        dur_seg = (current_len * 512) / sr
                        q_len = max(0.5, min(dur_seg * bpm / 60, 2.0))
                        n.quarterLength = q_len
                        notas_detectadas.append(n)
                    current_pitch = midi; current_len = 1
    if current_pitch and current_len >=3:
        n = note.Note(); n.pitch.midi = current_pitch
        n.quarterLength = 1.0
        notas_detectadas.append(n)

    total_notas = len(notas_detectadas)
    print(f"Notas detectadas para llenar {compases_reales} compases: {total_notas}")

    # Reparto de versos en toda la canción
    notas_finales = []
    verso_idx = 0
    palabras_en_verso_actual = []
    if versos_raw:
        palabras_en_verso_actual = versos_raw[0].split()
    
    palabra_idx_global = 0
    paso_versos = total_notas / len(versos_raw) if versos_raw else 1

    for i, n_detect in enumerate(notas_detectadas):
        nueva = note.Note()
        nueva.pitch.midi = n_detect.pitch.midi
        nueva.quarterLength = n_detect.quarterLength

        # Cambio de verso
        if i >= int((verso_idx+1) * paso_versos) and verso_idx < len(versos_raw)-1:
            verso_idx += 1
            palabras_en_verso_actual = versos_raw[verso_idx].split()
            palabra_idx_global = 0
            # MARCA DE SECCIÓN LEGIBLE
            es_coro = versos_raw[verso_idx].lower() == coro_texto
            marca = "CORO" if es_coro else f"VERSO {verso_idx+1}"
            nueva.addLyric(marca)
            # Texto grande arriba del pentagrama
            nueva.addLyric(f"--- {marca} ---")
        
        # Letra normal palabra por palabra pero sin mezclar versos
        if palabra_idx_global < len(palabras_en_verso_actual):
            if len(nueva.lyrics) == 0:
                nueva.addLyric(palabras_en_verso_actual[palabra_idx_global])
            else:
                # Si ya tiene marca de CORO/VERSO, añade palabra como segunda letra
                nueva.addLyric(palabras_en_verso_actual[palabra_idx_global])
            nueva.lyrics[-1].syllabic = "single"
            palabra_idx_global += 1
        
        notas_finales.append(nueva)

    # Rellenar con silencios si faltan compases para llegar a 4:11 reales
    quarters_actuales = sum(n.quarterLength for n in notas_finales)
    quarters_necesarios = compases_reales * 4
    if quarters_actuales < quarters_necesarios:
        falta = quarters_necesarios - quarters_actuales
        print(f"Faltan {falta} negras, añadiendo descansos instrumentales")
        # Añadimos notas largas instrumentales sin letra al final para respetar 4:11
        while falta > 0:
            n = note.Note()
            n.pitch.midi = 65
            n.quarterLength = min(4.0, falta)
            notas_finales.append(n)
            falta -= n.quarterLength

    for n in notas_finales:
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas_finales), len(palabras), duracion_real, compases_reales

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    persistent_path = f"/tmp/audio_{chat_id}.wav"
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
    file = await update.message.effective_attachment.get_file()
    await file.download_to_drive(persistent_path)
    context.user_data['audio_path'] = persistent_path
    context.user_data['titulo'] = titulo
    await update.message.reply_text(f"🎷 Recibido: {titulo}\nAhora manda la letra con saltos de línea:\nVerso 1\nVerso 2\nCORO\nPara que te marque VERSO/CORO")

async def handle_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Manda primero el mp3")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras, {len(letra.splitlines())} líneas. Armando partitura completa con marcas de CORO/VERSO...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_pal, dur, compases = audio_a_partitura_completa(in_path, out_xml, titulo, letra)
            await update.message.reply_document(
                document=open(out_xml, 'rb'), 
                filename=f"{titulo.replace('.mp3','')}_{compases}compases_{n_pal}pal.musicxml", 
                caption=f"✅ {int(dur//60)}:{int(dur%60):02d} REALES = {compases} compases, {n_notas} notas, {n_pal} palabras\nVERSO/CORO marcado, legible, sin mezclar."
            )
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Manda mp3 + letra con saltos de línea para detectar versos")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()

if __name__ == "__main__":
    main()
    
