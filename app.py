import oracledb
from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this to a random secret key

# Database connection details
username = 'dbbook'
password = 'password'
dsn = '192.168.9.176/xepdb1'


def get_db_connection():
    return oracledb.connect(user=username, password=password, dsn=dsn)


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ptal = request.form['ptal']
        pwd = request.form['password']
        if pwd == 'password':
            if ptal == 'admin':
                session['ptal'] = 'admin'
                return redirect(url_for('dashboard'))
            else:
                # Check if ptal exists
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT ptal FROM personur WHERE UPPER(ptal) = UPPER(:ptal)", {'ptal': ptal})
                user = cursor.fetchone()
                cursor.close()
                conn.close()

                if user:
                    session['ptal'] = user[0]  # Use the actual ptal from DB
                    return redirect(url_for('dashboard'))
                else:
                    flash('Ógyldugt P-tal')
                    return redirect(url_for('login'))
        else:
            flash('Ógyldugt loyniorð')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    # Get accounts
    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        # Admin sees all accounts
        cursor.execute("""
            SELECT k.kontonr, k.konto_slag, k.saldo, p.fornavn, p.eftirnavn
            FROM konto k
            JOIN kundi ku ON k.kundi_id = ku.kundi_id
            JOIN personur p ON ku.ptal = p.ptal
        """)
        accounts = cursor.fetchall()
    else:
        # Regular user: family accounts
        # Find family id
        cursor.execute("""
            SELECT f.familju_id
            FROM familju_limir fl
            JOIN familja f ON fl.familju_id = f.familju_id
            WHERE fl.ptal = :ptal
        """, {'ptal': ptal})
        family = cursor.fetchone()

        accounts = []
        if family:
            familju_id = family[0]
            # Get all family members' ptal
            cursor.execute("SELECT ptal FROM familju_limir WHERE familju_id = :fid", {
                           'fid': familju_id})
            members = cursor.fetchall()
            ptals = [m[0] for m in members]

            # Get their kundi_id
            if ptals:
                placeholders = ','.join([':' + str(i)
                                        for i in range(len(ptals))])
                params = {str(i): p for i, p in enumerate(ptals)}
                cursor.execute(
                    f"SELECT kundi_id FROM kundi WHERE ptal IN ({placeholders})", params)
                kundis = cursor.fetchall()
                kundi_ids = [k[0] for k in kundis]

                if kundi_ids:
                    placeholders = ','.join([':' + str(i)
                                            for i in range(len(kundi_ids))])
                    params = {str(i): k for i, k in enumerate(kundi_ids)}
                    cursor.execute(f"""
                        SELECT k.kontonr, k.konto_slag, k.saldo, p.fornavn, p.eftirnavn
                        FROM konto k
                        JOIN kundi ku ON k.kundi_id = ku.kundi_id
                        JOIN personur p ON ku.ptal = p.ptal
                        WHERE k.kundi_id IN ({placeholders})
                    """, params)
                    accounts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('dashboard.html', accounts=accounts, is_admin=is_admin)


@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        kontonr = request.form['kontonr']
        tekst = request.form['tekst']
        upphaedd = float(request.form['upphaedd'])
        slag = request.form['slag']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get next bokingar_id
        cursor.execute("SELECT NVL(MAX(bokingar_id), 0) + 1 FROM boking")
        boking_id = cursor.fetchone()[0]

        # Insert boking
        cursor.execute("""
            INSERT INTO boking (bokingar_id, kontonr, bokingar_tekst, dato, upphaedd, bokingar_slag, leypandi_saldo)
            VALUES (:id, :kontonr, :tekst, SYSDATE, :upphaedd, :slag, 0)
        """, {'id': boking_id, 'kontonr': kontonr, 'tekst': tekst, 'upphaedd': upphaedd, 'slag': slag})

        # Update saldo (simple, assuming positive for deposit, negative for withdrawal)
        if slag == 'Deposit':
            cursor.execute("UPDATE konto SET saldo = saldo + :amt WHERE kontonr = :kontonr",
                           {'amt': upphaedd, 'kontonr': kontonr})
        elif slag == 'Withdrawal':
            cursor.execute("UPDATE konto SET saldo = saldo - :amt WHERE kontonr = :kontonr",
                           {'amt': upphaedd, 'kontonr': kontonr})

        conn.commit()
        cursor.close()
        conn.close()

        flash('Færslu lagt afturat')
        return redirect(url_for('dashboard'))

    return render_template('add_transaction.html')


@app.route('/gen_ptal', methods=['GET', 'POST'])
def gen_ptal():
    if 'ptal' not in session or session['ptal'] != 'admin':
        return redirect(url_for('login'))

    generated_ptal = None
    if request.method == 'POST':
        fodidato_str = request.form['fodidato']  # YYYY-MM-DD
        try:
            fodidato = datetime.strptime(fodidato_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Ógyldigur dato format')
            return redirect(url_for('gen_ptal'))

        conn = get_db_connection()
        cursor = conn.cursor()
        # Call the function
        generated_ptal = cursor.callfunc('ptal_gen', str, [fodidato])
        cursor.close()
        conn.close()

    return render_template('gen_ptal.html', generated_ptal=generated_ptal)


@app.route('/add_account', methods=['GET', 'POST'])
def add_account():
    if 'ptal' not in session or session['ptal'] != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        ptal = request.form['ptal']
        konto_slag = request.form['konto_slag']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get kundi_id for ptal
        cursor.execute(
            "SELECT kundi_id FROM kundi WHERE ptal = :ptal", {'ptal': ptal})
        kundi = cursor.fetchone()
        if not kundi:
            flash('Kundi ikki funnin')
            cursor.close()
            conn.close()
            return redirect(url_for('add_account'))

        kundi_id = kundi[0]

        # Insert into konto (trigger will generate kontonr)
        cursor.execute("INSERT INTO konto (konto_slag, kundi_id, saldo) VALUES (:slag, :kid, 0)",
                       {'slag': konto_slag, 'kid': kundi_id})

        conn.commit()
        cursor.close()
        conn.close()

        flash('Konto lagt afturat')

    return render_template('add_account.html')


@app.route('/add_transfer', methods=['GET', 'POST'])
def add_transfer():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    if request.method == 'POST':
        kontonr_fra = request.form['kontonr_fra']
        kontonr_til = request.form['kontonr_til']
        upphaedd = float(request.form['upphaedd'])
        mottakara_tekst = request.form['mottakara_tekst']
        egin_tekst = request.form['egin_tekst']

        if kontonr_fra == kontonr_til:
            flash('Kann ikki flyta til sama konto')
            return redirect(url_for('add_transfer'))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if accounts exist and get current saldos
        cursor.execute("SELECT saldo FROM konto WHERE kontonr = :k", {
                       'k': kontonr_fra})
        saldo_fra = cursor.fetchone()
        cursor.execute("SELECT saldo FROM konto WHERE kontonr = :k", {
                       'k': kontonr_til})
        saldo_til = cursor.fetchone()

        if not saldo_fra or not saldo_til:
            flash('Ógyldugt konto')
            cursor.close()
            conn.close()
            return redirect(url_for('add_transfer'))

        if saldo_fra[0] < upphaedd:
            flash('Ikki nóg pengar')
            conn.close()
            return redirect(url_for('add_transfer'))

        # Get next kladda_id
        cursor.execute("SELECT NVL(MAX(kladda_id), 0) + 1 FROM kladda")
        kladda_id = cursor.fetchone()[0]

        # Insert into kladda
        cursor.execute("""
            INSERT INTO kladda (kladda_id, kontonr_fra, kontonr_til, mottakara_tekst, egin_tekst, dato, saldo_fra, saldo_til, upphaedd)
            VALUES (:id, :fra, :til, :mtekst, :etekt, SYSDATE, :sfra, :stil, :amt)
        """, {'id': kladda_id, 'fra': kontonr_fra, 'til': kontonr_til, 'mtekst': mottakara_tekst, 'etekt': egin_tekst, 'sfra': saldo_fra[0], 'stil': saldo_til[0], 'amt': upphaedd})

        # Update saldos
        cursor.execute("UPDATE konto SET saldo = saldo - :amt WHERE kontonr = :k",
                       {'amt': upphaedd, 'k': kontonr_fra})
        cursor.execute("UPDATE konto SET saldo = saldo + :amt WHERE kontonr = :k",
                       {'amt': upphaedd, 'k': kontonr_til})

        conn.commit()
        cursor.close()
        conn.close()

        flash('Flyting liðug')
        return redirect(url_for('dashboard'))

    # Get available accounts for the user
    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        cursor.execute("SELECT kontonr FROM konto")
    else:
        # Family accounts
        cursor.execute("""
            SELECT f.familju_id
            FROM familju_limir fl
            JOIN familja f ON fl.familju_id = f.familju_id
            WHERE fl.ptal = :ptal
        """, {'ptal': ptal})
        family = cursor.fetchone()

        if family:
            familju_id = family[0]
            cursor.execute("""
                SELECT DISTINCT k.kontonr
                FROM konto k
                JOIN kundi ku ON k.kundi_id = ku.kundi_id
                JOIN familju_limir fl ON ku.ptal = fl.ptal
                WHERE fl.familju_id = :fid
            """, {'fid': familju_id})
        else:
            accounts = []

    accounts = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()

    return render_template('add_transfer.html', accounts=accounts, is_admin=is_admin)


@app.route('/add_person', methods=['GET', 'POST'])
def add_person():
    if 'ptal' not in session or session['ptal'] != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        fornavn = request.form['fornavn']
        eftirnavn = request.form['eftirnavn']
        fodidato_str = request.form['fodidato']
        postkoda = int(request.form['postkoda'])
        adressa = request.form['adressa']
        kyn = request.form['kyn']

        try:
            fodidato = datetime.strptime(fodidato_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Ógyldigur føðidagur')
            return redirect(url_for('add_person'))

        conn = get_db_connection()
        cursor = conn.cursor()

        # Generate ptal
        ptal = cursor.callfunc('ptal_gen', str, [fodidato])

        # Insert into personur
        cursor.execute("""
            INSERT INTO personur (ptal, postkoda, fornavn, eftirnavn, adressa, fodidato, kyn)
            VALUES (:ptal, :postkoda, :fornavn, :eftirnavn, :adressa, :fodidato, :kyn)
        """, {'ptal': ptal, 'postkoda': postkoda, 'fornavn': fornavn, 'eftirnavn': eftirnavn, 'adressa': adressa, 'fodidato': fodidato, 'kyn': kyn})

        conn.commit()
        cursor.close()
        conn.close()

        flash(f'Persónur lagt afturat við P-tal: {ptal}')
        return redirect(url_for('dashboard'))

    # Get postkoda list
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT postkoda, byur FROM postkoda ORDER BY postkoda")
    postkodas = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('add_person.html', postkodas=postkodas)


if __name__ == '__main__':
    app.run(debug=True)


@app.route('/logout')
def logout():
    session.clear()  # removes user session
    return redirect(url_for('login'))
