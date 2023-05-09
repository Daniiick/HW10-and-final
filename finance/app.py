import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

import requests, json

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("SELECT * FROM users WHERE id=?", session.get("user_id"))
    username = rows[0]["username"]
    cash = rows[0]["cash"]

    rows = db.execute("SELECT * FROM transactions WHERE id=?", session.get("user_id"))
    res ={}
    for row in rows:
        try:
            res[row["symbol"]] += row["shares"]
        except KeyError:
            res[row["symbol"]] = row["shares"]

    networth = 0
    items = [
                {
                    'symbol': "Symbol",
                    'shares': "Shares",
                    'price': "Current Price",
                    'total': "Position Total"
                }
            ]
    for key, value in res.items():
        if value == 0:
            continue
        cur_price = lookup(key)["price"]
        an_item  = dict(symbol=key, shares=value, price=cur_price, total=value * cur_price)
        networth += value * cur_price
        items.append(an_item)
    networth += cash

    return render_template("index.html", username=username, cash=cash, items=items, networth=networth)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        share_data = lookup(symbol)
        if share_data is None:
            return apology("No such symbol exists")
        try:
            shares_int = int(shares)
            if shares_int <= 0:
                return apology("Number of shares should be greater than 0")
        except ValueError:
            return apology("Invalid number of shares")

        rows_cash = db.execute("SELECT cash FROM users WHERE id=?", session.get("user_id"))
        if rows_cash[0]["cash"] > shares_int * share_data["price"]:
            amount = shares_int * share_data["price"]
            new_amount = rows_cash[0]["cash"] - amount
            db.execute("UPDATE users SET cash=? WHERE id=?", new_amount, session.get("user_id"))

            db.execute("INSERT INTO transactions (user_id, symbol, shares, buy_price) VALUES (?, ?, ?, ?)", session.get("user_id"), symbol, shares_int, share_data["price"])

            flash(f"You have successfully bought {shares_int} shares of {share_data['name']}!")
            return redirect ("/")
        else:
            return apology("No sufficient funds")

    else:
       return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    username = db.execute("SELECT * FROM users WHERE id=?", session.get("user_id"))[0]["username"]
    rows = db.execute("SELECT * FROM transactions WHERE user_id=?", session.get("user_id"))
    items = [
                {
                    'sign': "Sign",
                    'symbol': "Symbol",
                    'shares': "Shares",
                    'buy_price': "Buy/Sell Price",
                    'date': "Date"
                }
            ]
    for row in rows:
        row["sign"] = '+' if row["shares"] > 0 else '-'
        items.append(row)

    return render_template("history.html", username=username, items=items)
# Have tried to make "add cash" route, but was not succesful =(
# @app.route("/add_cash")
# @login_required
# def add_cash():
#    """Allows user to add cash"""
#    if request.method == "POST":
#        return render_template("add.html")
#    else:
#        added_cash == int(request.form.get("added_cash"))
#
#        if not added_cash:
#            return apology("Add some money!")

#    cur_cash = db.execute("SELECT cash FROM users WHERE id=?", session.get("user_id"))[0]["cash"]
#        upd_cash = cur_cash + added_cash
#        db.execute("UPDATE users SET cash=? WHERE id=?", upd_cash, session.get("user_id"))

#    return redirect("/")


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
        session["username"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":
        dr = lookup(request.form.get("symbol"))
        return render_template("quoted.html", symbol=dr["symbol"], price=dr["price"])

    else:
        return render_template("quote.html")

    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""


    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

         # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if len(rows) > 0:
            return apology("username already exists", 403)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 403)

        if request.form.get("password") != request.form.get("password_confirmation"):
            return apology("password was not confirmed", 403)

        hashed_password = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO users ('username', 'hash') VALUES (?, ?)", request.form.get("username"), hashed_password)

        # Redirect user to home page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    symbols =[]
    rows = db.execute("SELECT * FROM transactions WHERE id=?", session.get("user_id"))
    res ={}
    for row in rows:
        try:
            res[row["symbol"]] += row["shares"]
        except KeyError:
            res[row["symbol"]] = row["shares"]
    for key, value in res.items():
        if value != 0:
            symbols.append(key)


    if request.method == "POST":
        shares = request.form.get("shares")
        symbol = request.form.get("symbols")
        if not symbol or res[symbol] <= 0:
            return apology("no symbol chosen or cannot sell this symbol")

        try:
            shares_int = int(shares)
            if shares_int <= 0:
                return apology("Number of shares should be greater than 0")
        except ValueError:
            return apology("Invalid number of shares")

        if res[symbol] < shares_int:
            return apology("You do not have this much shares")

        cur_price = lookup(symbol)["price"]
        db.execute("INSERT INTO transactions (user_id, symbol, shares, buy_price) values (?, ?, ?, ?)", session.get("user_id"), symbol, shares_int * (-1), cur_price)

        old_cash = db.execute("SELECT cash FROM users WHERE id=?", session.get("user_id"))[0]["cash"]
        new_cash = old_cash + shares_int * cur_price
        db.execute("UPDATE users SET cash=? WHERE id=?", new_cash, session.get("user_id"))


        return redirect("/")

    else:
        return render_template("sell.html", symbols=symbols)
