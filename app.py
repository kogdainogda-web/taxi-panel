from flask import Flask, render_template, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "12345"

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payer_name = db.Column(db.String(100))
    model = db.Column(db.String(100))
    plate_number = db.Column(db.String(20))
    tech_end_date = db.Column(db.String(20))
    osgo_end_date = db.Column(db.String(20))
    paid = db.Column(db.Boolean, default=False)
    paid_month = db.Column(db.String(7), default="")


class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    payment_day = db.Column(db.Integer)
    paid = db.Column(db.Boolean, default=False)

# ---------------- HELPERS ----------------

def current_month():
    return date.today().strftime("%Y-%m")

def get_status(end_date_str):
    try:
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        today = date.today()
        days_left = (end_date - today).days

        if days_left < 0:
            return "red", "❌ Просрочено"
        elif days_left <= 14:
            return "yellow", f"⏳ Осталось {days_left} дн."
        else:
            return "green", f"✅ {days_left} дн."

    except:
        return "gray", "—"

# ---------------- AUTH ----------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['password'] == "0091":
            session['auth'] = True
            return redirect('/dashboard')

    return '''
        <form method="post">
            <input name="password" type="password" placeholder="Пароль">
            <button>Войти</button>
        </form>
    '''


def auth_required():
    if not session.get('auth'):
        return redirect('/login')

# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return redirect('/dashboard')


@app.route('/dashboard')
def dashboard():
    if not session.get('auth'):
        return redirect('/login')

    vehicles = Vehicle.query.all()

    today = date.today()
    expiring = 0
    overdue = 0
    unpaid = 0

    for v in vehicles:
        try:
            tech = datetime.strptime(v.tech_end_date, "%Y-%m-%d").date()
            osgo = datetime.strptime(v.osgo_end_date, "%Y-%m-%d").date()

            if (tech - today).days < 0 or (osgo - today).days < 0:
                overdue += 1
            elif (tech - today).days <= 14 or (osgo - today).days <= 14:
                expiring += 1

            if not v.paid:
                unpaid += 1
        except:
            pass

    return render_template("dashboard.html",
                           total=len(vehicles),
                           expiring=expiring,
                           overdue=overdue,
                           unpaid=unpaid)


@app.route('/vehicles', methods=['GET', 'POST'])
def vehicles():
    if not session.get('auth'):
        return redirect('/login')

    if request.method == 'POST':
        v = Vehicle(
            payer_name=request.form['payer_name'],
            model=request.form['model'],
            plate_number=request.form['plate_number'],
            tech_end_date=request.form['tech_end_date'],
            osgo_end_date=request.form['osgo_end_date'],
            paid_month=current_month()
        )
        db.session.add(v)
        db.session.commit()
        return redirect('/vehicles')

    # --- SEARCH / FILTER ---
    search = request.args.get('search', '')
    paid_filter = request.args.get('paid', '')

    query = Vehicle.query

    if search:
        query = query.filter(
            (Vehicle.plate_number.contains(search)) |
            (Vehicle.payer_name.contains(search))
        )

    if paid_filter == "paid":
        query = query.filter_by(paid=True)
    elif paid_filter == "unpaid":
        query = query.filter_by(paid=False)

    data = query.all()

    return render_template('vehicles.html', vehicles=data, get_status=get_status)
@app.route('/edit_vehicle/<int:id>', methods=['GET', 'POST'])
def edit_vehicle(id):
    if not session.get('auth'):
        return redirect('/login')

    v = Vehicle.query.get_or_404(id)

    if request.method == 'POST':
        v.payer_name = request.form['payer_name']
        v.model = request.form['model']
        v.plate_number = request.form['plate_number']
        v.tech_end_date = request.form['tech_end_date']
        v.osgo_end_date = request.form['osgo_end_date']

        db.session.commit()
        return redirect('/vehicles')

    return render_template('edit_vehicle.html', v=v)


@app.route('/drivers', methods=['GET', 'POST'])
def drivers():
    if not session.get('auth'):
        return redirect('/login')

    if request.method == 'POST':
        d = Driver(
            full_name=request.form['full_name'],
            payment_day=int(request.form['payment_day'])
        )
        db.session.add(d)
        db.session.commit()
        return redirect('/drivers')

    data = Driver.query.all()
    return render_template('drivers.html', drivers=data)


@app.route('/toggle_vehicle/<int:id>')
def toggle_vehicle(id):
    v = Vehicle.query.get(id)
    v.paid = not v.paid
    db.session.commit()
    return redirect('/vehicles')


@app.route('/toggle_driver/<int:id>')
def toggle_driver(id):
    d = Driver.query.get(id)
    d.paid = not d.paid
    db.session.commit()
    return redirect('/drivers')

# ---------------- AUTO RESET (ONLY VEHICLES) ----------------

def reset_vehicle_payments():
    with app.app_context():
        month = current_month()
        vehicles = Vehicle.query.all()

        for v in vehicles:
            if v.paid_month != month:
                v.paid = False
                v.paid_month = month

        db.session.commit()


# ---------------- START SCHEDULER ----------------

scheduler = BackgroundScheduler()
scheduler.add_job(reset_vehicle_payments, 'cron', day=1, hour=0)
scheduler.start()

# ---------------- START APP ----------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    app.run(debug=True)