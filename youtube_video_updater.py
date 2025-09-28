import os
import threading
import queue
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, parse_qs

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# UI
from ttkbootstrap import Style
from ttkbootstrap.constants import *

# Veri
import pandas as pd

# Google / YouTube API
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---- Opsiyonel: thumbnail kalite kontrolü için Pillow ----
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ======= Ayarlar =======
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "token.json"

REQUIRED_COLUMNS = ["video_id"]
OPTIONAL_COLUMNS = [
    "title", "description", "tags", "categoryId",
    "privacyStatus", "publishAt", "made_for_kids",
    "thumbnail_path", "playlist_id", "is_short"
]

SUPPORTED_THUMB_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
MAX_THUMB_SIZE_MB = 2
MIN_THUMB_WIDTH = 1280
MIN_THUMB_HEIGHT = 720

# ======= Yardımcılar =======
def safe_bool(x: Any) -> bool:
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in ["true", "1", "evet", "yes"]

def parse_tags(tag_str: str) -> List[str]:
    if not isinstance(tag_str, str):
        return []
    return [t.strip() for t in tag_str.split(",") if t.strip()]

def load_table(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path)
    elif ext == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError("Lütfen .xlsx/.xls veya .csv dosyası seçin.")
    for col in REQUIRED_COLUMNS + OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[REQUIRED_COLUMNS + OPTIONAL_COLUMNS].copy()

def get_youtube_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(google.auth.transport.requests.Request())
            except Exception:
                creds = None
        if not creds:
            if not os.path.exists(CLIENT_SECRET_FILE):
                raise FileNotFoundError(f"'{CLIENT_SECRET_FILE}' bulunamadı.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                token.write(creds.to_json())
    return build("youtube", "v3", credentials=creds)

def normalize_playlist_id(x: str) -> str:
    s = (x or "").strip()
    if not s:
        return ""
    if s.startswith("http://") or s.startswith("https://"):
        qs = parse_qs(urlparse(s).query)
        pid = (qs.get("list") or [""])[0]
        return pid.strip()
    return s

def playlist_exists(youtube, playlist_id: str) -> bool:
    if not playlist_id:
        return False
    try:
        resp = youtube.playlists().list(part="id", id=playlist_id, maxResults=1).execute()
        return bool(resp.get("items"))
    except HttpError:
        return False

def list_my_playlists(youtube, log_cb=None):
    page_token = None
    count = 0
    while True:
        resp = youtube.playlists().list(
            part="id,snippet", mine=True, maxResults=50, pageToken=page_token
        ).execute()
        for it in resp.get("items", []):
            count += 1
            title = it["snippet"]["title"]
            pid = it["id"]
            if log_cb: log_cb(f"[PL{count:02}] {title}  |  ID: {pid}")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    if count == 0 and log_cb:
        log_cb("Bu hesapta hiç playlist bulunamadı.")

def list_my_recent_videos(youtube, max_results=10, log_cb=None):
    try:
        resp = youtube.search().list(
            part="id,snippet",
            forMine=True,  # eski sürümlerde 'mine' yerine forMine kullanılır
            type="video",
            order="date",
            maxResults=max_results
        ).execute()
        items = resp.get("items", [])
        if not items:
            if log_cb: log_cb("Hiç video bulunamadı.")
            return
        for idx, it in enumerate(items, start=1):
            vid = it["id"]["videoId"]
            title = it["snippet"]["title"]
            published = it["snippet"].get("publishedAt", "")
            if log_cb:
                log_cb(f"[{idx:02}] {title} | ID: {vid} | Yayın: {published}")
    except HttpError as e:
        if log_cb: log_cb(f"API Hatası: {e}")

def validate_thumbnail(thumb_path: str, log_cb=None) -> bool:
    if not thumb_path or not os.path.exists(thumb_path):
        if log_cb: log_cb("Thumbnail yok veya yol geçersiz, atlanıyor.")
        return False
    ext = os.path.splitext(thumb_path)[1].lower()
    if ext not in SUPPORTED_THUMB_EXTS:
        if log_cb: log_cb(f"Thumbnail uzantısı desteklenmiyor ({ext}). Desteklenen: {', '.join(SUPPORTED_THUMB_EXTS)}.")
        return False
    size_mb = os.path.getsize(thumb_path) / (1024*1024)
    if size_mb > MAX_THUMB_SIZE_MB:
        if log_cb: log_cb(f"Thumbnail {size_mb:.2f} MB (> {MAX_THUMB_SIZE_MB} MB). Atlanıyor.")
        return False
    if PIL_AVAILABLE:
        try:
            with Image.open(thumb_path) as im:
                w, h = im.size
                if w < MIN_THUMB_WIDTH or h < MIN_THUMB_HEIGHT:
                    if log_cb: log_cb(f"Thumbnail küçük ({w}x{h}). Önerilen min {MIN_THUMB_WIDTH}x{MIN_THUMB_HEIGHT}.")
                    return False
        except Exception:
            if log_cb: log_cb("Thumbnail açılırken hata oluştu, atlanıyor.")
            return False
    return True

# ======= Güncelleme İşlemleri =======
def fetch_current(youtube, video_id: str) -> Dict[str, Any]:
    resp = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        raise ValueError(f"Video bulunamadı: {video_id}")
    return items[0]

def build_update_body(current: Dict[str, Any], row: pd.Series, log_cb=None) -> Dict[str, Any]:
    body = {"id": current["id"]}
    cur_snippet = current.get("snippet", {}) or {}
    cur_status  = current.get("status", {}) or {}

    # Snippet
    snippet = {
        "title": cur_snippet.get("title", ""),
        "description": cur_snippet.get("description", ""),
        "categoryId": cur_snippet.get("categoryId", "22"),
    }
    if "tags" in cur_snippet:
        snippet["tags"] = cur_snippet.get("tags", [])

    title = str(row.get("title", "")).strip()
    if title:
        snippet["title"] = title

    desc = str(row.get("description", ""))
    if desc.strip() != "":
        snippet["description"] = desc.replace("\\n", "\n")

    tags_raw = str(row.get("tags", ""))
    if tags_raw.strip() != "":
        snippet["tags"] = parse_tags(tags_raw)

    cat = str(row.get("categoryId", "")).strip()
    if cat:
        snippet["categoryId"] = cat

    # Status
    status = {
        "privacyStatus": cur_status.get("privacyStatus", "public"),
        "selfDeclaredMadeForKids": cur_status.get("selfDeclaredMadeForKids", False)
    }
    priv = str(row.get("privacyStatus", "")).strip().lower()
    if priv:
        status["privacyStatus"] = "private" if priv == "scheduled" else priv

    mk = str(row.get("made_for_kids", "")).strip()
    if mk:
        status["selfDeclaredMadeForKids"] = safe_bool(mk)

    publish_at = str(row.get("publishAt", "")).strip()
    if publish_at:
        status["publishAt"] = publish_at

    body["snippet"] = snippet
    body["status"]  = status
    return body

def update_video(youtube, row: pd.Series, log_cb=None):
    video_id = str(row.get("video_id", "")).strip()
    if not video_id:
        raise ValueError("video_id zorunludur.")

    current = fetch_current(youtube, video_id)
    body = build_update_body(current, row, log_cb=log_cb)

    # Güncelle
    youtube.videos().update(part="snippet,status", body=body).execute()
    if log_cb: log_cb(f"Güncellendi: https://www.youtube.com/watch?v={video_id}")

    # Shorts ise thumbnail atlama ayarı
    is_short = safe_bool(row.get("is_short", "false"))

    # Thumbnail (isteğe bağlı, Shorts değilse)
    thumb_path = str(row.get("thumbnail_path", "")).strip()
    if thumb_path and not is_short:
        if validate_thumbnail(thumb_path, log_cb=log_cb):
            try:
                youtube.thumbnails().set(videoId=video_id, media_body=thumb_path).execute()
                if log_cb: log_cb("Thumbnail güncellendi.")
            except HttpError as e:
                if log_cb: log_cb(f"Thumbnail hatası: {e}")
    elif thumb_path and is_short:
        if log_cb: log_cb("Shorts işaretli; API üzerinden thumbnail güncellemesi atlandı.")

    # Playlist (isteğe bağlı: ekleme)
    raw_pl = str(row.get("playlist_id", "")).strip()
    pl_id = normalize_playlist_id(raw_pl)
    if pl_id:
        if playlist_exists(youtube, pl_id):
            try:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": pl_id,
                            "resourceId": {"kind": "youtube#video", "videoId": video_id}
                        }
                    }
                ).execute()
                if log_cb: log_cb(f"Playlist'e eklendi: {pl_id}")
            except HttpError as e:
                if log_cb: log_cb(f"Playlist ekleme hatası: {e}")
        else:
            if log_cb: log_cb(f"Uyarı: Playlist bulunamadı/erişim yok: {pl_id}")

# ======= Worker =======
class UpdateWorker(threading.Thread):
    def __init__(self, app, task_queue: queue.Queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self.task_queue = task_queue
        self.daemon = True

    def run(self):
        try:
            yt = get_youtube_service()
        except Exception as e:
            self.app.log(f"YouTube servisi/Yetkilendirme hatası: {e}")
            return

        while True:
            try:
                idx = self.task_queue.get(timeout=1)
            except queue.Empty:
                if self.app.stop_flag:
                    return
                continue

            if idx is None:
                self.task_queue.task_done()
                return

            try:
                row = self.app.df.iloc[idx]
                self.app.set_status(idx, "Güncelleniyor...")
                update_video(yt, row, log_cb=lambda m: self.app.log(f"[{idx+1}] {m}"))
                self.app.set_status(idx, "Tamamlandı")
            except Exception as e:
                self.app.set_status(idx, "Hata")
                self.app.log(f"[{idx+1}] Hata: {e}")
            finally:
                self.task_queue.task_done()
                if self.app.stop_flag:
                    return

# ======= GUI =======
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Video Updater (EBS)")
        self.root.geometry("1100x720")
        self.style = Style("flatly")
        self.stop_flag = False

        self.df: Optional[pd.DataFrame] = None
        self.file_path_var = tk.StringVar()
        self.concurrent_var = tk.IntVar(value=3)

        self.task_queue = queue.Queue()
        self.workers: List[UpdateWorker] = []

        self.build_gui()

    def build_gui(self):
        top = ttk.Frame(self.root, padding=12)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="Excel/CSV Dosyası:", width=18).pack(side=tk.LEFT)
        ttk.Entry(top, textvariable=self.file_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)

        ttk.Button(top, text="Dosya Seç", command=self.choose_file, bootstyle=PRIMARY).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="Google'da Yetkilendir", command=self.authorize, bootstyle=INFO).pack(side=tk.LEFT, padx=4)

        ctrl = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        ctrl.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(ctrl, text="Eşzamanlı İş (1-8):").pack(side=tk.LEFT)
        ttk.Spinbox(ctrl, from_=1, to=8, textvariable=self.concurrent_var, width=5).pack(side=tk.LEFT, padx=6)

        ttk.Button(ctrl, text="Güncellemeyi Başlat", command=self.start_updates, bootstyle=SUCCESS).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="Durdur", command=self.stop_updates, bootstyle=WARNING).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="Oynatma Listelerimi Göster", command=self.show_playlists, bootstyle=SECONDARY).pack(side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="Son Videoları Göster", command=self.show_recent_videos, bootstyle=SECONDARY).pack(side=tk.LEFT, padx=4)

        self.tree = ttk.Treeview(self.root, columns=("video_id","status"), show="headings", height=14)
        self.tree.heading("video_id", text="Video ID")
        self.tree.heading("status", text="Durum")
        self.tree.column("video_id", width=520, anchor=tk.W)
        self.tree.column("status", width=160, anchor=tk.CENTER)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12)

        bottom = ttk.Frame(self.root, padding=12)
        bottom.pack(side=tk.BOTTOM, fill=tk.BOTH)
        ttk.Label(bottom, text="Log / Çıktı:").pack(anchor=tk.W)
        self.log_text = tk.Text(bottom, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    # ---- GUI yardımcıları ----
    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Excel/CSV seçin",
            filetypes=[("Excel","*.xlsx *.xls"), ("CSV","*.csv")]
        )
        if path:
            try:
                df = load_table(path)
                self.df = df
                self.file_path_var.set(path)
                self.populate_tree()
                self.log(f"{len(df)} satır yüklendi.")
            except Exception as e:
                messagebox.showerror("Hata", str(e))

    def authorize(self):
        try:
            _ = get_youtube_service()
            messagebox.showinfo("Tamam", "Yetkilendirme başarılı.")
        except Exception as e:
            messagebox.showerror("Yetkilendirme Hatası", str(e))

    def populate_tree(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        if self.df is None:
            return
        for idx, row in self.df.iterrows():
            vid = str(row.get("video_id", ""))
            self.tree.insert("", tk.END, iid=str(idx), values=(vid, "Hazır"))

    def set_status(self, idx: int, status: str):
        vals = list(self.tree.item(str(idx), "values"))
        if len(vals) == 2:
            vals[1] = status
            self.tree.item(str(idx), values=vals)

    def start_updates(self):
        if self.df is None or self.df.empty:
            messagebox.showwarning("Uyarı", "Önce Excel/CSV yükleyin.")
            return
        self.stop_flag = False
        for i in range(len(self.df)):
            self.task_queue.put(i)
        conc = max(1, min(8, int(self.concurrent_var.get() or 3)))
        self.workers = []
        for _ in range(conc):
            w = UpdateWorker(self, self.task_queue)
            w.start()
            self.workers.append(w)
        self.log(f"Güncelleme başladı. Eşzamanlı işler: {conc}")

    def stop_updates(self):
        self.stop_flag = True
        # Kuyruktaki işlerin boşaltılması
        while True:
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except queue.Empty:
                break
        self.log("Durdurma işareti verildi.")

    def show_playlists(self):
        try:
            yt = get_youtube_service()
            self.log("Playlistler alınıyor...")
            list_my_playlists(yt, log_cb=self.log)
        except Exception as e:
            messagebox.showerror("Hata", str(e))

    def show_recent_videos(self):
        try:
            yt = get_youtube_service()
            self.log("Son yüklenen videolar alınıyor...")
            list_my_recent_videos(yt, max_results=10, log_cb=self.log)
        except Exception as e:
            messagebox.showerror("Hata", str(e))

# ======= Giriş Noktası =======
def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
