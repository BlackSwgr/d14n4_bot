import os, logging, tempfile, re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import librosa
from music21 import stream, note, tempo, meter, instrument, clef, metadata
import numpy as np

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def dividir_silabas_pt(palabra):
    palabra = palabra.strip()
    if len(palabra) <= 3:
        return [palabra]
    # Divide decente: Nada -> Na-da, impossiveis -> im-pos-si-veis
    partes = re.findall(r'[^aeiouáéíóúâêôãõà]+[aeiouáéíóúâêôãõà]+(?:s|m|n|r|l)?|[aeiouáéíóúâêôãõà]+', palabra.lower(), re.I)
    if not partes:
        return [palabra]
    # Reconstruir con casing original
    res = []
    idx = 0
    for p in partes:
        l = len(p)
        res.append(palabra[idx:idx+l])
        idx += l
        if idx >= len(palabra): break
    if idx < len(palabra):
        res[-1] += palabra[idx:]
    return [r for r in res if r]

def audio_a_partitura_gesticulada(wav_path, out_xml_path, titulo, letra_texto):
    y, sr = librosa.load(wav_path, sr=16000, mono=True)
    duracion_real = len(y) / sr
    
    try:
        t, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = int(t[0]) if isinstance(t, np.ndarray) else int(t)
        bpm = max(75, min(bpm, 130))
    except:
        bpm = 85

    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C3'), fmax=librosa.note_to_hz('C6'), sr=sr, hop_length=512)
    
    palabras = letra_texto.replace("\n", " ").split()
    silabas_totales = []
    for p in palabras:
        silabas_totales.extend(dividir_silabas_pt(p))
    
    print(f"GESTICULADO {duracion_real:.1f}s | {len(palabras)} palabras -> {len(silabas_totales)} silabas")

    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","") + f" - {int(duracion_real//60)}:{int(duracion_real%60):02d}"
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
                    if current_len >= 4:
                        n = note.Note()
                        n.pitch.midi = current_pitch
                        n.quarterLength = 1.0  # FIX: solo 1.0, no 0.73 que rompe MusicXML
                        notas_detectadas.append(n)
                    current_pitch = midi; current_len = 1
    if current_pitch and current_len >=4:
        n = note.Note(); n.pitch.midi = current_pitch; n.quarterLength = 1.0
        notas_detectadas.append(n)

    # Asegura llenar 4:11 real
    compases_reales = int((duracion_real * bpm / 60) / 4)
    if len(notas_detectadas) < compases_reales * 2:
        falta = (compases_reales * 4) - len(notas_detectadas)
        for _ in range(int(falta)):
            n = note.Note(); n.pitch.midi = 65; n.quarterLength = 1.0
            notas_detectadas.append(n)

    # REPARTO GESTICULADO EN TODA LA DURACIÓN
    paso = len(notas_detectadas) / len(silabas_totales) if silabas_totales else 1
    notas_finales = []
    silaba_idx = 0

    for i, n_detect in enumerate(notas_detectadas):
        nueva = note.Note()
        nueva.pitch.midi = n_detect.pitch.midi
        nueva.quarterLength = 1.0

        pos_esperada = int(silaba_idx * paso)
        if i >= pos_esperada and silaba_idx < len(silabas_totales):
            nueva.addLyric(silabas_totales[silaba_idx])
            nueva.lyrics[0].syllabic = "single"
            silaba_idx += 1
        
        notas_finales.append(nueva)

    for n in notas_finales:
        s.append(n)

    s.write('musicxml', fp=out_xml_path)
    return len(notas_finales), len(silabas_totales), duracion_real

async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    persistent_path = f"/tmp/audio_{chat_id}.wav"
    titulo = update.message.audio.file_name if update.message.audio else update.message.document.file_name if update.message.document else "Cancion"
    file = await update.message.effective_attachment.get_file()
    await file.download_to_drive(persistent_path)
    context.user_data['audio_path'] = persistent_path
    context.user_data['titulo'] = titulo
    await update.message.reply_text(f"🎷 Recibido: {titulo} - modo GESTICULADO v5")

async def handle_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Manda primero el mp3")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras. Generando gesticulado...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_sil, dur = audio_a_partitura_gesticulada(in_path, out_xml, titulo, letra)
            await update.message.reply_document(
                document=open(out_xml, 'rb'), 
                filename=f"{titulo.replace('.mp3','')}_v5_GESTICULADO.musicxml", 
                caption=f"✅ v5 GESTICULADO: {int(dur//60)}:{int(dur%60):02d} | {n_notas} notas | {n_sil} silabas - sin [VERSO] que corta frases"
            )
            context.user_data.clear()
    except Exception as e:
        logging.error(e, exc_info=True)
        await update.message.reply_text(f"Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Manda mp3 + letra")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.ALL, handle_audio))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_lyrics))
    app.run_polling()

if __name__ == "__main__":
    main()
    


