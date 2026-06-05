# =================================================================
# SERVIDOR FLASK UNIFICADO: INTEGRACIÓN DEFINITIVA SIN SECRETOS
# =================================================================

import os
import time
import qrcode
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from twilio.rest import Client
from dotenv import load_dotenv

# Cargar las variables de entorno desde el archivo secreto .env
load_dotenv()

app = Flask(__name__)

# --- CONFIGURACIONES PROTEGIDAS DESDE VARIABLES DE ENTORNO ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'clave_de_emergencia_por_si_falla_el_env')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///catalogo.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configuración de subida de archivos (Fotos de perfil - Clase 9)
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # Peso límite de foto: 2 Megabytes
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Extensiones de imagen que permitimos por seguridad
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    """Verifica que el archivo tenga una extensión válida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Inicializamos la base de datos SQLite
db = SQLAlchemy(app)

# --- CREDENCIALES PROTEGIDAS DE TWILIO (Cargadas de .env sin hardcodear) ---
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER')

try:
    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    else:
        twilio_client = None
except Exception as e:
    print(f"Error inicializando Twilio API: {e}")
    twilio_client = None


# --- MODELOS DE DATOS (SQLite) ---

class Usuario(db.Model): 
    id = db.Column(db.Integer, primary_key=True) 
    username = db.Column(db.String(50), unique=True, nullable=False) 
    password_hash = db.Column(db.String(255), nullable=False) 
    avatar = db.Column(db.String(255), nullable=True)  # Ruta de la imagen de perfil

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    categoria = db.Column(db.String(50), default="General")

    def to_dict(self):
        """Convierte un producto de DB a JSON (Clase 5)."""
        return {
            "id": self.id,
            "nombre": self.nombre,
            "precio": self.precio,
            "categoria": self.categoria
        }

# Creación de tablas de la base de datos automáticamente
with app.app_context(): 
    db.create_all() 


# --- OPERACIÓN: SUBIDA DE IMÁGENES (Clase 9) ---

@app.route('/subir_avatar', methods=['POST'])
def subir_avatar():
    if 'user_id' not in session:
        flash("Debes iniciar sesión para subir una imagen.", "warning")
        return redirect(url_for('login'))

    if 'foto_perfil' not in request.files:
        flash("No se seleccionó ningún archivo.", "error")
        return redirect(url_for('dashboard'))

    archivo = request.files['foto_perfil']

    if archivo.filename == '':
        flash("No has seleccionado un archivo.", "error")
        return redirect(url_for('dashboard'))

    if archivo and allowed_file(archivo.filename):
        # Limpiamos el nombre original para evitar inyecciones de código
        nombre_original = secure_filename(archivo.filename)
        # Hacemos el nombre único usando el ID de usuario
        nombre_unico = f"user_{session['user_id']}_{nombre_original}"
        
        ruta_completa = os.path.join(app.config['UPLOAD_FOLDER'], nombre_unico)
        
        try:
            archivo.save(ruta_completa)
            
            # Guardamos la ruta del avatar en el usuario correspondiente de la DB
            usuario_db = Usuario.query.get(session['user_id'])
            if usuario_db:
                usuario_db.avatar = f"/static/uploads/{nombre_unico}"
                db.session.commit()
                flash("¡Tu foto de perfil se ha guardado exitosamente!", "success")
        except Exception as e:
            print(f"Error escribiendo archivo: {e}")
            flash("Error al procesar y guardar la imagen.", "error")
    else:
        flash("Formato de archivo no admitido. Sube solo PNG, JPG, JPEG o GIF.", "error")

    return redirect(url_for('dashboard'))


# --- RUTAS DE NAVEGACIÓN Y CRUD DE PRODUCTOS (Clase 4 y 5) ---

@app.route('/')
def index():
    productos_db = Producto.query.all()
    return render_template('index.html', productos=productos_db, titulo="Inicio")

@app.route('/agregar', methods=['POST'])
def agregar_producto():
    nombre = request.form.get('nombre')
    precio = request.form.get('precio')
    
    if nombre and precio:
        nuevo_producto = Producto(nombre=nombre, precio=float(precio))
        db.session.add(nuevo_producto)
        db.session.commit()
        flash("Producto guardado correctamente en la base de datos.", "success")
    return redirect(url_for('index'))

@app.route('/borrar/<int:id>')
def eliminar_producto(id):
    producto = Producto.query.get(id)
    if producto:
        db.session.delete(producto)
        db.session.commit()
        flash("Producto eliminado.", "info")
    return redirect(url_for('index'))

@app.route('/api/buscar')
def buscar_productos():
    query_text = request.args.get('q', '').lower()
    if not query_text:
        return jsonify([])
    resultados = Producto.query.filter(Producto.nombre.ilike(f'%{query_text}%')).all()
    return jsonify([p.to_dict() for p in resultados])


# --- RUTAS DE LA CLASE 2 Y 3 (Contacto y Servicios) ---

@app.route('/contacto', methods=['GET', 'POST'])
def contacto():
    mensaje_error = None
    mensaje_exito = None

    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        telefono = request.form.get('telefono')

        if not nombre or not email or not telefono:
            mensaje_error = "⚠️ Todos los campos son obligatorios."
        elif "@" not in email or "." not in email:
            mensaje_error = "📧 El formato del correo electrónico no es válido."
        elif not telefono.isdigit() or len(telefono) < 7:
            mensaje_error = "📞 Por favor, ingresa un número de teléfono válido."
        else:
            mensaje_exito = f"✅ ¡Perfecto {nombre}! Hemos recibido tus datos de contacto."

    return render_template('contacto.html', titulo="Contacto", error=mensaje_error, exito=mensaje_exito)

@app.route('/servicios')
def servicios():
    datos_servicios = [
        {"nombre": "Corte de Cabello", "precio": 25, "disponible": True},
        {"nombre": "Barba Premium", "precio": 15, "disponible": True},
        {"nombre": "Tinte Pro", "precio": 40, "disponible": False},
        {"nombre": "Masaje Facial", "precio": 20, "disponible": True}
    ]
    return render_template('servicios.html', titulo="Servicios", servicios=datos_servicios)


# --- RUTAS DE RESERVAS CON QR Y WHATSAPP (Clase 7) ---

@app.route('/reserva')
def formulario_reserva():
    return render_template('reserva.html', titulo="Reservar Cita")

@app.route('/reservar', methods=['POST'])
def reservar():
    nombre = request.form.get('nombre')
    telefono = request.form.get('telefono')
    servicio = request.form.get('servicio')

    if not nombre or not telefono or not servicio:
        flash("Todos los campos del formulario son obligatorios.", "error")
        return redirect(url_for('formulario_reserva'))

    ticket_id = "TKT-2026-99"

    # Generación de Código QR físico en static/qrs/
    try:
        qr_data = f"Ticket: {ticket_id} | Cliente: {nombre} | Servicio: {servicio}"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(qr_data)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        ruta_qr = f"static/qrs/{ticket_id}.png"
        
        os.makedirs("static/qrs", exist_ok=True)
        img.save(ruta_qr)
    except Exception as e:
        print(f"Error generando QR: {e}")
        flash("Ocurrió un error al procesar el código QR.", "error")
        return redirect(url_for('formulario_reserva'))

    # Envío asíncrono de WhatsApp con Twilio API
    try:
        if twilio_client:
            cuerpo = f"¡Hola {nombre}! 🌿 Tu reserva para '{servicio}' se ha confirmado.\n\n🎟️ Código de Ticket: {ticket_id}\n\nPresenta tu código QR adjunto al llegar."
            twilio_client.messages.create(
                body=cuerpo,
                from_=TWILIO_WHATSAPP_NUMBER,
                to=f"whatsapp:{telefono}"
            )
            flash("¡Reserva confirmada! Te enviamos un mensaje de WhatsApp.", "success")
        else:
            flash("Reserva guardada de manera local (Twilio no configurado).", "warning")
    except Exception as e:
        print(f"Error Twilio: {e}")
        flash("Reserva creada, pero falló la notificación de WhatsApp.", "warning")

    return redirect(url_for('formulario_reserva'))


# --- RUTAS DE AUTENTICACIÓN (Clase 6) ---

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        usuario = request.form.get('username')
        clave = request.form.get('password')
        
        hash_seguro = generate_password_hash(clave, method='scrypt')
        nuevo_usuario = Usuario(username=usuario, password_hash=hash_seguro)
        try:
            db.session.add(nuevo_usuario)
            db.session.commit()
            flash("Registro exitoso. Inicia sesión ahora.", "success")
            return redirect(url_for('login'))
        except Exception:
            flash("El nombre de usuario ingresado ya existe.", "error")
            
    return render_template('registro.html', titulo="Registro")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = Usuario.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('dashboard'))
        else:
            flash("Nombre de usuario o contraseña incorrectos.", "error")
            
    return render_template('login.html', titulo="Iniciar Sesión")

@app.route('/logout')
def logout():
    session.clear()
    flash("Has cerrado tu sesión de forma segura.", "info")
    return redirect(url_for('login'))


# --- RUTA PROTEGIDA (DASHBOARD - CLASE 8 Y 9) ---

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash("Debes iniciar sesión para ingresar a tu panel administrativo.", "warning")
        return redirect(url_for('login'))
        
    usuario_db = Usuario.query.get(session['user_id'])
    ruta_avatar = usuario_db.avatar if usuario_db and usuario_db.avatar else None

    return render_template('dashboard.html', nombre=session['username'], avatar_url=ruta_avatar, titulo="Dashboard")


# --- ENDPOINTS AUXILIARES DE LATENCIA PARA LA CLASE 8 ---

@app.route('/api/reservas', methods=['GET'])
def api_obtener_reservas():
    if 'user_id' not in session:
        return jsonify({"error": "No autorizado"}), 403
        
    # Agregamos latencia artificial de 2 segundos para ver el Skeleton Screen
    time.sleep(2)
    
    if 'mock_reservas' not in session:
        session['mock_reservas'] = []
    return jsonify(session['mock_reservas'])

@app.route('/api/reservas/crear', methods=['POST'])
def api_crear_reserva():
    if 'user_id' not in session:
        return jsonify({"error": "No autorizado"}), 403
        
    time.sleep(1.5)
    import random
    servicios = ["Mentoría Python Avanzado 🐍", "Taller de Despliegue Flask 🚀", "Asesoría UI/UX Avanzada 🎨"]
    id_ticket = f"TKT-2026-{random.randint(10, 99)}"
    
    nueva_reserva = {
        "id": id_ticket,
        "servicio": random.choice(servicios),
        "estado": "Confirmado"
    }
    
    if 'mock_reservas' not in session:
        session['mock_reservas'] = []
        
    reservas = session['mock_reservas']
    reservas.append(nueva_reserva)
    session['mock_reservas'] = reservas
    
    return jsonify(nueva_reserva), 201

@app.route('/api/reservas/limpiar', methods=['POST'])
def api_limpiar_reservas():
    if 'user_id' not in session:
        return jsonify({"error": "No autorizado"}), 403
        
    time.sleep(1)
    session['mock_reservas'] = []
    return jsonify({"status": "success"}), 200


if __name__ == '__main__':
    app.run(debug=True)