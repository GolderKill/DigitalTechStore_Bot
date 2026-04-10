import sqlite3
import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, PreCheckoutQueryHandler, MessageHandler, filters, ContextTypes

# === CONFIGURACIÓN ===
# ⚠️ REEMPLAZA "TU_TOKEN_AQUI" con el token que te dio BotFather
TOKEN = "7991919991:AAEgjU-aTblealMolV5mJ9a2tCQHSyKUCIY"

# Activar logs para ver lo que pasa (útil para depurar)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# === CATÁLOGO DE PRODUCTOS CON IMÁGENES ===
# Puedes usar URLs de imágenes online o imágenes locales
# Para imágenes locales, colócalas en la carpeta 'productos/imagenes/'
PRODUCTOS = {
    'guia_python': {
        'nombre': '🐍 Guía Rápida de Python',
        'descripcion': 'PDF de 50 páginas con ejemplos prácticos.',
        'precio': 25,
        'archivo': 'productos/guia_python.pdf',
        'categoria': 'programacion',
        'imagen_url': 'https://i.imgur.com/python.jpg',
        'comision': 0.20
    },
    'plantilla_notion': {
        'nombre': '📋 Plantilla Notion',
        'descripcion': 'Sistema completo de productividad.',
        'precio': 35,
        'archivo': 'productos/plantilla_notion.pdf',
        'categoria': 'productividad',
        'imagen_url': 'https://i.imgur.com/notion.jpg',
        'comision': 0.20
    },
    'curso_excel': {  # ← NUEVO PRODUCTO
        'nombre': '📊 Curso de Excel',
        'descripcion': 'Aprende Excel desde cero.\n\n✅ Fórmulas\n✅ Tablas dinámicas',
        'precio': 45,
        'archivo': 'productos/curso_excel.pdf',
        'categoria': 'productividad',
        'imagen_url': 'https://i.imgur.com/excel.jpg',
        'comision': 0.20
    },
    'cheatsheet_html': {  # ← OTRO PRODUCTO NUEVO
        'nombre': '🌐 Cheatsheet HTML/CSS',
        'descripcion': 'Referencia rápida de HTML5 y CSS3.',
        'precio': 20,
        'archivo': 'productos/cheatsheet_html.pdf',
        'categoria': 'programacion',
        'imagen_url': 'https://i.imgur.com/html.jpg',
        'comision': 0.20
    },
}

# === BASE DE DATOS MEJORADA ===
def iniciar_db():
    """Crea todas las tablas necesarias"""
    conn = sqlite3.connect('ventas.db')
    
    # Tabla de compras
    conn.execute('''CREATE TABLE IF NOT EXISTS compras (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER,
        producto_id TEXT,
        precio INTEGER,
        comision_pagada INTEGER DEFAULT 0,
        referido_por INTEGER DEFAULT NULL,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabla de referidos
    conn.execute('''CREATE TABLE IF NOT EXISTS referidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER UNIQUE,
        codigo TEXT UNIQUE,
        balance INTEGER DEFAULT 0,
        total_ganado INTEGER DEFAULT 0
    )''')
    
    # Tabla de relación referido-referente
    conn.execute('''CREATE TABLE IF NOT EXISTS referencias (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referente_id INTEGER,
        referido_id INTEGER,
        fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

def obtener_o_crear_referido(usuario_id):
    """Obtiene o crea un registro de referido para el usuario"""
    conn = sqlite3.connect('ventas.db')
    cursor = conn.execute("SELECT * FROM referidos WHERE usuario_id = ?", (usuario_id,))
    referido = cursor.fetchone()
    
    if not referido:
        import random
        import string
        # Generar código único de 8 caracteres
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        conn.execute("INSERT INTO referidos (usuario_id, codigo) VALUES (?, ?)", (usuario_id, codigo))
        conn.commit()
        cursor = conn.execute("SELECT * FROM referidos WHERE usuario_id = ?", (usuario_id,))
        referido = cursor.fetchone()
    
    conn.close()
    return referido

def guardar_compra_con_referido(usuario_id, producto_id, precio, referido_por=None):
    """Guarda una compra y asigna comisión si hay referido"""
    conn = sqlite3.connect('ventas.db')
    
    # Guardar la compra
    conn.execute("INSERT INTO compras (usuario_id, producto_id, precio, referido_por) VALUES (?, ?, ?, ?)",
                 (usuario_id, producto_id, precio, referido_por))
    
    # Si hay referido, calcular y asignar comisión
    if referido_por:
        producto = PRODUCTOS.get(producto_id)
        if producto:
            comision = int(precio * producto['comision'])
            # Actualizar balance del referente
            conn.execute("UPDATE referidos SET balance = balance + ?, total_ganado = total_ganado + ? WHERE usuario_id = ?",
                         (comision, comision, referido_por))
    
    conn.commit()
    conn.close()

def registrar_referencia(referente_id, referido_id):
    """Registra que un usuario fue referido por otro"""
    conn = sqlite3.connect('ventas.db')
    
    # Verificar si ya existe la referencia
    cursor = conn.execute("SELECT * FROM referencias WHERE referente_id = ? AND referido_id = ?", 
                         (referente_id, referido_id))
    if not cursor.fetchone():
        conn.execute("INSERT INTO referencias (referente_id, referido_id) VALUES (?, ?)",
                    (referente_id, referido_id))
        conn.commit()
    
    conn.close()

def obtener_estadisticas_usuario(usuario_id):
    """Obtiene estadísticas del usuario (compras, referidos, balance)"""
    conn = sqlite3.connect('ventas.db')
    
    # Compras del usuario
    cursor = conn.execute("SELECT COUNT(*), SUM(precio) FROM compras WHERE usuario_id = ?", (usuario_id,))
    total_compras, total_gastado = cursor.fetchone()
    total_compras = total_compras or 0
    total_gastado = total_gastado or 0
    
    # Referidos que han comprado
    cursor = conn.execute("""
        SELECT COUNT(DISTINCT r.referido_id), SUM(c.precio) 
        FROM referencias r 
        JOIN compras c ON c.usuario_id = r.referido_id 
        WHERE r.referente_id = ?
    """, (usuario_id,))
    referidos_activos, ventas_referidos = cursor.fetchone()
    referidos_activos = referidos_activos or 0
    ventas_referidos = ventas_referidos or 0
    
    # Balance del referido
    cursor = conn.execute("SELECT balance, total_ganado FROM referidos WHERE usuario_id = ?", (usuario_id,))
    referido = cursor.fetchone()
    balance = referido[0] if referido else 0
    total_ganado = referido[1] if referido else 0
    
    conn.close()
    
    return {
        'compras': total_compras,
        'gastado': total_gastado,
        'referidos_activos': referidos_activos,
        'ventas_referidos': ventas_referidos,
        'balance': balance,
        'total_ganado': total_ganado
    }

# === MENÚ PRINCIPAL CON CATEGORÍAS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde al comando /start con soporte para referidos"""
    usuario_id = update.effective_user.id
    
    # Verificar si viene de un link de referido
    if context.args and len(context.args) > 0:
        codigo_referido = context.args[0]
        # Buscar quién tiene ese código
        conn = sqlite3.connect('ventas.db')
        cursor = conn.execute("SELECT usuario_id FROM referidos WHERE codigo = ?", (codigo_referido,))
        referente = cursor.fetchone()
        conn.close()
        
        if referente and referente[0] != usuario_id:
            registrar_referencia(referente[0], usuario_id)
            await update.message.reply_text(
                f"🎉 *¡Bienvenido!* Has sido referido por un amigo.\n\n"
                f"💰 Él recibirá una comisión por tus compras.\n"
                f"✨ ¡Y tú también puedes ganar! Usa /referidos para obtener tu link.",
                parse_mode='Markdown'
            )
    
    # Crear o actualizar registro de referido
    obtener_o_crear_referido(usuario_id)
    
    await update.message.reply_text(
        "🛍️ *Bienvenido a Mi Tienda Digital*\n\n"
        "Explora nuestro catálogo por categorías y compra productos digitales con Telegram Stars.\n"
        "¡Paga una vez y recibe el archivo al instante!\n\n"
        "✨ *Gana dinero*: Invita amigos y recibe comisiones de sus compras.\n\n"
        "Usa el menú de abajo para comenzar:",
        parse_mode='Markdown',
        reply_markup=menu_principal()
    )

def menu_principal():
    """Crea los botones del menú principal con categorías"""
    teclado = [
        [InlineKeyboardButton("📚 Ver catálogo", callback_data="catalogo")],
        [InlineKeyboardButton("🏆 Mis referidos", callback_data="mis_referidos")],
        [InlineKeyboardButton("💰 Retirar ganancias", callback_data="retirar")],
        [InlineKeyboardButton("❓ Ayuda", callback_data="ayuda")]
    ]
    return InlineKeyboardMarkup(teclado)

async def mostrar_categorias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra las categorías disponibles"""
    query = update.callback_query
    await query.answer()
    
    # Obtener categorías únicas
    categorias = set()
    for prod in PRODUCTOS.values():
        categorias.add(prod['categoria'])
    
    teclado = []
    for cat in categorias:
        nombre_cat = "💻 Programación" if cat == "programacion" else "📊 Productividad"
        teclado.append([InlineKeyboardButton(nombre_cat, callback_data=f"cat_{cat}")])
    
    teclado.append([InlineKeyboardButton("🔙 Volver al menú", callback_data="menu")])
    
    await query.edit_message_text(
        "📚 *Categorías disponibles*\n\nSelecciona una categoría para ver los productos:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def mostrar_productos_por_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra productos de una categoría específica"""
    query = update.callback_query
    await query.answer()
    
    categoria = query.data.replace("cat_", "")
    
    # Filtrar productos por categoría
    productos_cat = {pid: prod for pid, prod in PRODUCTOS.items() if prod['categoria'] == categoria}
    
    teclado = []
    for pid, prod in productos_cat.items():
        boton_texto = f"{prod['nombre']} — {prod['precio']}⭐"
        teclado.append([InlineKeyboardButton(boton_texto, callback_data=f"prod_{pid}")])
    
    teclado.append([InlineKeyboardButton("🔙 Volver a categorías", callback_data="catalogo")])
    
    nombre_categoria = "Programación" if categoria == "programacion" else "Productividad"
    await query.edit_message_text(
        f"📚 *{nombre_categoria}*\n\nSelecciona un producto para ver los detalles:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def mostrar_producto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra los detalles de un producto con imagen"""
    query = update.callback_query
    await query.answer()
    
    producto_id = query.data.replace("prod_", "")
    producto = PRODUCTOS.get(producto_id)
    
    if not producto:
        await query.edit_message_text("❌ Producto no encontrado.")
        return
    
    context.user_data['producto_a_comprar'] = producto_id
    
    mensaje = f"*{producto['nombre']}*\n\n"
    mensaje += f"{producto['descripcion']}\n\n"
    mensaje += f"💰 *Precio:* {producto['precio']} Stars\n\n"
    mensaje += "¿Deseas comprarlo?"
    
    teclado = [
        [InlineKeyboardButton(f"💎 Comprar por {producto['precio']} Stars", callback_data=f"comprar_{producto_id}")],
        [InlineKeyboardButton("🔙 Volver al catálogo", callback_data="catalogo")]
    ]
    
    # Enviar con imagen si hay URL
    if producto.get('imagen_url'):
        # Enviar nueva mensaje con foto
        await query.message.delete()
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=producto['imagen_url'],
            caption=mensaje,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(teclado)
        )
    else:
        await query.edit_message_text(
            mensaje,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(teclado)
        )

# === SISTEMA DE REFERIDOS ===
async def mostrar_referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra información del sistema de referidos"""
    query = update.callback_query
    await query.answer()
    
    usuario_id = update.effective_user.id
    stats = obtener_estadisticas_usuario(usuario_id)
    referido = obtener_o_crear_referido(usuario_id)
    codigo = referido[2]  # El código está en la tercera columna
    
    # Generar link de invitación
    bot_username = context.bot.username
    link_invitacion = f"https://t.me/{bot_username}?start={codigo}"
    
    mensaje = (
        "🏆 *Sistema de Referidos*\n\n"
        f"💰 *Tu balance:* {stats['balance']} Stars\n"
        f"📊 *Total ganado:* {stats['total_ganado']} Stars\n\n"
        f"👥 *Referidos que compraron:* {stats['referidos_activos']}\n"
        f"💸 *Ventas de referidos:* {stats['ventas_referidos']} Stars\n\n"
        f"🔗 *Tu link de invitación:*\n"
        f"`{link_invitacion}`\n\n"
        f"✨ *¿Cómo funciona?*\n"
        f"1️⃣ Comparte tu link con amigos\n"
        f"2️⃣ Cuando compren, tú ganas 20% de comisión\n"
        f"3️⃣ Acumula Stars y retíralos\n\n"
        f"📌 *Comisión:* 20% de cada compra de tus referidos"
    )
    
    teclado = [
        [InlineKeyboardButton("📋 Copiar link", callback_data="copiar_link")],
        [InlineKeyboardButton("🔙 Volver al menú", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        mensaje,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def copiar_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envía el link para que el usuario lo copie fácilmente"""
    query = update.callback_query
    await query.answer()
    
    usuario_id = update.effective_user.id
    referido = obtener_o_crear_referido(usuario_id)
    codigo = referido[2]
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start={codigo}"
    
    await query.message.reply_text(
        f"🔗 *Tu link de invitación:*\n\n"
        f"`{link}`\n\n"
        f"✅ *Copia y comparte este link*\n"
        f"Cuando alguien entre y compre, ganarás comisión.",
        parse_mode='Markdown'
    )

async def retirar_ganancias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Permite retirar las ganancias acumuladas"""
    query = update.callback_query
    await query.answer()
    
    usuario_id = update.effective_user.id
    stats = obtener_estadisticas_usuario(usuario_id)
    
    if stats['balance'] <= 0:
        await query.edit_message_text(
            "❌ *No tienes Stars para retirar*\n\n"
            "Invita amigos y gana comisiones de sus compras. Usa /referidos para obtener tu link.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu")]])
        )
        return
    
    # Crear factura para pagar al usuario
    try:
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="Retiro de ganancias",
            description=f"Retiro de {stats['balance']} Stars de tu balance de referidos",
            payload=f"withdraw_{usuario_id}",
            provider_token="",
            currency="XTR",
            prices=[{"label": "Retiro", "amount": stats['balance']}],
            start_parameter="withdraw"
        )
    except Exception as e:
        logging.error(f"Error al crear factura de retiro: {e}")
        await query.edit_message_text(
            "❌ *Error al procesar el retiro*\n\n"
            "Contacta al administrador para recibir tus ganancias.\n\n"
            f"Balance pendiente: {stats['balance']} Stars",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="menu")]])
        )

# === PROCESO DE PAGO ===
async def iniciar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Inicia el proceso de pago con Telegram Stars"""
    query = update.callback_query
    await query.answer()
    
    producto_id = query.data.replace("comprar_", "")
    producto = PRODUCTOS.get(producto_id)
    
    if not producto:
        await query.edit_message_text("❌ Producto no encontrado.")
        return
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=producto['nombre'],
        description=producto['descripcion'][:100],
        payload=f"pay_{producto_id}",
        provider_token="",
        currency="XTR",
        prices=[{"label": producto['nombre'], "amount": producto['precio']}],
        start_parameter="test_bot",
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verifica que el pago sea válido antes de procesarlo"""
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def pago_exitoso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Se ejecuta cuando el usuario completa el pago"""
    mensaje = update.message
    payload = mensaje.successful_payment.payload
    usuario_id = mensaje.from_user.id
    
    # Extraer el ID del producto
    producto_id = payload.replace("pay_", "")
    producto = PRODUCTOS.get(producto_id)
    
    if not producto:
        await mensaje.reply_text("❌ Error: Producto no encontrado.")
        return
    
    # Buscar si el usuario fue referido por alguien
    conn = sqlite3.connect('ventas.db')
    cursor = conn.execute("SELECT referente_id FROM referencias WHERE referido_id = ?", (usuario_id,))
    referente = cursor.fetchone()
    conn.close()
    
    referido_por = referente[0] if referente else None
    
    # Guardar la compra con referido
    guardar_compra_con_referido(usuario_id, producto_id, producto['precio'], referido_por)
    
    # Enviar el archivo digital
    try:
        with open(producto['archivo'], 'rb') as archivo:
            await mensaje.reply_document(
                document=archivo,
                caption=f"✅ *¡Gracias por tu compra!*\n\nHas adquirido: {producto['nombre']}\n\nGuarda este archivo, es tuyo para siempre.",
                parse_mode='Markdown'
            )
            
            # Notificar al referente si existe
            if referido_por:
                comision = int(producto['precio'] * producto['comision'])
                await context.bot.send_message(
                    chat_id=referido_por,
                    text=f"🎉 *¡Has ganado una comisión!*\n\n"
                         f"Un usuario que invitaste acaba de comprar *{producto['nombre']}*\n"
                         f"💰 Has ganado: *{comision} Stars*\n\n"
                         f"Usa /referidos para ver tu balance.",
                    parse_mode='Markdown'
                )
    except FileNotFoundError:
        await mensaje.reply_text(
            f"✅ *¡Pago recibido!* Has comprado: {producto['nombre']}\n\n"
            f"⚠️ El archivo no está disponible automáticamente. Contacta al administrador para recibir tu producto.\n\n"
            f"📧 ID de transacción: `{mensaje.successful_payment.telegram_payment_charge_id}`",
            parse_mode='Markdown'
        )
        logging.error(f"Archivo no encontrado: {producto['archivo']}")

# === AYUDA ===
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el mensaje de ayuda"""
    query = update.callback_query
    await query.answer()
    
    mensaje = (
        "❓ *¿Cómo funciona?*\n\n"
        "📚 *Comprar productos:*\n"
        "1️⃣ Explora el catálogo por categorías\n"
        "2️⃣ Selecciona un producto\n"
        "3️⃣ Presiona 'Comprar' y paga con Telegram Stars\n"
        "4️⃣ ¡Recibirás el archivo al instante!\n\n"
        "🏆 *Ganar dinero (Referidos):*\n"
        "1️⃣ Usa /referidos para obtener tu link\n"
        "2️⃣ Comparte el link con amigos\n"
        "3️⃣ Gana 20% de comisión en sus compras\n"
        "4️⃣ Acumula Stars y retíralos\n\n"
        "📌 *¿Qué son los Stars?*\n"
        "Son la moneda dentro de Telegram. Puedes comprarlos desde la app.\n\n"
        "❓ *¿Problemas?* Contacta al administrador."
    )
    
    teclado = [[InlineKeyboardButton("🔙 Volver al menú", callback_data="menu")]]
    await query.edit_message_text(
        mensaje,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(teclado)
    )

async def volver_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vuelve al menú principal"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🛍️ *Bienvenido a Mi Tienda Digital*\n\n"
        "Usa el menú de abajo para comenzar:",
        parse_mode='Markdown',
        reply_markup=menu_principal()
    )

# === COMANDOS DIRECTOS ===
async def cmd_referidos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /referidos directo"""
    usuario_id = update.effective_user.id
    stats = obtener_estadisticas_usuario(usuario_id)
    referido = obtener_o_crear_referido(usuario_id)
    codigo = referido[2]
    bot_username = context.bot.username
    link_invitacion = f"https://t.me/{bot_username}?start={codigo}"
    
    mensaje = (
        "🏆 *Tus Estadísticas de Referidos*\n\n"
        f"💰 *Balance:* {stats['balance']} Stars\n"
        f"📊 *Total ganado:* {stats['total_ganado']} Stars\n"
        f"👥 *Referidos activos:* {stats['referidos_activos']}\n\n"
        f"🔗 *Tu link:*\n`{link_invitacion}`\n\n"
        f"✨ Comparte el link y gana 20% de comisión en cada compra."
    )
    
    await update.message.reply_text(mensaje, parse_mode='Markdown')

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats para ver estadísticas de la tienda"""
    conn = sqlite3.connect('ventas.db')
    cursor = conn.execute("SELECT COUNT(*), SUM(precio) FROM compras")
    total_compras, total_stars = cursor.fetchone()
    cursor = conn.execute("SELECT SUM(total_ganado) FROM referidos")
    total_comisiones = cursor.fetchone()[0]
    conn.close()
    
    total_compras = total_compras or 0
    total_stars = total_stars or 0
    total_comisiones = total_comisiones or 0
    
    await update.message.reply_text(
        f"📊 *Estadísticas de la tienda*\n\n"
        f"🛒 Ventas totales: {total_compras}\n"
        f"⭐ Stars generados: {total_stars}\n"
        f"💰 Comisiones pagadas: {total_comisiones} Stars\n\n"
        f"💡 *Tip:* Usa /referidos para ver tu balance personal.",
        parse_mode='Markdown'
    )

# === CONFIGURAR Y EJECUTAR ===
def main():
    """Punto de entrada principal"""
    print("🚀 Iniciando el bot de tienda digital con referidos...")
    
    # Crear la base de datos
    iniciar_db()
    print("✅ Base de datos lista")
    
    # Crear carpetas necesarias
    if not os.path.exists('productos'):
        os.makedirs('productos')
        print("📁 Carpeta 'productos' creada. Coloca tus archivos allí.")
    
    if not os.path.exists('productos/imagenes'):
        os.makedirs('productos/imagenes')
        print("📁 Carpeta 'productos/imagenes' creada para imágenes locales.")
    
    # Crear la aplicación
    app = Application.builder().token(TOKEN).build()
    
    # Comandos directos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("referidos", cmd_referidos))
    app.add_handler(CommandHandler("stats", cmd_stats))
    
    # Callbacks del menú
    app.add_handler(CallbackQueryHandler(mostrar_categorias, pattern="^catalogo$"))
    app.add_handler(CallbackQueryHandler(ayuda, pattern="^ayuda$"))
    app.add_handler(CallbackQueryHandler(volver_menu, pattern="^menu$"))
    app.add_handler(CallbackQueryHandler(mostrar_referidos, pattern="^mis_referidos$"))
    app.add_handler(CallbackQueryHandler(retirar_ganancias, pattern="^retirar$"))
    app.add_handler(CallbackQueryHandler(copiar_link, pattern="^copiar_link$"))
    app.add_handler(CallbackQueryHandler(mostrar_productos_por_categoria, pattern="^cat_"))
    app.add_handler(CallbackQueryHandler(mostrar_producto, pattern="^prod_"))
    app.add_handler(CallbackQueryHandler(iniciar_compra, pattern="^comprar_"))
    
    # Manejadores de pagos
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, pago_exitoso))
    
    # Iniciar
    print("✅ Bot listo y funcionando. ¡A vender!")
    print("💡 Comandos disponibles: /start, /referidos, /stats")
    print("💡 Presiona Ctrl+C para detener")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()