import os
import json
import secrets
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import stripe

load_dotenv()
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
DOMAIN_URL = os.getenv("DOMAIN_URL")

ACCOUNTS_FILE = 'accounts.json'

PRODUCTS = {
    'coins100': {'name': '100 монет', 'amount': 100, 'price': 100},
    'coins1000': {'name': '1 000 монет', 'amount': 1000, 'price': 900},
    'coins10000': {'name': '10 000 монет', 'amount': 10000, 'price': 7000},
    'auto10': {'name': '10 автокліків', 'amount': 0, 'price': 50},
    'auto100': {'name': '100 автокліків', 'amount': 0, 'price': 400},
    'auto1000': {'name': '1 000 автокліків', 'amount': 0, 'price': 2500},
}

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return {}
    with open(ACCOUNTS_FILE, 'r') as f:
        return json.load(f)

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=2)

@app.route('/')
def index():
    user = session.get("user")
    coins = 0
    autoclick = 0

    if user:
        path = f"user_data/{user}.json"
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                coins = data.get("coins", 0)
                autoclick = data.get("autoclick", 0)

    return render_template("index.html", user=user, coins=coins, autoclick=autoclick)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        accounts = load_accounts()

        if username in accounts:
            return render_template('register.html', error='Користувач уже існує')

        token = secrets.token_hex(16)
        accounts[username] = {
            "password": generate_password_hash(password),
            "token": token,
            "coins": 0,
            "autoclick": 0
        }
        save_accounts(accounts)

        os.makedirs("user_data", exist_ok=True)
        with open(f"user_data/{username}.json", "w") as f:
            json.dump({"coins": 0, "autoclick": 0}, f)

        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        accounts = load_accounts()

        if username in accounts and check_password_hash(accounts[username]["password"], password):
            session['user'] = username
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Невірний логін або пароль')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route("/download")
def download_page():
    return render_template("download.html")

@app.route("/profile")
def profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = session['user']
    accounts = load_accounts()
    user_data = accounts.get(user)
    token = user_data.get('token') if user_data else "Токен не знайдено"
    return render_template('profile.html', user=user, token=token)

@app.route("/shop")
def shop():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template("shop.html", products=PRODUCTS, key=PUBLISHABLE_KEY)

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    product_id = request.form.get("product_id")
    prod = PRODUCTS.get(product_id)
    if not prod:
        return "Unknown product", 400

    session['buy'] = product_id

    checkout = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {"name": prod['name']},
                "unit_amount": prod['price'],
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=DOMAIN_URL + "/success",
        cancel_url=DOMAIN_URL + "/cancel",
    )
    return redirect(checkout.url)

@app.route("/success")
def success():
    user = session.get('user')
    pid = session.pop('buy', None)
    if user and pid:
        path = f"user_data/{user}.json"
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
        else:
            data = {"coins": 0, "autoclick": 0}

        prod = PRODUCTS[pid]
        if pid.startswith('coins'):
            data['coins'] += prod['amount']
        elif pid.startswith('auto'):
            if pid == 'auto10': data['autoclick'] += 10
            if pid == 'auto100': data['autoclick'] += 100
            if pid == 'auto1000': data['autoclick'] += 1000

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    return render_template("success.html")

@app.route("/cancel")
def cancel():
    return render_template("cancel.html")

# Disable caching for static files
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.context_processor
def override_url_for():
    def dated_url_for(endpoint, **values):
        if endpoint == 'static':
            filename = values.get('filename', None)
            if filename:
                file_path = os.path.join(app.root_path, 'static', filename)
                if os.path.exists(file_path):
                    values['v'] = int(os.path.getmtime(file_path))
        return url_for(endpoint, **values)
    return dict(url_for=dated_url_for)

if __name__ == '__main__':
    app.run(debug=True)
