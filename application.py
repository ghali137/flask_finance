import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/", methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        amount = int(request.form.get('amount'))
        
        if not amount or amount < 0:
            return apology("you didn't type a number")
        else:
            db.execute('UPDATE users SET cash = (SELECT cash FROM users WHERE id = ?) + ? WHERE id = ?',
                        session['user_id'], amount, session['user_id'])
        return redirect('/')
    else:
        stock_db = db.execute('SELECT * FROM purchases WHERE id = ? AND shares > 0', session['user_id'])
        cash = db.execute('SELECT cash FROM users WHERE id = ?', session['user_id'])
        hold_value = 0
        for row in stock_db:
            stock = lookup(row['symbol'])
            row['price'] = stock['price']
            hold_value += stock['price'] * row['shares']
        return render_template('index.html', stock_db=stock_db, cash=cash[0]['cash'], hold_value=hold_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == 'GET':
        return render_template('buy.html')

    else:
        stock = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")
        
        if not stock:
            return apology("The stock symbol doesn't exist")
        elif not shares:
            return apology("Your shares number is not a positive integer")
        elif not shares.isdigit() or int(shares) < 1:
            return apology("Your shares number is not a positive integer")
        
        price = stock['price']
        symbol = stock['symbol']

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
        cash = cash[0]['cash']

        if cash < price * int(shares):
            return apology('You do not have enough money')

        if db.execute("SELECT symbol FROM purchases WHERE id = ? AND symbol = ?", session['user_id'], symbol):
            db.execute('UPDATE purchases SET shares = (SELECT shares FROM purchases WHERE id = ? AND symbol = ?) + ? WHERE id = ? AND symbol = ?', 
                        session['user_id'], symbol, int(shares), session['user_id'], symbol)
        else:
            db.execute('INSERT INTO purchases (shares, symbol, id) values(?, ?, ?)', int(shares), symbol, session['user_id'])
        db.execute('UPDATE users SET cash = ? WHERE id = ?', cash - price * int(shares), session['user_id'])
        now = datetime.datetime.now()
        db.execute('INSERT INTO history (id, shares, price, symbol, type, date, time) values(?, ?, ?, ?, "Bought", ?, ?)',
                    session['user_id'], int(shares), price * int(shares), symbol, datetime.date.today(), now.strftime("%H:%M:%S"))
        return redirect('/')


@app.route("/history")
@login_required
def history():
    stock_db = db.execute('SELECT * FROM history WHERE id = ?', session['user_id'])
    return render_template('history.html', stock_db=stock_db)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == 'GET':
        return render_template('quote.html')
    else:
        data = lookup(request.form.get("symbol"))
        if not data:
            return apology("The stock symbol doesn't exist")
        else:
            return render_template('quoted.html', data=data)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        
        if not username:
            return apology("You haven't typed your username or it already exists, try again")

        duplicate = db.execute("SELECT username FROM users WHERE username=?", username)
        if not len(duplicate) == 0:
            return apology("You haven't typed your username or it already exists, try again")
       
        elif not password:
            return apology("You haven't typed your password, try again")

        elif not password == confirmation:
            return apology("Your password and confirmation do not match")

        db.execute("INSERT INTO users (username, hash) values (?, ?)", username, generate_password_hash(password, 'sha256'))


        return redirect('/')

    if request.method == "GET":
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == 'GET':
        
        symbols = db.execute('SELECT symbol FROM purchases WHERE id = ? AND shares > 0', session['user_id'])
        
        return render_template('sell.html', symbols=symbols)

    else:
        stock = lookup(request.form.get("symbol"))
        shares = request.form.get("shares")
       
        if not stock:
            return apology("The stock symbol doesn't exist")
        elif not shares or not shares.isdigit() or int(shares) < 1:
            return apology("Your shares number is not a positive integer")
        
        price = stock['price']
        symbol = stock['symbol']

        cash = db.execute("SELECT cash FROM users WHERE id = ?", session['user_id'])
        cash = cash[0]['cash']

        db_shares = db.execute("SELECT shares FROM purchases WHERE id = ? AND symbol = ?", session['user_id'], symbol)

        if db_shares and db_shares[0]['shares'] - int(shares) >= 0:
            db.execute('UPDATE purchases SET shares = (SELECT shares FROM purchases WHERE id = ? AND symbol = ?) - ? WHERE id = ? AND symbol = ?', 
                        session['user_id'], symbol, int(shares), session['user_id'], symbol)
        else:
            return apology('Too much')

        db.execute('UPDATE users SET cash = ? WHERE id = ?', cash + price * int(shares), session['user_id'])
        now = datetime.datetime.now()
        db.execute('INSERT INTO history (id, shares, price, symbol, type, date, time) values(?, ?, ?, ?, "Sold", ?, ?)', 
                    session['user_id'], int(shares), price * int(shares), symbol, datetime.date.today(), now.strftime("%H:%M:%S"))
        return redirect('/')


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
