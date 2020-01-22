import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
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


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    array = {}
    stocks = db.execute(
        "SELECT symbol, SUM(shares) as sumofshares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING sumofshares > 0", user_id=session["user_id"])
    users = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])
    remaining_cash = users[0]["cash"]
    total = remaining_cash
    for stock in stocks:
        array[stock["symbol"]] = lookup(stock["symbol"])
        total += lookup(stock["symbol"])["price"] * stock["sumofshares"]

    return render_template("index.html", array=array, stocks=stocks, remaining_cash=remaining_cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("Invalid Symbol")

        shares = int(request.form.get("shares"))
        if shares < 1:
            return apology("Shares must be a positive non-zero integer")

        money = db.execute("SELECT cash FROM users WHERE id = :id",
                            id=session["user_id"])
        price_of_shares = stock["price"] * shares

        if float(money[0]["cash"]) < price_of_shares:
            return apology("Not enough funds")

        db.execute("UPDATE users SET cash = cash - :cost WHERE id = :id",
                    id=session["user_id"],
                    cost=price_of_shares)

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES(:user_id, :symbol, :shares, :price)",
                   user_id=session["user_id"],
                   symbol=stock["symbol"],
                   shares=shares,
                   price=stock["price"])

        return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    transactions = db.execute("SELECT symbol, shares, price, executed_at FROM transactions WHERE user_id=:user_id", user_id=session['user_id'])

    return render_template("history.html", transactions=transactions)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
        quoted_company = lookup(request.form.get("symbol"))

        if quoted_company == None:
            return apology("invalid symbol", 400)

        return render_template("quoted.html", quoted_company=quoted_company)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        hashed_password = generate_password_hash(request.form.get("password"))
        new_id = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)",
                            username=request.form.get("username"), hash=hashed_password)
        if not new_id:
            return apology("Username already exist")
        return redirect("/")
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        symbol = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))

        if not shares or shares <= 0:
            return apology("cannot sell 0 or less than 0 shares of shares")

        if not symbol:
            return apology("invalid symbol")

        sum_of_shares = db.execute("SELECT SUM(shares) as summed_shares FROM transactions WHERE user_id=:user_id AND symbol=:symbol;",
                                    user_id=session["user_id"], symbol=symbol["symbol"])
        if not sum_of_shares[0]["summed_shares"]:
            return apology("stock is not in your portfolio")

        if shares > sum_of_shares[0]["summed_shares"]:
            return apology("cannot sell more stocks than you own")

        price_of_shares = shares*symbol["price"]
        db.execute("UPDATE users SET cash = cash + :price_of_shares WHERE id = :user_id;", price_of_shares=price_of_shares,
                     user_id=session["user_id"])

        db.execute("INSERT INTO transactions (user_id, symbol, shares, price) VALUES (:user_id, :symbol, :shares, :price);",
                    user_id=session["user_id"], symbol=symbol["symbol"], shares=-shares, price=symbol["price"])

        return redirect("/")

    else:
        return render_template("sell.html")


@app.route("/addfunds", methods=["GET", "POST"])
@login_required
def funding():
    if request.method == "POST":
        quantity = float(request.form.get("quantity"))
        if quantity <= 0:
            return apology("quantity must be a positive non-zero real number")

        db.execute("UPDATE users SET cash = cash + :quantity WHERE id = :user_id", quantity=quantity, user_id=session["user_id"])

        return redirect("/")
    else:
        return render_template("funding.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
