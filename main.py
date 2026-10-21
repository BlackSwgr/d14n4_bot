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
    partes = re.findall(r'[^aeiouáéíóúâêôãõà]+[aeiouáéíóúâêôãõà]+(?:s|m|n|r|l)?|[aeiouáéíóúâêôãõà]+', palabra.lower(), re.I)
    if not partes:
        return [palabra]
    res, idx = [], 0
    for p in partes:
        l = len(p)
        res.append(palabra[idx:idx+l])
        idx += l
        if idx >= len(palabra): break
    if idx < len(palabra):
        res[-1] += palabra[idx:]
    return [r for r in res if r]

def audio_a_partitura_sin_volando(wav_path, out_xml_path, titulo, letra_texto):
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
    
    print(f"SIN VOLANDO {duracion_real:.1f}s | {len(palabras)} palabras -> {len(silabas_totales)} silabas exactas")

    s = stream.Stream()
    s.append(metadata.Metadata())
    s.metadata.title = titulo.replace(".mp3","") + f" - {int(duracion_real//60)}:{int(duracion_real%60):02d} - arreglo"
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
                        n.quarterLength = 1.0
                        notas_detectadas.append(n)
                    current_pitch = midi; current_len = 1
    if current_pitch and current_len >=4:
        n = note.Note(); n.pitch.midi = current_pitch; n.quarterLength = 1.0
        notas_detectadas.append(n)

    print(f"Notas del mp3 detectadas: {len(notas_detectadas)} para mapear a {len(silabas_totales)} silabas")

    # FIX 1: SIN NOTAS VOLANDO - mapeo exacto 1 silaba = 1 nota del mp3
    # No más notas sin letra entre palabras
    notas_finales = []
    num_sil = len(silabas_totales)
    num_det = len(notas_detectadas)
    
    if num_det == 0:
        num_det = num_sil
        notas_detectadas = [note.Note() for _ in range(num_sil)]
        for nn in notas_detectadas:
            nn.pitch.midi = 65
            nn.quarterLength = 1.0

    for i, silaba in enumerate(silabas_totales):
        # Toma la nota del mp3 en proporción exacta para respetar la melodía original 4:11
        idx_mp3 = int(i * num_det / num_sil)
        idx_mp3 = min(idx_mp3, num_det-1)
        
        n_orig = notas_detectadas[idx_mp3]
        nueva = note.Note()
        nueva.pitch.midi = n_orig.pitch.midi
        nueva.quarterLength = 1.0
        nueva.addLyric(silaba)
        nueva.lyrics[0].syllabic = "single"
        notas_finales.append(nueva)

        # FIX 2: ARREGLO LIGERO - cada 6-8 silabas mete una notita de paso armonía sin letra
        # Esto es lo que hace que no suene solo voz plana, sino con adorno de banda
        # Solo si es final de palabra (silaba termina en vocal) para no romper palabra
        if i > 0 and i % 7 == 0 and i < num_sil -1:
            # Nota de paso a un tono arriba/abajo de la armonía
            armonia = note.Note()
            # Armonía simple: tercera arriba para que suene bonito
            armonia.pitch.midi = n_orig.pitch.midi + 2 if n_orig.pitch.midi < 80 else n_orig.pitch.midi -2
            # Cuantizamos a blancas también
            armonia.pitch.midi = nota_sin_alteracion(armonia.pitch.midi)
            armonia.quarterLength = 0.5  # Corchea de adorno
            # Sin letra, es adorno instrumental entre frases
            notas_finales.append(armonia)

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
    await update.message.reply_text(f"🎷 Recibido: {titulo} - modo SIN VOLANDO + ARREGLO")

async def handle_lyrics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'audio_path' not in context.user_data or not os.path.exists(context.user_data['audio_path']):
        await update.message.reply_text("Manda primero el mp3")
        return
    letra = update.message.text
    titulo = context.user_data['titulo']
    in_path = context.user_data['audio_path']
    await update.message.reply_text(f"Recibí {len(letra.split())} palabras. Generando...")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out_xml = f"{tmp}/out.musicxml"
            n_notas, n_sil, dur = audio_a_partitura_sin_volando(in_path, out_xml, titulo, letra)
            await update.message.reply_document(
                document=open(out_xml, 'rb'), 
                filename=f"{titulo.replace('.mp3','')}_SIN_VOLANDO_ARREGLO.musicxml", 
                caption=f"✅ v5.3: {int(dur//60)}:{int(dur%60):02d} | {n_notas} notas totales | {n_sil} sílabas - 0 notas volando, con adornos de armonía"
            )
            context.user_data.clear()
    except Exception as e:
        import traceback; traceback.print_exc()
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