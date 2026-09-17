# --- START OF FILE universal_downloader_fb_safe.py ---

import gradio as gr
import yt_dlp
import os
from pathlib import Path
import subprocess
import threading
import queue
import time
from datetime import datetime
import json
import re
from itertools import count
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# ==============================================================================
# CONFIG
# ==============================================================================

APP_DIR = Path(__file__).parent
DOWNLOADS_DIR = APP_DIR / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)
HISTORY_FILE = APP_DIR / "download_history.json"

# ==============================================================================
# UTILITAIRES
# ==============================================================================

def check_ffmpeg():
    """Vérifie si FFmpeg est disponible."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return True
    except Exception:
        return False


FFMPEG_AVAILABLE = check_ffmpeg()


def sanitize_filename(filename):
    """Nettoie une chaîne pour un nom de fichier Windows/macOS/Linux."""
    filename = str(filename or "video")
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    filename = re.sub(r"\s+", " ", filename).strip()
    return filename[:140] or "video"


def format_duration(seconds):
    """Formate la durée en HH:MM:SS ou MM:SS."""
    if not seconds:
        return "Durée inconnue"
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"


YOUTUBE_CANONICAL_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}

# Domaines tiers/alternatifs connus qui servent de passerelle vers une vidéo YouTube.
# Ils sont convertis vers une URL officielle AVANT de passer la requête à yt-dlp.
YOUTUBE_ALIAS_HOSTS = {
    "yout-ube.com",
    "www.yout-ube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}

YOUTUBE_TRACKING_PARAMS = {"si", "feature", "app"}


def _normalized_hostname(url):
    """Retourne le hostname en minuscules, sans port final."""
    try:
        return (urlsplit(str(url or "").strip()).hostname or "").lower()
    except Exception:
        return ""


def is_youtube_url(url):
    """Détecte YouTube par hostname exact (évite les faux positifs par sous-chaîne)."""
    host = _normalized_hostname(url)
    return host in YOUTUBE_CANONICAL_HOSTS or host in YOUTUBE_ALIAS_HOSTS


def normalize_video_url(url):
    """Normalise les variantes YouTube connues vers une URL officielle stable.

    Exemples :
      yout-ube.com/shorts/ID      -> youtube.com/shorts/ID
      youtube-nocookie.com/embed/ID -> youtube.com/watch?v=ID
      youtu.be/ID                 -> youtube.com/watch?v=ID

    Les paramètres de playlist sont conservés ; seuls quelques paramètres de
    partage/traçage sans utilité pour l'extraction sont supprimés.
    """
    raw = str(url or "").strip()
    if not raw:
        return raw

    try:
        parts = urlsplit(raw)
    except Exception:
        return raw

    if parts.scheme.lower() not in {"http", "https"}:
        return raw

    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)

    # Supprime uniquement les paramètres de partage/traçage non nécessaires.
    query_pairs = [
        (k, v) for k, v in query_pairs
        if not k.lower().startswith("utm_") and k.lower() not in YOUTUBE_TRACKING_PARAMS
    ]

    if host == "youtu.be":
        video_id = path.strip("/").split("/")[0] if path.strip("/") else ""
        if video_id:
            query_pairs = [("v", video_id)] + [(k, v) for k, v in query_pairs if k != "v"]
            return urlunsplit(("https", "www.youtube.com", "/watch", urlencode(query_pairs, doseq=True), ""))

    if host in YOUTUBE_CANONICAL_HOSTS or host in YOUTUBE_ALIAS_HOSTS:
        # Toutes les variantes/alias sont ramenées sur le domaine officiel.
        canonical_host = "www.youtube.com"

        # Un embed youtube-nocookie est plus fiable pour yt-dlp sous forme /watch?v=.
        if path.startswith("/embed/"):
            video_id = path.split("/embed/", 1)[1].split("/", 1)[0]
            if video_id:
                query_pairs = [("v", video_id)] + [(k, v) for k, v in query_pairs if k != "v"]
                path = "/watch"

        return urlunsplit(("https", canonical_host, path, urlencode(query_pairs, doseq=True), ""))

    return raw


def detect_platform(url):
    """Détecte la plateforme depuis le hostname, avec support des alias YouTube."""
    if is_youtube_url(url):
        return "YouTube"

    host = _normalized_hostname(url)
    platforms = {
        "Facebook": {"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"},
        "Instagram": {"instagram.com", "www.instagram.com"},
        "TikTok": {"tiktok.com", "www.tiktok.com", "vm.tiktok.com"},
        "Twitter/X": {"twitter.com", "www.twitter.com", "x.com", "www.x.com"},
        "Vimeo": {"vimeo.com", "www.vimeo.com", "player.vimeo.com"},
        "Dailymotion": {"dailymotion.com", "www.dailymotion.com", "dai.ly"},
        "Twitch": {"twitch.tv", "www.twitch.tv"},
        "Reddit": {"reddit.com", "www.reddit.com", "redd.it"},
    }
    for platform, domains in platforms.items():
        if host in domains:
            return platform
    return "Autre/Inconnu"


def get_final_filepath(ydl, info, dl_type):
    """Récupère le chemin final de manière plus robuste après yt-dlp."""
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath") or item.get("filename")
        if filepath and os.path.exists(filepath):
            return filepath

    filename = ydl.prepare_filename(info)
    candidates = [filename]

    if dl_type == "audio_only" and FFMPEG_AVAILABLE:
        candidates.append(os.path.splitext(filename)[0] + ".mp3")

    if dl_type in {"merge", "combined"} and FFMPEG_AVAILABLE:
        candidates.append(os.path.splitext(filename)[0] + ".mp4")

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate

    # Dernier recours : dernier fichier modifié dans downloads.
    files = [p for p in DOWNLOADS_DIR.iterdir() if p.is_file()]
    if files:
        latest = max(files, key=lambda p: p.stat().st_mtime)
        if time.time() - latest.stat().st_mtime < 120:
            return str(latest)
    return filename


# ==============================================================================
# OPTIONS YT-DLP
# ==============================================================================

def build_ydl_base_opts(cookie_mode="Aucun", cookies_file=None, user_agent="", use_impersonate=False):
    """Options communes pour l'analyse et le téléchargement.

    Facebook peut nécessiter des cookies de session et/ou une empreinte navigateur.
    """
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "cachedir": False,
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 2,
    }

    browser_map = {
        "Firefox": "firefox",
        "Chrome": "chrome",
        "Edge": "edge",
        "Brave": "brave",
    }

    if cookie_mode in browser_map:
        opts["cookiesfrombrowser"] = (browser_map[cookie_mode],)
    elif cookie_mode == "cookies.txt" and cookies_file:
        opts["cookiefile"] = str(cookies_file)

    if user_agent and str(user_agent).strip():
        opts["http_headers"] = {"User-Agent": str(user_agent).strip()}

    if use_impersonate:
        opts["impersonate"] = "chrome"

    return opts


def apply_privacy_policy(url, privacy_mode, cookie_mode, cookies_file, user_agent, use_impersonate):
    """Applique le mode confidentialité uniquement aux URLs YouTube.

    Ce mode évite d'envoyer volontairement à yt-dlp les cookies du navigateur,
    un User-Agent personnalisé et l'impersonation demandés dans l'interface.
    Il ne rend PAS la connexion anonyme : le serveur distant voit toujours la
    connexion réseau (notamment l'adresse IP publique).
    """
    if privacy_mode and is_youtube_url(url):
        return "Aucun", None, "", False
    return cookie_mode, cookies_file, user_agent, use_impersonate


# ==============================================================================
# ETAT GLOBAL
# ==============================================================================

download_queue = queue.Queue()
queue_lock = threading.Lock()
queue_pause_event = threading.Event()
queue_pause_event.set()

current_download = {
    "active": False,
    "should_stop": False,
    "title": "",
    "url": "",
    "progress": 0,
    "phase": "",
}

last_worker_message = ""
download_history = []
queue_list = []
item_id_counter = count()


# ==============================================================================
# HISTORIQUE / NETTOYAGE
# ==============================================================================

def save_history():
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(download_history, f, ensure_ascii=False, indent=2)


def load_history():
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []


def clear_history():
    global download_history
    download_history = []
    save_history()
    return "🗑️ Historique effacé", get_download_history()


def clear_downloads_folder():
    try:
        deleted_count = 0
        for file in DOWNLOADS_DIR.iterdir():
            if file.is_file():
                file.unlink()
                deleted_count += 1
        return f"🗑️ {deleted_count} fichier(s) supprimé(s) du dossier downloads."
    except Exception as e:
        return f"❌ Erreur : {str(e)}"


# ==============================================================================
# FILE D'ATTENTE / TELECHARGEMENT
# ==============================================================================

def progress_hook(d):
    """Hook yt-dlp : progression + annulation."""
    if current_download["should_stop"]:
        raise yt_dlp.utils.DownloadError("Téléchargement annulé par l'utilisateur")

    status = d.get("status")
    if status == "downloading":
        current_download["phase"] = "Téléchargement"
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        if total:
            current_download["progress"] = (d.get("downloaded_bytes", 0) / total) * 100
        else:
            current_download["progress"] = 0
    elif status == "finished":
        current_download["phase"] = "Finalisation / fusion"
        current_download["progress"] = 100


def _perform_download(item):
    """Téléchargement réel d'un élément de la file."""
    global last_worker_message

    url = item["url"]
    format_id = item["format_id"]
    dl_type = item["download_type"]
    title = item["title"]
    platform = item["platform"]
    video_id = item.get("video_id") or "noid"
    cookie_mode = item.get("cookie_mode", "Aucun")
    cookies_file = item.get("cookies_file")
    user_agent = item.get("user_agent", "")
    use_impersonate = item.get("use_impersonate", False)
    privacy_mode = item.get("privacy_mode", True)

    cookie_mode, cookies_file, user_agent, use_impersonate = apply_privacy_policy(
        url, privacy_mode, cookie_mode, cookies_file, user_agent, use_impersonate
    )

    try:
        current_download.update({
            "active": True,
            "should_stop": False,
            "progress": 0,
            "phase": "Préparation",
            "title": title,
            "url": url,
        })

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = sanitize_filename(title)
        safe_platform = sanitize_filename(platform).replace("/", "-")
        safe_id = sanitize_filename(video_id)
        output_prefix = f"{timestamp}_{safe_platform}_{safe_id}_{safe_title}"

        ydl_opts = build_ydl_base_opts(cookie_mode, cookies_file, user_agent, use_impersonate)
        ydl_opts.update({
            "outtmpl": str(DOWNLOADS_DIR / f"{output_prefix}.%(ext)s"),
            "progress_hooks": [progress_hook],
            "windowsfilenames": True,
            "overwrites": False,
            "continuedl": False,
        })

        if dl_type in {"combined", "video_only", "audio_only", "merge"}:
            ydl_opts["format"] = format_id

        if dl_type == "audio_only" and FFMPEG_AVAILABLE:
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        elif dl_type == "merge" and FFMPEG_AVAILABLE:
            ydl_opts["merge_output_format"] = "mp4"
        elif dl_type == "combined" and FFMPEG_AVAILABLE:
            ydl_opts.setdefault("merge_output_format", "mp4")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            current_download["phase"] = "Extraction"
            info = ydl.extract_info(url, download=True)
            filename = get_final_filepath(ydl, info, dl_type)

        if os.path.exists(filename):
            file_size = os.path.getsize(filename) / (1024 * 1024)
            history_entry = {
                "title": title,
                "platform": platform,
                "size": f"{file_size:.1f} MB",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "path": filename,
                "url": url,
                "id": video_id,
            }
            download_history.append(history_entry)
            save_history()
            last_worker_message = f"✅ Téléchargé : {os.path.basename(filename)}"
            return last_worker_message

        last_worker_message = "❌ Erreur : fichier non trouvé après téléchargement"
        return last_worker_message

    except Exception as e:
        msg = "🛑 Annulé" if "annul" in str(e).lower() else f"❌ Erreur : {str(e)}"
        last_worker_message = msg
        return msg
    finally:
        current_download.update({
            "active": False,
            "title": "",
            "url": "",
            "phase": "",
            "progress": 0,
            "should_stop": False,
        })


def process_queue():
    """Thread qui traite la file d'attente."""
    while True:
        queue_pause_event.wait()
        if not current_download["active"] and not download_queue.empty():
            item = download_queue.get()
            with queue_lock:
                queue_list[:] = [q for q in queue_list if q["id"] != item["id"]]
            _perform_download(item)
        time.sleep(0.5)


def clear_pending_queue():
    """Vide uniquement les éléments en attente."""
    global download_queue
    with queue_lock:
        queue_list.clear()
        download_queue = queue.Queue()
    return "🧹 File d'attente vidée.", gr.update(value=None)


def stop_current_and_clear_queue():
    """Demande l'arrêt du téléchargement courant + vide la file."""
    global download_queue
    current_download["should_stop"] = True
    with queue_lock:
        queue_list.clear()
        download_queue = queue.Queue()
    return "🛑 Annulation demandée + file vidée.", gr.update(value=None)


def handle_download_request(
    current_url,
    analyzed_url,
    format_id,
    download_type,
    title,
    platform,
    video_id,
    cookie_mode="Aucun",
    cookies_file=None,
    user_agent="",
    use_impersonate=False,
    privacy_mode=True,
):
    """Ajoute un téléchargement à la file avec garde anti-ancienne URL."""
    current_url = (current_url or "").strip()
    analyzed_url = (analyzed_url or "").strip()

    if not analyzed_url:
        return "⚠️ Analyse d'abord l'URL avant de télécharger."

    # Compare les versions normalisées afin qu'un alias YouTube reste compatible
    # avec la garde anti-ancienne URL.
    if normalize_video_url(current_url) != normalize_video_url(analyzed_url):
        return "⚠️ L'URL a changé depuis la dernière analyse. Clique d'abord sur 🔍 Analyser pour éviter de télécharger l'ancienne vidéo."

    if not all([format_id, title, platform]):
        return "⚠️ Informations manquantes. Relance l'analyse de l'URL."

    if download_type == "merge" and "+None" in str(format_id):
        return "⚠️ Choisis une piste vidéo et une piste audio avant de fusionner."

    item = {
        "id": next(item_id_counter),
        "url": analyzed_url,
        "format_id": format_id,
        "download_type": download_type,
        "title": title,
        "platform": platform,
        "video_id": video_id or "noid",
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "cookie_mode": cookie_mode,
        "cookies_file": cookies_file,
        "user_agent": user_agent,
        "use_impersonate": use_impersonate,
        "privacy_mode": bool(privacy_mode),
    }

    with queue_lock:
        is_first_in_line = not current_download["active"] and download_queue.empty()
        queue_list.append(item)
        download_queue.put(item)
        position = len(queue_list)

    return "🚀 Lancement du téléchargement..." if is_first_in_line else f"✅ Ajouté à la file (position {position})"


def toggle_queue_pause():
    if queue_pause_event.is_set():
        queue_pause_event.clear()
        return gr.update(value="▶️ Reprendre", variant="primary")
    queue_pause_event.set()
    return gr.update(value="⏸️ Mettre en pause", variant="secondary")


def remove_from_queue(item_id_to_remove):
    global download_queue
    if item_id_to_remove is None:
        return "⚠️ Aucun élément sélectionné.", gr.update()

    with queue_lock:
        queue_list[:] = [item for item in queue_list if item["id"] != item_id_to_remove]
        temp_queue = queue.Queue()
        for item in queue_list:
            temp_queue.put(item)
        download_queue = temp_queue

    return "🗑️ Élément supprimé.", gr.update(value=None)


# ==============================================================================
# AFFICHAGE
# ==============================================================================

def get_queue_status():
    with queue_lock:
        queue_choices = [(f"{item['title'][:50]}...", item["id"]) for item in queue_list]
        queue_snapshot = list(queue_list)

    if current_download["active"]:
        status = (
            f"📥 Téléchargement : {current_download['title']}\n"
            f"Phase : {current_download.get('phase') or 'En cours'}\n"
            f"Progression : {current_download['progress']:.1f}%\n"
            f"URL : {current_download.get('url', '')[:90]}\n\n"
        )
    else:
        status = "✅ Prêt à télécharger\n\n"

    if last_worker_message:
        status += f"Dernier résultat : {last_worker_message}\n\n"

    if not queue_pause_event.is_set():
        status = "⏸️ FILE EN PAUSE\n\n" + status

    if queue_snapshot:
        status += f"📋 File d'attente ({len(queue_snapshot)}) :\n"
        for i, item in enumerate(queue_snapshot[:5], 1):
            status += f"{i}. {item['title'][:45]}...\n"
    else:
        status += "📋 File d'attente vide"

    return (
        status,
        gr.update(choices=queue_choices, visible=bool(queue_choices)),
        gr.update(visible=bool(queue_choices)),
    )


def get_download_history():
    if not download_history:
        return "📝 Aucun téléchargement."
    history_md = "| Titre | Plateforme | Taille | Date | ID |\n|---|---|---:|---|---|\n"
    for entry in reversed(download_history[-20:]):
        title_short = str(entry.get("title", "")).replace("|", " ")[:40]
        history_md += (
            f"| {title_short} | {entry.get('platform', '')} | {entry.get('size', '')} | "
            f"{entry.get('timestamp', '')} | {entry.get('id', '')} |\n"
        )
    return history_md


def analyze_url_and_update_ui(url, cookie_mode="Aucun", cookies_file=None, user_agent="", use_impersonate=False, privacy_mode=True):
    """Analyse l'URL et force un état propre pour éviter l'ancien téléchargement."""
    # Reset immédiat des états liés à l'ancienne vidéo.
    yield (
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(visible=False),
        gr.update(value="🔍 Analyse en cours...", visible=True),
        "",
        "",
        "",
        "",
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None),
        gr.update(choices=[], value=None),
    )

    try:
        original_url = (url or "").strip()
        if not original_url.lower().startswith(("http://", "https://")):
            raise ValueError("URL invalide")

        clean_url = normalize_video_url(original_url)
        effective_cookie_mode, effective_cookies_file, effective_user_agent, effective_impersonate = apply_privacy_policy(
            clean_url, privacy_mode, cookie_mode, cookies_file, user_agent, use_impersonate
        )

        opts = build_ydl_base_opts(
            effective_cookie_mode, effective_cookies_file, effective_user_agent, effective_impersonate
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)

        if "entries" in info and info.get("entries"):
            first = next((entry for entry in info["entries"] if entry), None)
            if first:
                info = first

        video_formats, audio_formats, combined_formats = [], [], []
        for f in info.get("formats", []) or []:
            fmt_id = f.get("format_id")
            if not fmt_id:
                continue
            height = f.get("height") or 0
            abr = f.get("abr") or 0
            ext = f.get("ext") or "?"
            filesize = f.get("filesize") or f.get("filesize_approx")
            size_mb = f" (~{filesize / (1024 * 1024):.1f}MB)" if filesize else ""
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")

            if vcodec != "none" and acodec != "none":
                combined_formats.append({
                    "label": f"{height}p ({ext}, vidéo+audio){size_mb} — {fmt_id}",
                    "format_id": fmt_id,
                    "height": height,
                })
            elif vcodec != "none" and acodec == "none":
                video_formats.append({
                    "label": f"{height}p (vidéo seule, {ext}){size_mb} — {fmt_id}",
                    "format_id": fmt_id,
                    "height": height,
                })
            elif acodec != "none" and vcodec == "none":
                audio_formats.append({
                    "label": f"Audio {abr}kbps ({ext}){size_mb} — {fmt_id}",
                    "format_id": fmt_id,
                    "abr": abr,
                })

        combined_formats.sort(key=lambda x: x["height"], reverse=True)
        video_formats.sort(key=lambda x: x["height"], reverse=True)
        audio_formats.sort(key=lambda x: x["abr"], reverse=True)

        title = info.get("title") or "Vidéo"
        thumbnail = info.get("thumbnail")
        platform = detect_platform(clean_url)
        video_id = str(info.get("id") or "noid")
        webpage_url = info.get("webpage_url") or clean_url
        duration = format_duration(info.get("duration"))

        normalized_note = ""
        if clean_url != original_url:
            normalized_note = f"**URL normalisée :** `{clean_url}`\n\n"

        privacy_note = ""
        if is_youtube_url(clean_url):
            if privacy_mode:
                privacy_note = "🔒 **Confidentialité YouTube : active** — cookies navigateur, User-Agent personnalisé et impersonation ignorés.\n\n"
            else:
                privacy_note = "🔓 **Confidentialité YouTube : désactivée** — les options d'authentification choisies peuvent être utilisées.\n\n"

        info_text = (
            f"✅ Vidéo trouvée ({duration})\n\n"
            f"{privacy_note}"
            f"**ID détecté :** `{video_id}`\n\n"
            f"**URL saisie :** `{original_url}`\n\n"
            f"{normalized_note}"
            f"**URL canonique yt-dlp :** `{webpage_url}`"
        )

        yield (
            gr.update(value=f"## {platform}", visible=True),
            gr.update(value=thumbnail, visible=bool(thumbnail)),
            gr.update(value=f"### {title}", visible=True),
            gr.update(value=info_text, visible=True),
            gr.update(visible=True),
            gr.update(visible=False),
            title,
            platform,
            clean_url,
            video_id,
            gr.update(
                choices=[(f["label"], f["format_id"]) for f in combined_formats],
                value=combined_formats[0]["format_id"] if combined_formats else None,
            ),
            gr.update(
                choices=[(f["label"], f["format_id"]) for f in video_formats],
                value=video_formats[0]["format_id"] if video_formats else None,
            ),
            gr.update(
                choices=[(f["label"], f["format_id"]) for f in audio_formats],
                value=audio_formats[0]["format_id"] if audio_formats else None,
            ),
            gr.update(choices=[(f["label"], f["format_id"]) for f in video_formats], value=video_formats[0]["format_id"] if video_formats else None),
            gr.update(choices=[(f["label"], f["format_id"]) for f in audio_formats], value=audio_formats[0]["format_id"] if audio_formats else None),
        )
    except Exception as e:
        yield (
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(visible=False),
            gr.update(value=f"❌ Erreur : {e}", visible=True),
            "",
            "",
            "",
            "",
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
            gr.update(choices=[], value=None),
        )


# ==============================================================================
# DEMARRAGE THREAD
# ==============================================================================

download_history = load_history()
queue_thread = threading.Thread(target=process_queue, daemon=True)
queue_thread.start()


# ==============================================================================
# INTERFACE GRADIO
# ==============================================================================

with gr.Blocks(theme=gr.themes.Soft(primary_hue="purple", secondary_hue="blue"), title="Téléchargeur Universel - vidéo/son") as app:
    video_title_state = gr.State("")
    platform_state = gr.State("")
    analyzed_url_state = gr.State("")
    video_id_state = gr.State("")

    gr.HTML("""
        <div style="text-align: center; font-size: 2.5em; font-weight: bold;">🌐 Téléchargeur Universel</div>
        <div style="text-align: center; color: #666; margin-bottom: 1.5em;">
            Téléchargement direct, file d'attente contrôlée, garde anti-ancienne URL.
        </div>
    """)

    with gr.Row():
        with gr.Column(scale=2):
            with gr.Row():
                url_input = gr.Textbox(label="URL de la vidéo", placeholder="https://...", scale=4)
                analyze_btn = gr.Button("🔍 Analyser", variant="primary", scale=1)

            privacy_mode = gr.Checkbox(
                label="🔒 Mode confidentialité YouTube (recommandé)",
                value=True,
                info="Pour YouTube uniquement : ignore les cookies navigateur, le User-Agent personnalisé et l'impersonation. L'adresse IP reste visible par le service.",
            )

            with gr.Accordion("Options Facebook / sites protégés", open=False):
                cookie_mode = gr.Dropdown(
                    label="Cookies de session",
                    choices=["Aucun", "Firefox", "Chrome", "Edge", "Brave", "cookies.txt"],
                    value="Aucun",
                    interactive=True,
                )
                cookies_file = gr.File(label="Fichier cookies.txt — optionnel", file_types=[".txt"], type="filepath")
                user_agent = gr.Textbox(label="User-Agent navigateur — optionnel", placeholder="Mozilla/5.0 ...")
                use_impersonate = gr.Checkbox(label="Essayer l'impersonation Chrome via curl_cffi", value=False)
                gr.Markdown("Astuce : pour Facebook, commence par Firefox ou Chrome si la vidéo est lisible dans ce navigateur avec ton compte connecté. Ne partage jamais ton fichier cookies.txt.")

            message_box = gr.Markdown(visible=False)
            platform_badge = gr.Markdown(visible=False)
            thumbnail_img = gr.Image(label="Aperçu", visible=False, height=300)
            video_title_md = gr.Markdown(visible=False)
            video_info_md = gr.Markdown(visible=False)

            with gr.Tabs(visible=False) as tabs:
                with gr.Tab("🎬 Vidéo + Audio"):
                    combined_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_combined_btn = gr.Button("📥 Télécharger", variant="primary")
                with gr.Tab("🎥 Vidéo seule"):
                    video_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_video_btn = gr.Button("📥 Télécharger", variant="primary")
                with gr.Tab("🎵 Audio seul"):
                    audio_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_audio_btn = gr.Button("📥 Télécharger", variant="primary", interactive=FFMPEG_AVAILABLE)
                with gr.Tab("🔧 Fusion manuelle"):
                    with gr.Row():
                        video_merge_list = gr.Dropdown(label="Vidéo", choices=[])
                        audio_merge_list = gr.Dropdown(label="Audio", choices=[])
                    download_merge_btn = gr.Button("📥 Télécharger et fusionner", variant="primary", interactive=FFMPEG_AVAILABLE)

            download_message = gr.Markdown()

        with gr.Column(scale=1):
            gr.Markdown("### 📊 Gestion de la file")
            queue_status = gr.Textbox(label="État", lines=10, interactive=False, max_lines=14)
            pause_resume_btn = gr.Button("⏸️ Mettre en pause", variant="secondary")

            with gr.Row():
                clear_queue_btn = gr.Button("🧹 Vider file", variant="secondary")
                stop_current_btn = gr.Button("🛑 Stop + vider", variant="stop")

            with gr.Row(visible=False) as queue_management_row:
                queue_dropdown = gr.Dropdown(label="Supprimer un élément", choices=[], interactive=True)
                remove_from_queue_btn = gr.Button("🗑️", variant="stop", scale=0)

            clear_message = gr.Markdown()

            gr.Markdown("### 📝 Historique")
            history_display = gr.Markdown(value=get_download_history())
            with gr.Row():
                refresh_history_btn = gr.Button("🔄 Actualiser")
                clear_history_btn = gr.Button("🗑️ Effacer")
            clear_downloads_btn = gr.Button("🗑️ Vider dossier downloads", variant="stop")

    gr.Markdown(f"📁 **Dossier de téléchargement :** `{DOWNLOADS_DIR}`")
    gr.Markdown("""
    ---
    **Avertissement légal :** Cet outil est fourni à des fins éducatives et de convenance personnelle. Il est de votre responsabilité de vous assurer que vous avez le droit de télécharger le contenu ciblé. Respectez les lois sur le droit d'auteur et les conditions d'utilisation des plateformes.
    """)

    analysis_outputs = [
        platform_badge,
        thumbnail_img,
        video_title_md,
        video_info_md,
        tabs,
        message_box,
        video_title_state,
        platform_state,
        analyzed_url_state,
        video_id_state,
        combined_list,
        video_list,
        audio_list,
        video_merge_list,
        audio_merge_list,
    ]

    analyze_btn.click(
        fn=analyze_url_and_update_ui,
        inputs=[url_input, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=analysis_outputs,
    )
    url_input.submit(
        fn=analyze_url_and_update_ui,
        inputs=[url_input, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=analysis_outputs,
    )

    common_download_inputs = [
        url_input,
        analyzed_url_state,
        video_title_state,
        platform_state,
        video_id_state,
        cookie_mode,
        cookies_file,
        user_agent,
        use_impersonate,
        privacy_mode,
    ]

    download_combined_btn.click(
        fn=lambda current_url, analyzed_url, fmt, title, platform, video_id, cm, cf, ua, imp, priv: handle_download_request(current_url, analyzed_url, fmt, "combined", title, platform, video_id, cm, cf, ua, imp, priv),
        inputs=[url_input, analyzed_url_state, combined_list, video_title_state, platform_state, video_id_state, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=[download_message],
    )
    download_video_btn.click(
        fn=lambda current_url, analyzed_url, fmt, title, platform, video_id, cm, cf, ua, imp, priv: handle_download_request(current_url, analyzed_url, fmt, "video_only", title, platform, video_id, cm, cf, ua, imp, priv),
        inputs=[url_input, analyzed_url_state, video_list, video_title_state, platform_state, video_id_state, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=[download_message],
    )
    download_audio_btn.click(
        fn=lambda current_url, analyzed_url, fmt, title, platform, video_id, cm, cf, ua, imp, priv: handle_download_request(current_url, analyzed_url, fmt, "audio_only", title, platform, video_id, cm, cf, ua, imp, priv),
        inputs=[url_input, analyzed_url_state, audio_list, video_title_state, platform_state, video_id_state, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=[download_message],
    )
    download_merge_btn.click(
        fn=lambda current_url, analyzed_url, v, a, title, platform, video_id, cm, cf, ua, imp, priv: handle_download_request(current_url, analyzed_url, f"{v}+{a}", "merge", title, platform, video_id, cm, cf, ua, imp, priv),
        inputs=[url_input, analyzed_url_state, video_merge_list, audio_merge_list, video_title_state, platform_state, video_id_state, cookie_mode, cookies_file, user_agent, use_impersonate, privacy_mode],
        outputs=[download_message],
    )

    pause_resume_btn.click(fn=toggle_queue_pause, outputs=[pause_resume_btn])
    clear_queue_btn.click(fn=clear_pending_queue, outputs=[clear_message, queue_dropdown])
    stop_current_btn.click(fn=stop_current_and_clear_queue, outputs=[clear_message, queue_dropdown])
    remove_from_queue_btn.click(fn=remove_from_queue, inputs=[queue_dropdown], outputs=[clear_message, queue_dropdown])

    refresh_history_btn.click(fn=get_download_history, outputs=[history_display])
    clear_history_btn.click(fn=clear_history, outputs=[clear_message, history_display])
    clear_downloads_btn.click(fn=clear_downloads_folder, outputs=[clear_message])

    def queue_status_updater():
        while True:
            yield get_queue_status()
            time.sleep(1)

    app.load(queue_status_updater, None, [queue_status, queue_dropdown, queue_management_row])


if __name__ == "__main__":
    print("Lancement de l'application... Accédez à http://localhost:7860")
    app.launch(server_name="127.0.0.1", server_port=7860)
