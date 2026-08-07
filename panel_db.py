"""Mobil ve servis panelleri için ortak DB bağlantısı."""
import streamlit as st
import psycopg2
from datetime import datetime, timedelta, date
from psycopg2.extras import RealDictCursor

RETENTION_DAYS = 1  # dün ve sonrası görünür; daha eski kayıtlar gizlenir

JOB_INSERT_SQL = """
    INSERT INTO jobs (
        group_id, date, customer_id, job_type, price_worker, price_customer,
        job_tag, is_prepaid, contact_phone, location_url, staff_name, staff_phone
    ) VALUES %s
"""


def job_musteri_telefon(job):
    """Telefon: müşteri profili öncelikli."""
    return (job.get("customer_phone") or job.get("contact_phone") or "").strip()


def job_musteri_konum(job):
    """Konum linki: müşteri profili öncelikli."""
    return (job.get("customer_location") or job.get("location_url") or "").strip()


def render_action_link(label, url=None, new_tab=False):
    """link_button eski Streamlit sürümlerinde key desteklemez; HTML link kullan."""
    if url:
        tgt = ' target="_blank" rel="noopener"' if new_tab else ""
        st.markdown(
            f'<a class="action-link" href="{url}"{tgt}>{label}</a>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="action-link-disabled">{label}</span>',
            unsafe_allow_html=True,
        )


def min_visible_date() -> date:
    """Kısıtlı panellerde görülebilir en eski gün (dün)."""
    return date.today() - timedelta(days=RETENTION_DAYS)


def parse_tr_date_str(ds) -> date | None:
    if not ds or not str(ds).strip():
        return None
    try:
        return datetime.strptime(str(ds).strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def is_date_visible(ds, admin: bool = False) -> bool:
    """Tarihli kayıt görünür mü? Tarihsiz işler (bekleyen kota) her zaman görünür."""
    if admin:
        return True
    d = parse_tr_date_str(ds)
    if d is None:
        return True
    return d >= min_visible_date()


def _job_date_filter_sql(admin: bool) -> str:
    if admin:
        return ""
    return """
        AND (
            j.date IS NULL OR TRIM(j.date) = ''
            OR (
                j.date ~ '^[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}$'
                AND TO_DATE(j.date, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '1 day'
            )
        )
    """


def _expense_date_filter_sql(admin: bool) -> str:
    if admin:
        return ""
    return """
        AND e.date ~ '^[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}$'
        AND TO_DATE(e.date, 'DD.MM.YYYY') >= CURRENT_DATE - INTERVAL '1 day'
    """


def get_db_connection():
    s = st.secrets["supabase"]
    denemeler = [(s["host"], s["user"])]
    if s.get("pooler_host") and s.get("pooler_user"):
        denemeler.append((s["pooler_host"], s["pooler_user"]))
    son_hata = None
    for host, user in denemeler:
        try:
            return psycopg2.connect(
                host=host, database=s["dbname"], user=user, password=s["password"],
                port=int(s.get("port", 5432)), cursor_factory=RealDictCursor,
                sslmode="require", connect_timeout=10,
            )
        except Exception as e:
            son_hata = e
    st.error(f"Bağlantı hatası: {son_hata}")
    st.stop()


def ensure_schema(conn):
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS service_personnel (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                phone TEXT DEFAULT ''
            )
        """)
        for col, typ in [
            ("contact_phone", "TEXT"),
            ("location_url", "TEXT"),
            ("staff_name", "TEXT"),
            ("staff_phone", "TEXT"),
        ]:
            c.execute(f"""
                ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {col} {typ}
            """)
        c.execute("""
            ALTER TABLE customers ADD COLUMN IF NOT EXISTS location TEXT DEFAULT ''
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                date TEXT NOT NULL,
                name TEXT DEFAULT '',
                description TEXT DEFAULT '',
                amount NUMERIC DEFAULT 0
            )
        """)
        c.execute("""
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS name TEXT DEFAULT ''
        """)
    conn.commit()


def load_panel_data(admin: bool = False):
    """admin=True → tam veri (yeni.py). admin=False → son 1 gün + tarihsiz işler."""
    conn = get_db_connection()
    try:
        ensure_schema(conn)
        job_filter = _job_date_filter_sql(admin)
        exp_filter = _expense_date_filter_sql(admin)
        with conn.cursor() as c:
            data = {"admin_mode": admin}
            c.execute(f"""
                SELECT j.*, c.name, c.phone AS customer_phone, c.location AS customer_location
                FROM jobs j JOIN customers c ON j.customer_id = c.id
                WHERE 1=1 {job_filter}
            """)
            data["jobs"] = c.fetchall()
            c.execute("SELECT * FROM customers ORDER BY name")
            data["customers"] = c.fetchall()
            c.execute("SELECT * FROM service_personnel ORDER BY name")
            data["service_personnel"] = c.fetchall()
            try:
                c.execute(f"""
                    SELECT * FROM expenses e
                    WHERE 1=1 {exp_filter}
                    ORDER BY date DESC, id DESC
                """)
                data["expenses"] = c.fetchall()
            except Exception:
                data["expenses"] = []
            return data
    finally:
        conn.close()
