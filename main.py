cat > main.py << 'PY'
import os
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from reportlab.pdfgen import canvas
import tempfile
from datetime import datetime
TOKEN=os.getenv("TELEGRAM_TOKEN")
async def start(update, context):
    await update.message.reply_text("D14N4 activo. Enviame texto.")
async def handle(update, context):
    texto=update.message.text
    f=tempfile.NamedTemporaryFile(delete=False,suffix=".pdf")
    c=canvas.Canvas(f.name)
    c.drawString(50,800,f"D14N4 - {datetime.now()}")
    y=770
    for line in texto.split("\n"):
        c.drawString(50,y,line[:90]); y-=15
    c.save()
    await update.message.reply_document(document=open(f.name,'rb'), filename="D14N4.pdf")
def main():
    app=Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start",start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()
if __name__=="__main__": main()
PY
