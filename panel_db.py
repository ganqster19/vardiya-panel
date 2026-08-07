"""Mobil ve servis panelleri için ortak DB bağlantısı."""
import streamlit as st
import psycopg2
from datetime import datetime, timedelta, date
from typing import Optional
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


TIP_LABELS = {"pro": "Profesyonel", "student": "Öğrenci"}


def subscription_session_no(group_id) -> Optional[int]:
    """Abonelik oturum sırası: abc123_2 → 3 (group_id son eki + 1)."""
    gid = (group_id or "").strip()
    if not gid:
        return None
    parts = gid.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1]) + 1
    return None


def subscription_session_key(group_id):
    """Oturum anahtarı: (paket_id, oturum_indeksi)."""
    gid = (group_id or "").strip()
    if not gid:
        return None
    parts = gid.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return (parts[0], parts[1])
    return (gid, "")


def build_subscription_calendar_meta(rows):
    """yeni.py takvim ile aynı kota mantığı: toplam paket + tarih sırasına göre adım."""
    pkg_totals = {}
    pkg_sessions = {}
    for row in rows:
        if isinstance(row, dict):
            gid = (row.get("group_id") or "").strip()
            d = (row.get("date") or "").strip()
        else:
            gid = (row[0] or "").strip()
            d = (row[1] or "").strip() if len(row) > 1 else ""
        if not gid:
            continue
        pid = gid.split("_")[0]
        pkg_totals.setdefault(pid, set()).add(gid)
        if d:
            pkg_sessions.setdefault(pid, {})[gid] = d

    session_steps = {}
    for sessions_dict in pkg_sessions.values():
        sorted_sessions = sorted(
            sessions_dict.items(),
            key=lambda x: (
                datetime.strptime(x[1], "%d.%m.%Y") if x[1] else datetime.min,
                x[0],
            ),
        )
        for step, (gid, _) in enumerate(sorted_sessions, 1):
            session_steps[gid] = step

    return {
        "pkg_totals": {pid: len(sessions) for pid, sessions in pkg_totals.items()},
        "session_steps": session_steps,
    }


def subscription_label(job, meta=None) -> str:
    """Kota etiketi: [3/4] — yeni.py takvimi ile aynı."""
    if job.get("job_tag") != "subscription":
        return ""
    gid = (job.get("group_id") or "").strip()
    if not gid:
        return ""
    meta = meta or {}
    pid = gid.split("_")[0]
    total = meta.get("pkg_totals", {}).get(pid, 0)
    step = meta.get("session_steps", {}).get(gid)
    if step and total:
        return f" [{step}/{total}]"
    return ""


def job_visit_key(job):
    """Aynı ziyarete ait satırları grupla.

    - Abonelik: aynı müşteri + gün + paket → tek kart (2/4, 3/4 birlikte)
    - Tek seferlik: aynı müşteri + gün → tek kart
    """
    date = job.get("date") or ""
    gid = (job.get("group_id") or "").strip()
    cid = job.get("customer_id")
    tag = job.get("job_tag") or "one_time"

    if tag == "subscription":
        pid = gid.split("_")[0] if gid else ""
        if date and cid is not None and pid:
            return (date, "subpkg", str(cid), pid)
        sess = subscription_session_key(gid)
        if date and cid is not None and sess and sess[1]:
            return (date, "sub", str(cid), sess[1])
        if sess and sess[1]:
            return (date, "sub", sess[0], sess[1])
        if gid:
            return (date, "sub", gid)
        if cid is not None:
            return (date, "sub", f"c{cid}")
        return (date, "sub", str(job.get("id")))

    if cid is not None and date:
        return (date, "once", str(cid))
    if gid:
        return (date, "once", gid)
    return (date, "once", str(job.get("id")))


def visit_delete_action(group):
    """Ziyaret grubunun tamamını silmek için SQL."""
    j = visit_group_label(group)
    tag = j.get("job_tag") or "one_time"
    gid = (j.get("group_id") or "").strip()
    date = j.get("date") or ""
    cid = j.get("customer_id")

    if tag == "subscription":
        gids = {(r.get("group_id") or "").strip() for r in group if (r.get("group_id") or "").strip()}
        if len(gids) == 1:
            return ("DELETE FROM jobs WHERE group_id=%s", (next(iter(gids)),))
        if len(gids) > 1:
            return ("DELETE FROM jobs WHERE group_id = ANY(%s)", (list(gids),))
        ids = [r["id"] for r in group if r.get("id")]
        if ids:
            return ("DELETE FROM jobs WHERE id = ANY(%s)", (ids,))
    if tag == "one_time" and date and cid is not None:
        return (
            "DELETE FROM jobs WHERE customer_id=%s AND COALESCE(date, '')=%s AND job_tag=%s",
            (cid, date, "one_time"),
        )
    if gid:
        return (
            "DELETE FROM jobs WHERE group_id=%s AND COALESCE(date, '')=%s",
            (gid, date),
        )
    return None


def group_jobs_by_visit(jobs):
    """İş satırlarını ziyaret gruplarına ayır."""
    groups, order = {}, []
    for j in jobs:
        k = job_visit_key(j)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(j)
    return [groups[k] for k in order]


def summarize_personnel(rows):
    """Gruptaki personeli tip ve sayıya göre özetle."""
    counts = {"pro": 0, "student": 0}
    ucret = {"pro": 0.0, "student": 0.0}
    names = {"pro": [], "student": []}
    phones = {"pro": [], "student": []}
    for r in rows:
        tip = r.get("job_type") or "pro"
        if tip not in counts:
            tip = "pro"
        counts[tip] += 1
        ucret[tip] = float(r.get("price_worker") or 0)
        if r.get("staff_name"):
            names[tip].append(r.get("staff_name"))
        if r.get("staff_phone") is not None:
            phones[tip].append(r.get("staff_phone") or "")
    return counts, ucret, names, phones


def format_personnel_badge(counts, ucret=None):
    parts = []
    for tip in ("pro", "student"):
        n = counts.get(tip, 0)
        if n > 0:
            lbl = TIP_LABELS[tip]
            u = ""
            if ucret is not None and ucret.get(tip):
                u = f" · {ucret[tip]:,.0f} ₺/kişi"
            parts.append(f"**{n}** {lbl}{u}")
    return " · ".join(parts) if parts else "Personel yok"


def format_personnel_html(counts, ucret=None, names=None, phones=None):
    parts = []
    for tip in ("pro", "student"):
        n = counts.get(tip, 0)
        if n > 0:
            lbl = TIP_LABELS[tip]
            u = f" · {ucret[tip]:,.0f} ₺/kişi" if ucret and ucret.get(tip) else ""
            parts.append(f"<b>{n}</b> {lbl}{u}")
    line = " · ".join(parts) if parts else "Personel yok"
    if names:
        det = []
        for tip in ("pro", "student"):
            for nm, ph in zip(names.get(tip, []), phones.get(tip, [])):
                det.append(f"{nm}" + (f" ({ph})" if ph else ""))
        if det:
            line += "<br><span style='opacity:0.85'>" + ", ".join(det) + "</span>"
    return line


def personel_listesi_ozet(personeller):
    counts = {"pro": 0, "student": 0}
    ucret = {"pro": 0.0, "student": 0.0}
    for p in personeller:
        tip = p.get("tip") or "pro"
        counts[tip] = counts.get(tip, 0) + 1
        ucret[tip] = float(p.get("ucret") or 0)
    return format_personnel_badge(counts, ucret)


def expand_personnel_by_type(pro_n, pro_ucret, student_n, student_ucret, existing=None):
    """Tip ve sayıdan personel listesi oluştur."""
    existing = existing or {"pro": [], "student": [], "phones": {"pro": [], "student": []}}
    result = []
    for i in range(int(pro_n)):
        name = existing["pro"][i] if i < len(existing["pro"]) else f"Profesyonel {i + 1}"
        phone = existing["phones"]["pro"][i] if i < len(existing["phones"]["pro"]) else ""
        result.append({"tip": "pro", "ucret": float(pro_ucret), "name": name, "phone": phone})
    for i in range(int(student_n)):
        name = existing["student"][i] if i < len(existing["student"]) else f"Öğrenci {i + 1}"
        phone = existing["phones"]["student"][i] if i < len(existing["phones"]["student"]) else ""
        result.append({"tip": "student", "ucret": float(student_ucret), "name": name, "phone": phone})
    return result


def build_visit_db_rows(group_id, date_str, customer_id, job_tag, price_customer, personeller):
    """Tek ziyaret için DB insert satırları."""
    rows = []
    ilk = True
    for p in personeller:
        cut = float(price_customer) if ilk else 0.0
        ilk = False
        prepaid = 1 if cut > 0 else 0
        rows.append((
            group_id, date_str, customer_id, p["tip"], p["ucret"], cut, job_tag, prepaid,
            None, None, p.get("name"), p.get("phone") or None,
        ))
    return rows


def visit_group_label(group):
    """Grup temsil satırı."""
    return group[0] if group else {}


def subscription_labels_merged(group, meta=None) -> str:
    """Birleşik kart için kota etiketleri: [2/4, 3/4] — yeni.py mantığı."""
    meta = meta or {}
    j = visit_group_label(group)
    if j.get("job_tag") != "subscription":
        return ""
    gid_steps = []
    seen = set()
    for row in group:
        gid = (row.get("group_id") or "").strip()
        if not gid or gid in seen:
            continue
        seen.add(gid)
        step = meta.get("session_steps", {}).get(gid)
        if not step:
            continue
        pid = gid.split("_")[0]
        total = meta.get("pkg_totals", {}).get(pid, 0)
        if total:
            gid_steps.append((step, f"{step}/{total}"))
    if not gid_steps:
        return subscription_label(j, meta)
    gid_steps.sort(key=lambda x: x[0])
    unique = []
    for _, label in gid_steps:
        if label not in unique:
            unique.append(label)
    return " [" + ", ".join(unique) + "]"


def visit_has_pro(group) -> bool:
    counts, _, _, _ = summarize_personnel(group)
    return counts.get("pro", 0) > 0


def visit_customer_name(group) -> str:
    return (visit_group_label(group).get("name") or "").casefold()


def sort_visit_groups(groups):
    """Önce profesyonelli işler (A-Z), sonra yalnızca öğrencili işler (A-Z)."""
    return sorted(groups, key=lambda g: (0 if visit_has_pro(g) else 1, visit_customer_name(g)))


def min_visible_date() -> date:
    """Kısıtlı panellerde görülebilir en eski gün (dün)."""
    return date.today() - timedelta(days=RETENTION_DAYS)


def parse_tr_date_str(ds) -> Optional[date]:
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
            c.execute("""
                SELECT group_id, date FROM jobs
                WHERE job_tag = 'subscription'
                  AND group_id IS NOT NULL AND TRIM(group_id) <> ''
            """)
            data["subscription_meta"] = build_subscription_calendar_meta(c.fetchall())
            return data
    finally:
        conn.close()
