# Vardiya Panel

Temizlik işletmesi vardiya yönetimi — Supabase PostgreSQL + Streamlit.

## Paneller

| Dosya | Kim kullanır | Açıklama |
|-------|----------------|----------|
| `panel_basit.py` | Yönetici (mobil) | İş, takvim, müşteri, personel, gider |
| `panel_servis.py` | Servis ekibi | Günlük iş listesi (salt okunur) |
| `yeni.py` | Masaüstü yönetim | Tam panel (finans, analiz, AI) |

## Lokal çalıştırma

```bash
pip install -r requirements.txt
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# secrets.toml içindeki değerleri doldurun

streamlit run panel_basit.py
streamlit run panel_servis.py
streamlit run yeni.py
```

## Streamlit Community Cloud (ücretsiz)

1. Bu klasörü GitHub reposuna yükleyin (`secrets.toml` **yüklenmesin**).
2. [share.streamlit.io](https://share.streamlit.io) → GitHub ile giriş.
3. **Her panel için ayrı app** oluşturun (Main file farklı):

   - App 1 → `panel_basit.py`
   - App 2 → `panel_servis.py`
   - App 3 → `yeni.py` (isteğe bağlı)

4. Her app'te **Settings → Secrets** → `.streamlit/secrets.toml.example` içeriğini gerçek değerlerle yapıştırın.

5. Deploy sonrası URL'leri ekiple paylaşın.

> **Not:** Cloud ortamında Supabase bağlantısı için `pooler_host` / `pooler_user` kullanılır (`panel_db.py` otomatik dener).

## GitHub'a yükleme

```bash
cd vardiya-panel
git init
git add .
git commit -m "Initial deploy"
git branch -M main
git remote add origin https://github.com/KULLANICI/REPO.git
git push -u origin main
```

## Güvenlik

- `secrets.toml` repoda olmamalı (`.gitignore`'da).
- Supabase şifresini kimseyle paylaşmayın.
- Servis paneli URL'sini sadece servis ekibiyle paylaşın.
