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
            if ptal == 'banki':
                session['ptal'] = 'admin'
                return redirect(url_for('dashboard'))
            else:
                # Check if ptal exists
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "select ptal from personur where ptal = :ptal", {'ptal': ptal})
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
            select * from banki_view
        """)
        accounts = cursor.fetchall()
    else:
        cursor.execute(
            """
            select 1
            from familju_limir
            where ptal = :ptal and upper(familju_rolla) = 'BARN'
            fetch first 1 row only
            """,
            {'ptal': ptal}
        )
        is_child = cursor.fetchone() is not None

        if is_child:
            cursor.execute(
                """
                select kontonr, konto_slag, saldo, familju_rolla, fornavn
                from barn_view
                where ptal = :ptal
                """,
                {'ptal': ptal}
            )
        else:
            cursor.execute(
                "select kontonr, konto_slag, saldo, familju_rolla, fornøvn from Familju_view where brúkari = :ptal",
                {'ptal': ptal}
            )
        accounts = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('dashboard.html', accounts=accounts, is_admin=is_admin)


@app.route('/seinasti_manin')
def seinasti_manin():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        cursor.execute("SELECT kontonr FROM konto ORDER BY kontonr")
    else:
        cursor.execute(
            """
            SELECT k.kontonr
            FROM konto k
            JOIN kundi ku ON k.kundi_id = ku.kundi_id
            WHERE ku.ptal = :ptal
            ORDER BY k.kontonr
            """,
            {'ptal': ptal}
        )

    allowed_accounts = [row[0] for row in cursor.fetchall()]
    selected_kontonr = request.args.get('kontonr')

    if not selected_kontonr and allowed_accounts:
        selected_kontonr = allowed_accounts[0]

    rows = []
    if selected_kontonr:
        if selected_kontonr not in allowed_accounts:
            flash('Konto hoyrir ikki til teg')
            cursor.close()
            conn.close()
            return redirect(url_for('seinasti_manin'))

        cursor.execute(
            "select * from seinasti_manin_yvirlit where kontonr = :kontonr",
            {'kontonr': selected_kontonr}
        )
        rows = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        'seinasti_manin.html',
        accounts=allowed_accounts,
        selected_kontonr=selected_kontonr,
        rows=rows,
    )


@app.route('/add_transaction', methods=['GET', 'POST'])
def add_transaction():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        cursor.execute("select kontonr from konto order by kontonr")
    else:
        cursor.execute("""
            select k.kontonr
            from konto k
        join kundi ku on k.kundi_id = ku.kundi_id
            where ku.ptal = :ptal
            order by k.kontonr
        """, {'ptal': ptal})
    accounts = [row[0] for row in cursor.fetchall()]

    if request.method == 'POST':
        kontonr = request.form['kontonr']
        tekst = request.form['tekst']
        upphaedd = float(request.form['upphaedd'])
        slag = request.form['slag']

        if kontonr not in accounts:
            flash('Konto hoyrir ikki til teg')
            cursor.close()
            conn.close()
            return redirect(url_for('add_transaction'))

        if slag == 'Deposit':
            signed_upphaedd = upphaedd
        elif slag == 'Withdrawal':
            signed_upphaedd = -upphaedd
        else:
            flash('Ógyldugt slag')
            cursor.close()
            conn.close()
            return redirect(url_for('add_transaction'))

        # The trigger sets bokingar_id, dato, leypandi_saldo, and updates konto.saldo.
        cursor.execute("""
            INSERT INTO boking (kontonr, bokingar_tekst, upphaedd, bokingar_slag)
            VALUES (:kontonr, :tekst, :upphaedd, :slag)
        """, {'kontonr': kontonr, 'tekst': tekst, 'upphaedd': signed_upphaedd, 'slag': slag})

        conn.commit()
        cursor.close()
        conn.close()

        flash('Gerð framd')
        return redirect(url_for('dashboard'))

    cursor.close()
    conn.close()

    return render_template('add_transaction.html', accounts=accounts)


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
            flash('Ógyldigt dato format')
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

        flash('Konta stovnað')

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

        try:
            kontonr_fra_num = int(kontonr_fra)
            kontonr_til_num = int(kontonr_til)
        except ValueError:
            flash('Ógyldig konto')
            return redirect(url_for('add_transfer'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if not is_admin:
                cursor.execute("""
                    SELECT 1
                    FROM konto k
                    JOIN kundi ku ON k.kundi_id = ku.kundi_id
                    WHERE k.kontonr = :kontonr AND ku.ptal = :ptal
                """, {'kontonr': kontonr_fra_num, 'ptal': ptal})
                owns_from_account = cursor.fetchone()
                if not owns_from_account:
                    flash('Frá konto hoyrir ikki til teg')
                    return redirect(url_for('add_transfer'))

            cursor.callproc('KladdaFlyting', [
                kontonr_fra_num,
                kontonr_til_num,
                upphaedd,
                mottakara_tekst,
                egin_tekst,
            ])
            conn.commit()
        except oracledb.DatabaseError as exc:
            conn.rollback()
            error = exc.args[0]
            code = getattr(error, 'code', None)
            if code == 20001:
                flash('Ikki nóg pengar')
            elif code == 20002:
                flash('Upphædd má vera størri enn 0')
            elif code == 20003:
                flash('Kann ikki flyta til sama konto')
            elif code == 1403:
                flash('Ógyldig konto')
            else:
                flash(getattr(error, 'message', str(exc)))
            return redirect(url_for('add_transfer'))
        finally:
            cursor.close()
            conn.close()

        flash('Flyting framd')
        return redirect(url_for('dashboard'))

    # Get available accounts for dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        cursor.execute("SELECT kontonr FROM konto ORDER BY kontonr")
        from_accounts = [row[0] for row in cursor.fetchall()]
    else:
        # From-account: only accounts owned by signed-in user
        cursor.execute("""
            SELECT k.kontonr
            FROM konto k
            JOIN kundi ku ON k.kundi_id = ku.kundi_id
            WHERE ku.ptal = :ptal
            ORDER BY k.kontonr
        """, {'ptal': ptal})
        from_accounts = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return render_template('add_transfer.html', from_accounts=from_accounts, is_admin=is_admin)


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
            flash('Ógyldugt føðidato')
            return redirect(url_for('add_person'))

        conn = get_db_connection()
        cursor = conn.cursor()

        ptal = cursor.callfunc('ptal_gen', str, [fodidato])

        cursor.execute(
            """
            INSERT INTO personur (ptal, postkoda, fornavn, eftirnavn, adressa, fodidato, kyn)
            VALUES (:ptal, :postkoda, :fornavn, :eftirnavn, :adressa, :fodidato, :kyn)
            """,
            {
                'ptal': ptal,
                'postkoda': postkoda,
                'fornavn': fornavn,
                'eftirnavn': eftirnavn,
                'adressa': adressa,
                'fodidato': fodidato,
                'kyn': kyn,
            },
        )

        conn.commit()
        cursor.close()
        conn.close()

        flash(f'Personur lagdur afturat vid P-tal: {ptal}')
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT postkoda, byur FROM postkoda ORDER BY postkoda")
    postkodas = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('add_person.html', postkodas=postkodas)


@app.route('/add_family_member', methods=['GET', 'POST'])
def add_family_member():
    if 'ptal' not in session or session['ptal'] != 'admin':
        return redirect(url_for('login'))

    if request.method == 'POST':
        member_ptal = request.form['member_ptal']
        familju_id_value = request.form['familju_id'].strip()
        familju_rolla = request.form['familju_rolla'].strip()

        if not familju_rolla:
            flash('Familjurolla manglar')
            return redirect(url_for('add_family_member'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT 1 FROM personur WHERE ptal = :ptal", {
                           'ptal': member_ptal})
            if not cursor.fetchone():
                flash('Persónur er ikki funnin')
                return redirect(url_for('add_family_member'))

            if familju_id_value:
                try:
                    familju_id = int(familju_id_value)
                except ValueError:
                    flash('Familju ID má vera eitt tal')
                    return redirect(url_for('add_family_member'))

                cursor.execute(
                    "SELECT 1 FROM familja WHERE familju_id = :familju_id",
                    {'familju_id': familju_id},
                )
                if not cursor.fetchone():
                    flash('Familju ID er ikki funnið')
                    return redirect(url_for('add_family_member'))
            else:
                cursor.execute(
                    "SELECT NVL(MAX(familju_id), 0) + 1 FROM familja")
                familju_id = cursor.fetchone()[0]
                cursor.execute(
                    "INSERT INTO familja (familju_id) VALUES (:familju_id)",
                    {'familju_id': familju_id},
                )

            cursor.execute(
                "SELECT 1 FROM familju_limir WHERE familju_id = :familju_id AND ptal = :ptal",
                {'familju_id': familju_id, 'ptal': member_ptal},
            )
            if cursor.fetchone():
                flash('Persónur er longu í familjuni')
                return redirect(url_for('add_family_member'))

            cursor.execute(
                """
                INSERT INTO familju_limir (familju_id, ptal, familju_rolla)
                VALUES (:familju_id, :ptal, :rolla)
                """,
                {'familju_id': familju_id, 'ptal': member_ptal,
                    'rolla': familju_rolla},
            )

            conn.commit()
            flash(f'Familjulimur lagdur í familju {familju_id}')
            return redirect(url_for('dashboard'))
        except oracledb.DatabaseError:
            conn.rollback()
            flash('Kundi ikki leggja familjulim afturat')
            return redirect(url_for('add_family_member'))
        finally:
            cursor.close()
            conn.close()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.ptal, p.fornavn, p.eftirnavn
        FROM personur p
        ORDER BY p.fornavn, p.eftirnavn
        """
    )
    linked_people = cursor.fetchall()
    cursor.execute(
        """
        SELECT fl.familju_id, fl.ptal, p.fornavn, p.eftirnavn, fl.familju_rolla
        FROM familju_limir fl
        JOIN personur p ON p.ptal = fl.ptal
        ORDER BY fl.familju_id, p.fornavn, p.eftirnavn
        """
    )
    family_members = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'add_family_member.html',
        linked_people=linked_people,
        family_members=family_members,
    )


@app.route('/kundar')
def kundar():
    if 'ptal' not in session or session['ptal'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT p.ptal, p.fornavn, p.eftirnavn, p.adressa, p.fodidato, p.kyn, p.postkoda, pk.byur, k.kundi_id
        FROM personur p
        LEFT JOIN postkoda pk ON pk.postkoda = p.postkoda
        LEFT JOIN kundi k ON k.ptal = p.ptal
        ORDER BY k.kundi_id
        """
    )
    all_kundar = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('kundar.html', all_kundar=all_kundar)


@app.route('/bokingar')
def bokingar():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    if is_admin:
        # Admin sees all transactions
        cursor.execute("""
            SELECT b.bokingar_id, b.kontonr, b.bokingar_tekst, b.dato, b.upphaedd, b.bokingar_slag, b.leypandi_saldo
            FROM boking b
            ORDER BY b.dato DESC
        """)
        transactions = cursor.fetchall()
    else:
        # Regular user: transactions for their own accounts
        # Get all kontonr for this user's kundi
        cursor.execute("""
            SELECT k.kontonr
            FROM konto k
            JOIN kundi ku ON k.kundi_id = ku.kundi_id
            WHERE ku.ptal = :ptal
        """, {'ptal': ptal})
        user_kontonr = [row[0] for row in cursor.fetchall()]

        transactions = []
        if user_kontonr:
            # Get transactions for all user's accounts
            placeholders = ','.join([':' + str(i)
                                    for i in range(len(user_kontonr))])
            params = {str(i): k for i, k in enumerate(user_kontonr)}
            cursor.execute(f"""
                SELECT b.bokingar_id, b.kontonr, b.bokingar_tekst, b.dato, b.upphaedd, b.bokingar_slag, b.leypandi_saldo
                FROM boking b
                WHERE b.kontonr IN ({placeholders})
                ORDER BY b.dato DESC
            """, params)
            transactions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('bokingar.html', transactions=transactions, is_admin=is_admin)


@app.route('/kladda')
def kladda():
    if 'ptal' not in session:
        return redirect(url_for('login'))

    ptal = session['ptal']
    is_admin = (ptal == 'admin')

    conn = get_db_connection()
    cursor = conn.cursor()

    user_kontonr = []
    if not is_admin:
        # Get all kontonr for this user's kundi
        cursor.execute("""
            SELECT k.kontonr
            FROM konto k
            JOIN kundi ku ON k.kundi_id = ku.kundi_id
            WHERE ku.ptal = :ptal
        """, {'ptal': ptal})
        user_kontonr = [row[0] for row in cursor.fetchall()]

    if is_admin:
        # Admin sees all transfers with historical saldos and owner names
        cursor.execute("""
            SELECT k.kladda_id, k.kontonr_fra, k.kontonr_til, k.mottakara_tekst, k.egin_tekst, k.dato, k.upphaedd,
                   k.saldo_fra, k.saldo_til,
                   pf.fornavn || ' ' || pf.eftirnavn AS eigari_fra,
                   pt.fornavn || ' ' || pt.eftirnavn AS eigari_til
            FROM kladda k
            JOIN konto kf ON k.kontonr_fra = kf.kontonr
            JOIN konto kt ON k.kontonr_til = kt.kontonr
            JOIN kundi kuf ON kf.kundi_id = kuf.kundi_id
            JOIN kundi kut ON kt.kundi_id = kut.kundi_id
            JOIN personur pf ON kuf.ptal = pf.ptal
            JOIN personur pt ON kut.ptal = pt.ptal
            ORDER BY k.dato DESC
        """)
        transfers = cursor.fetchall()
    else:
        # Regular user: transfers involving their own accounts - show historical saldos
        transfers = []
        if user_kontonr:
            # Get transfers from or to user's accounts with historical saldos
            placeholders = ','.join([':' + str(i)
                                    for i in range(len(user_kontonr))])
            params = {str(i): k for i, k in enumerate(user_kontonr)}
            cursor.execute(f"""
                SELECT k.kladda_id, k.kontonr_fra, k.kontonr_til, k.mottakara_tekst, k.egin_tekst, k.dato, k.upphaedd,
                       k.saldo_fra, k.saldo_til,
                       pf.fornavn || ' ' || pf.eftirnavn AS eigari_fra,
                       pt.fornavn || ' ' || pt.eftirnavn AS eigari_til
                FROM kladda k
                JOIN konto kf ON k.kontonr_fra = kf.kontonr
                JOIN konto kt ON k.kontonr_til = kt.kontonr
                JOIN kundi kuf ON kf.kundi_id = kuf.kundi_id
                JOIN kundi kut ON kt.kundi_id = kut.kundi_id
                JOIN personur pf ON kuf.ptal = pf.ptal
                JOIN personur pt ON kut.ptal = pt.ptal
                WHERE k.kontonr_fra IN ({placeholders})
                   OR k.kontonr_til IN ({placeholders})
                ORDER BY k.dato DESC
            """, params)
            transfers = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('kladda.html', transfers=transfers, is_admin=is_admin, user_kontonr=user_kontonr)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    app.run(debug=True)
