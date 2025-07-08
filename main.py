import logging
import json
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler, ContextTypes
import re
from aiohttp import web


# Abilita il logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# Carica il token da una variabile d'ambiente per sicurezza
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("La variabile d'ambiente TELEGRAM_BOT_TOKEN non è stata impostata.")

# Carica gli ID dei gruppi e dei topic dalle variabili d'ambiente
try:
    GROUP_CHAT_ID = int(os.environ.get('GROUP_CHAT_ID'))
    TOPIC_MESSAGE_THREAD_ID = int(os.environ.get('TOPIC_MESSAGE_THREAD_ID'))
    MODERATION_CHAT_ID = int(os.environ.get('MODERATION_CHAT_ID'))
except (TypeError, ValueError):
    raise ValueError("Errore: Assicurati che le variabili d'ambiente GROUP_CHAT_ID, TOPIC_MESSAGE_THREAD_ID, e MODERATION_CHAT_ID siano impostate e siano numeri interi.")

# Stati della conversazione per l'annuncio
FOTO, TITOLO, DESCRIZIONE, LOCALITA, PREZZO, CONFERMA = range(6)
# Stati per il tutorial
TUTORIAL_START, TUTORIAL_STEP_1 = range(6, 8)


# /start configurazione comando --------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    support_topic_url = os.environ.get('SUPPORT_TOPIC_URL')
    messaggio_start = f"""Ciao {user.mention_html()}! 👋
Prima di pubblicare il tuo annuncio di Stock oggetti usati ecco una panoramica dei comandi che puoi usare. 

📖  <b>/readme</b>
Qui trovi tutto quello che devi sapere prima di pubblicare il tuo annuncio.

➡️  <b>/nuovo_annuncio</b>
Per iniziare la procedura guidata passo passo della pubblicazione tuo annuncio.

❌  <b>/cancel</b>
Per annullare la creazione del tuo annuncio.

🤖  <b>/cosa_sono_i_bot</b>
Se non hai mai usato i bot di telegram ti consigliamo questo semplicissimo tutorial.
"""
    if support_topic_url:
        messaggio_start += f"""
- - - - - - - - - - - -
🆘 Per qualsiasi problema tecnico o dubbio sul funzionamento del bot, puoi scrivere <a href="{support_topic_url}">qui nel topic di assistenza</a>.
"""
    
    try:
        await update.message.reply_html(messaggio_start)
    except Exception as e:
        logger.error(f"Impossibile inviare il messaggio /start. Errore: {e}.")
        await update.message.reply_text("Ciao! Si è verificato un errore nel caricare il messaggio di benvenuto. Contatta un amministratore.")
# --------------------------------------------------


async def readme(update: Update, context):
    """Fornisce una guida su come creare un annuncio."""
    testo_readme = """Ciao! Ecco cosa ti servirà per creare il tuo annuncio:

1.  <b>Le foto</b> dell'articolo.
2.  Un <b>titolo</b> accattivante.
3.  Una <b>descrizione</b> dettagliata.
4.  La <b>località</b> in cui si trova l'oggetto.
5.  Il <b>prezzo</b> di vendita.

Quando sei pronto, usa il comando /nuovo_annuncio per iniziare!"""
    await update.message.reply_text(testo_readme, parse_mode='HTML')


# --- Funzioni per il Tutorial Interattivo ---
async def cosa_sono_i_bot(update: Update, context):
    """Spiega cosa sono i bot e propone un tutorial."""
    testo_spiegazione = """🤖 <b>Cosa sono i Bot e come si usano?</b>

Un bot come me è un programma automatico con cui puoi interagire direttamente qui su Telegram. Non sono una persona reale, ma eseguo compiti specifici in base ai comandi che mi dai.

<b>Come si usa un comando?</b>
È semplicissimo! Un comando è una parola che inizia con una barra <b>/</b>, come <code>/start</code>.

Vuoi fare una prova pratica? Clicca qui sotto!"""

    keyboard = [[
        InlineKeyboardButton("▶️ Avvia mini-tutorial",
                             callback_data='start_tutorial')
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(testo_spiegazione,
                                    parse_mode='HTML',
                                    reply_markup=reply_markup)
    return TUTORIAL_START


async def start_tutorial(update: Update, context):
    """Avvia la parte pratica del tutorial."""
    query = update.callback_query
    await query.answer()

    testo_task = """Perfetto! Mettiamoci alla prova.

Il tuo compito è semplice: <b>invia il comando /prova</b>

Puoi farlo in due modi:
1. Scrivendo <code>/prova</code> e premendo invio.
2. Toccando il testo blu del comando qui sopra (su alcuni dispositivi funziona!)."""

    await query.edit_message_text(text=testo_task, parse_mode='HTML')
    return TUTORIAL_STEP_1


async def tutorial_prova_command(update: Update, context):
    """Gestisce il successo nel tutorial."""
    await update.message.reply_text(
        "🎉 Complimenti, hai usato il comando correttamente! Hai completato il tutorial. Ora sei prontissimo a usare tutti i miei comandi."
    )
    return ConversationHandler.END


async def tutorial_fallback(update: Update, context):
    """Guida l'utente se sbaglia durante il tutorial."""
    await update.message.reply_text(
        "Ci sei quasi! Ricorda, devi inviare il comando che inizia con la barra: /prova"
    )
    return TUTORIAL_STEP_1


# --- Funzioni per la Conversazione 'nuovo_annuncio' ---
async def nuovo_annuncio(update: Update, context):
    """Inizia la conversazione per un nuovo annuncio."""
    await update.message.reply_text(
        "<b>1  Carica le Foto</b>\n\n"
        "Allega una o più foto del tuo articolo \n\n"
        "<i>💡 Consigli: </i>\n"
        "<i>- Cerca di usare sfondi neutri</i>\n"
        "<i>- Allega una foto che mostri tutti gli oggetti </i>\n"
        "<i>- Usa foto di dettaglio per mostrare lo stato </i>\n",
        parse_mode='HTML')
    context.user_data['photos'] = []
    return FOTO


async def ricevi_foto(update: Update, context):
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        context.user_data['photos'].append(file_id)
        logger.info(f"Ricevuta foto: {file_id}")
        keyboard = [[KeyboardButton("✅ Fatto")]]
        reply_markup = ReplyKeyboardMarkup(keyboard,
                                           resize_keyboard=True,
                                           one_time_keyboard=True)
        await update.message.reply_text(
            "Foto ricevuta! Puoi inviarne altre oppure, quando hai finito, premi il bottone '✅ Fatto'.",
            reply_markup=reply_markup)
        return FOTO
    else:
        await update.message.reply_text("Per favore, invia una foto.")
        return FOTO


async def foto_fatto(update: Update, context):
    if not context.user_data.get('photos'):
        await update.message.reply_text(
            "Non hai inviato nessuna foto. Per favore, invia almeno una foto.")
        return FOTO
    await update.message.reply_text(
        "Ok, foto ricevute! Ora, per favore, invia il **titolo** del tuo annuncio.",
        reply_markup=ReplyKeyboardRemove())
    return TITOLO


async def ricevi_titolo(update: Update, context):
    context.user_data['title'] = update.message.text
    logger.info(f"Titolo ricevuto: {context.user_data['title']}")
    await update.message.reply_text(
        "Titolo ricevuto! Ora, per favora, invia la **descrizione** del tuo annuncio."
    )
    return DESCRIZIONE


async def ricevi_descrizione(update: Update, context):
    context.user_data['description'] = update.message.text
    logger.info(f"Descrizione ricevuta: {context.user_data['description']}")
    await update.message.reply_text(
        "Descrizione ricevuta! Ora, per favore, indica la **località** (es. Roma, Milano)."
    )
    return LOCALITA


async def ricevi_localita(update: Update, context):
    context.user_data['location'] = update.message.text
    logger.info(f"Località ricevuta: {context.user_data['location']}")
    await update.message.reply_text(
        "Località ricevuta! Infine, per favore, invia il **prezzo** del tuo articolo (solo il numero, es. 25.50)."
    )
    return PREZZO


async def ricevi_prezzo(update: Update, context):
    price_text = update.message.text
    try:
        price = float(price_text.replace(',', '.'))
        context.user_data['price'] = price
        logger.info(f"Prezzo ricevuto: {context.user_data['price']}")
        summary = (
            f"**Riepilogo del tuo annuncio:**\n\n"
            f"**Titolo:** {context.user_data.get('title', 'N/A')}\n"
            f"**Descrizione:** {context.user_data.get('description', 'N/A')}\n"
            f"**Località:** {context.user_data.get('location', 'N/A')}\n"
            f"**Prezzo:** €{context.user_data.get('price', 'N/A'):.2f}\n"
            f"**Numero di foto:** {len(context.user_data.get('photos', []))}\n\n"
            "È corretto? Digita 'Si' per confermare o 'No' per annullare.")
        await update.message.reply_text(summary, parse_mode='Markdown')
        return CONFERMA
    except ValueError:
        await update.message.reply_text(
            "Formato prezzo non valido. Per favora, inserisci solo un numero (es. 25 o 25.50)."
        )
        return PREZZO


async def conferma_annuncio(update: Update, context):
    if update.message.text.lower() == 'si':
        await update.message.reply_text(
            "Perfetto! Il tuo annuncio è stato ricevuto e sarà inviato agli amministratori per l'approvazione. Ti avviserò non appena sarà pubblicato. Grazie!",
            reply_markup=ReplyKeyboardRemove())
        photos = context.user_data.get('photos', [])
        title = context.user_data.get('title', 'N/A')
        description = context.user_data.get('description', 'N/A')
        location = context.user_data.get('location', 'N/A')
        price = context.user_data.get('price', 'N/A')
        moderation_card_text = (
            f"🚨 **NUOVO ANNUNCIO DA APPROVARE!** 🚨\n\n"
            f"**Da Utente:** {update.effective_user.mention_html()}\n\n"
            f" **Articolo:** {title}\n"
            f" **Descrizione:** {description}\n"
            f" **Località:** {location}\n"
            f" **Prezzo:** €{price:.2f}\n\n"
            f"Approvazione richiesta. Cosa vuoi fare?")
        keyboard = [[
            InlineKeyboardButton(
                "✅ Approva",
                callback_data=f"approve_{update.effective_user.id}"),
            InlineKeyboardButton(
                "❌ Rifiuta",
                callback_data=f"reject_{update.effective_user.id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            if photos:
                media_group = [
                    InputMediaPhoto(
                        media=file_id,
                        caption=moderation_card_text if i == 0 else None,
                        parse_mode='HTML') for i, file_id in enumerate(photos)
                ]
                sent_messages_moderation = await context.bot.send_media_group(
                    chat_id=MODERATION_CHAT_ID, media=media_group)
                moderation_message_id = sent_messages_moderation[0].message_id
                await context.bot.edit_message_reply_markup(
                    chat_id=MODERATION_CHAT_ID,
                    message_id=moderation_message_id,
                    reply_markup=reply_markup)
            else:
                sent_message_moderation = await context.bot.send_message(
                    chat_id=MODERATION_CHAT_ID,
                    text=moderation_card_text,
                    parse_mode='HTML',
                    reply_markup=reply_markup)
                moderation_message_id = sent_message_moderation.message_id
            context.bot_data[str(moderation_message_id)] = {
                'photos': photos,
                'title': title,
                'description': description,
                'location': location,
                'price': price,
                'original_user_id': update.effective_user.id,
                'moderation_card_text': moderation_card_text
            }
        except Exception as e:
            logger.error(f"Errore durante l'invio per moderazione: {e}")
            await update.message.reply_text(
                "Si è verificato un errore durante l'invio per moderazione. Riprova più tardi."
            )
        context.user_data.clear()
        return ConversationHandler.END
    elif update.message.text.lower() == 'no':
        await update.message.reply_text(
            "Ok, annuncio annullato. Puoi riavviare con /nuovo_annuncio.",
            reply_markup=ReplyKeyboardRemove())
        context.user_data.clear()
        return ConversationHandler.END
    else:
        await update.message.reply_text("Per favora, rispondi 'Si' o 'No'.")
        return CONFERMA


async def cancel(update: Update, context):
    user = update.effective_user
    logger.info(f"Utente {user.first_name} ha annullato la conversazione.")
    await update.message.reply_text(
        'Operazione annullata. Puoi riavviare con /nuovo_annuncio.',
        reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


async def button_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    moderation_message_id = query.message.message_id
    ad_data = context.bot_data.get(str(moderation_message_id))
    if not ad_data:
        await query.edit_message_text(
            "Errore: Dati dell'annuncio non trovati o già elaborati.",
            reply_markup=None)
        return
    action = query.data.split('_')[0]
    original_user_id = ad_data.get('original_user_id')
    original_moderation_text = ad_data.get('moderation_card_text',
                                           "Testo originale non disponibile.")
    card_text = (f" **Articolo:** {ad_data['title']}\n"
                 f" **Descrizione:** {ad_data['description']}\n"
                 f" **Località:** {ad_data['location']}\n"
                 f" **Prezzo:** €{ad_data['price']:.2f}\n\n"
                 f"Contatta l'utente per maggiori info!")
    if action == 'approve':
        try:
            if ad_data['photos']:
                media_group = [
                    InputMediaPhoto(media=file_id,
                                    caption=card_text if i == 0 else None,
                                    parse_mode='Markdown')
                    for i, file_id in enumerate(ad_data['photos'])
                ]
                await context.bot.send_media_group(
                    chat_id=GROUP_CHAT_ID,
                    media=media_group,
                    message_thread_id=TOPIC_MESSAGE_THREAD_ID)
            else:
                await context.bot.send_message(
                    chat_id=GROUP_CHAT_ID,
                    text=card_text,
                    parse_mode='Markdown',
                    message_thread_id=TOPIC_MESSAGE_THREAD_ID)
            if original_user_id:
                await context.bot.send_message(
                    original_user_id,
                    "✅ Il tuo annuncio è stato approvato e pubblicato!")
            if query.message.photo:
                await query.edit_message_caption(
                    caption=
                    f"✅ Annuncio Approvato da {query.from_user.first_name}\n\n{original_moderation_text}",
                    parse_mode='HTML',
                    reply_markup=None)
            else:
                await query.edit_message_text(
                    f"✅ Annuncio Approvato da {query.from_user.first_name}\n\n{original_moderation_text}",
                    parse_mode='HTML',
                    reply_markup=None)
        except Exception as e:
            logger.error(f"Errore durante l'approvazione e pubblicazione: {e}")
    elif action == 'reject':
        if query.message.photo:
            await query.edit_message_caption(
                caption=
                f"❌ Annuncio Rifiutato da {query.from_user.first_name}\n\n{original_moderation_text}",
                parse_mode='HTML',
                reply_markup=None)
        else:
            await query.edit_message_text(
                f"❌ Annuncio Rifiutato da {query.from_user.first_name}\n\n{original_moderation_text}",
                parse_mode='HTML',
                reply_markup=None)
        if original_user_id:
            await context.bot.send_message(
                original_user_id,
                "❌ Il tuo annuncio è stato rifiutato dagli amministratori.")
    if str(moderation_message_id) in context.bot_data:
        del context.bot_data[str(moderation_message_id)]


# --- NUOVA STRUTTURA DI AVVIO CON SERVER AIOHTTP ---


async def health_check(request: web.Request) -> web.Response:
    """Endpoint per UptimeRobot. Risponde a richieste GET su /."""
    return web.Response(text="Bot is alive!", status=200)


async def telegram_webhook_handler(request: web.Request) -> web.Response:
    """Gestisce gli aggiornamenti in arrivo da Telegram su /webhook."""
    application = request.app["bot_application"]
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response()  # Risponde 200 OK a Telegram
    except Exception as e:
        logger.error(
            f"Errore nella gestione dell'aggiornamento da Telegram: {e}")
        return web.Response(status=500)


async def main() -> None:
    """Configura il bot e avvia il server web."""
    # Costruisce l'applicazione del bot
    application = Application.builder().token(TOKEN).build()

    # --- Registrazione degli handler ---
    annuncio_handler = ConversationHandler(
        entry_points=[CommandHandler('nuovo_annuncio', nuovo_annuncio)],
        states={
            FOTO: [
                MessageHandler(filters.PHOTO, ricevi_foto),
                MessageHandler(filters.TEXT & filters.Regex('^✅ Fatto$'),
                               foto_fatto),
            ],
            TITOLO:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_titolo)],
            DESCRIZIONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               ricevi_descrizione)
            ],
            LOCALITA:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_localita)],
            PREZZO:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, ricevi_prezzo)],
            CONFERMA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               conferma_annuncio)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    tutorial_handler = ConversationHandler(
        entry_points=[CommandHandler("cosa_sono_i_bot", cosa_sono_i_bot)],
        states={
            TUTORIAL_START:
            [CallbackQueryHandler(start_tutorial, pattern='^start_tutorial$')],
            TUTORIAL_STEP_1: [
                CommandHandler("prova", tutorial_prova_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               tutorial_fallback)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("readme", readme))
    application.add_handler(annuncio_handler)
    application.add_handler(
        tutorial_handler)  # <-- NUOVO HANDLER PER IL TUTORIAL
    application.add_handler(
        CallbackQueryHandler(button_callback,
                             pattern=r'^(approve|reject)_\d+$'))

    # Questo prepara il bot a ricevere aggiornamenti, ma non avvia la ricezione.
    await application.initialize()

    # --- Impostazione del server web AIOHTTP ---
    web_app = web.Application()
    web_app["bot_application"] = application
    web_app.router.add_get("/", health_check)
    web_app.router.add_post("/webhook", telegram_webhook_handler)

    
# Menù Bot Telegram ----------------------------------------------------------
    comandi_menu = [
        BotCommand("start", "Avvia il bot"),
        BotCommand("nuovo_annuncio", "Crea annuncio Stock di oggetti"),
        BotCommand("readme", "Istruzioni preliminari"),
        BotCommand("cosa_sono_i_bot", "Come usare i bot di telegram"),
        BotCommand("cancel", "Annulla l'operazione corrente")
    ]
    await application.bot.set_my_commands(comandi_menu)
#----------------------------------------------------------

    
    # Imposta l'URL del webhook con i server di Telegram
    # Carica l'URL base del server da una variabile d'ambiente
    BASE_URL = os.environ.get('BASE_URL')
    if not BASE_URL:
        raise ValueError("La variabile d'ambiente BASE_URL non è stata impostata.")

    # La riga successiva userà questa variabile
    await application.bot.set_webhook(url=f"{BASE_URL}/webhook", allowed_updates=Update.ALL_TYPES)
    logger.info(f"Webhook impostato su {BASE_URL}/webhook")
    

    # --- Avvio del server ---
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Server avviato su porta {port}")

    # Mantiene lo script in esecuzione
    await asyncio.Event().wait()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Script interrotto manualmente.")
