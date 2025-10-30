# --- START OF FILE universal_downloader.py ---

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

# --- Fonctions utilitaires de base ---

def check_ffmpeg():
    """Vérifie si FFmpeg est disponible."""
    try:
        # Ajout de creationflags pour éviter l'ouverture de console sous Windows
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        return True
    except:
        return False

FFMPEG_AVAILABLE = check_ffmpeg()
DOWNLOADS_DIR = Path(__file__).parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

def sanitize_filename(filename):
    """Nettoie une chaîne de caractères pour la rendre valide comme nom de fichier."""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def format_duration(seconds):
    """Formate la durée en HH:MM:SS ou MM:SS."""
    if not seconds: return "Durée inconnue"
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def detect_platform(url):
    """Détecte la plateforme depuis l'URL."""
    platforms = {
        'YouTube': ['youtube.com', 'youtu.be'], 'Facebook': ['facebook.com', 'fb.watch'],
        'Instagram': ['instagram.com'], 'TikTok': ['tiktok.com'], 'Twitter/X': ['twitter.com', 'x.com'],
        'Vimeo': ['vimeo.com'], 'Dailymotion': ['dailymotion.com'], 'Twitch': ['twitch.tv'],
        'Reddit': ['reddit.com', 'redd.it']
    }
    url_lower = url.lower()
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return "Autre/Inconnu"

# --- Gestion d'état globale (file d'attente, pause, historique) ---

download_queue = queue.Queue()
queue_lock = threading.Lock()
queue_pause_event = threading.Event()
queue_pause_event.set()  # Par défaut, la file n'est PAS en pause

current_download = {'active': False, 'should_stop': False, 'title': '', 'progress': 0}
download_history = []
queue_list = []  # Liste miroir pour l'affichage, plus facile à manipuler
item_id_counter = count()  # Générateur d'ID uniques pour chaque tâche

# --- Fonctions de gestion de l'historique ---

def save_history():
    history_file = Path(__file__).parent / "download_history.json"
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(download_history, f, ensure_ascii=False, indent=2)

def load_history():
    history_file = Path(__file__).parent / "download_history.json"
    if history_file.exists():
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def clear_history():
    """Efface l'historique et met à jour l'affichage."""
    global download_history
    download_history = []
    save_history()
    return "🗑️ Historique effacé", get_download_history()

def clear_downloads_folder():
    """Supprime tous les fichiers du dossier downloads."""
    try:
        deleted_count = 0
        for file in DOWNLOADS_DIR.iterdir():
            if file.is_file():
                file.unlink()
                deleted_count += 1  # ✅ Utilise deleted_count
        return f"🗑️ {deleted_count} fichier(s) supprimé(s) du dossier downloads."  # ✅ Et ici aussi
    except Exception as e:
        return f"❌ Erreur : {str(e)}"

# --- Logique de téléchargement et de la file d'attente ---

def progress_hook(d):
    """Hook pour suivre la progression et permettre l'annulation."""
    if current_download['should_stop']:
        raise yt_dlp.utils.DownloadError("Téléchargement annulé par l'utilisateur")
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            current_download['progress'] = (d.get('downloaded_bytes', 0) / total) * 100

def _perform_download(item):
    """Fonction interne qui effectue le téléchargement réel d'un élément."""
    url, format_id, dl_type, title, platform = item['url'], item['format_id'], item['download_type'], item['title'], item['platform']
    try:
        current_download.update({'active': True, 'should_stop': False, 'progress': 0, 'title': title})
        sanitized_title = sanitize_filename(title)
        ydl_opts = {
            'outtmpl': str(DOWNLOADS_DIR / f'{sanitized_title}.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': True,
            'no_warnings': True,
        }
        if dl_type == "combined": ydl_opts['format'] = format_id
        elif dl_type == "video_only": ydl_opts['format'] = format_id
        elif dl_type == "audio_only":
            ydl_opts['format'] = format_id
            if FFMPEG_AVAILABLE: ydl_opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}]
        elif dl_type == "merge":
            ydl_opts['format'] = format_id
            if FFMPEG_AVAILABLE: ydl_opts['merge_output_format'] = 'mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if dl_type == "audio_only" and FFMPEG_AVAILABLE and not filename.endswith('.mp3'):
                 filename = os.path.splitext(filename)[0] + '.mp3'
        
        if os.path.exists(filename):
            file_size = os.path.getsize(filename) / (1024*1024)
            history_entry = {'title': title, 'platform': platform, 'size': f"{file_size:.1f} MB", 'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'path': filename}
            download_history.append(history_entry)
            save_history()
            return f"✅ Téléchargé : {os.path.basename(filename)}"
        return "❌ Erreur : Fichier non trouvé après téléchargement"
    except Exception as e:
        return "🛑 Annulé" if "annulé" in str(e).lower() else f"❌ Erreur : {str(e)}"
    finally:
        current_download.update({'active': False, 'title': ''})

def process_queue():
    """Thread qui traite la file d'attente en arrière-plan."""
    while True:
        queue_pause_event.wait()  # Le thread attend ici si l'événement est "clear" (pause)
        if not current_download['active'] and not download_queue.empty():
            item = download_queue.get()
            with queue_lock:
                if queue_list and queue_list[0]['id'] == item['id']:
                    queue_list.pop(0)
            
            _perform_download(item)
        time.sleep(0.5)

def handle_download_request(url, format_id, download_type, title, platform):
    """Fonction unique appelée par tous les boutons 'Télécharger'.
    LOGIQUE CORRIGÉE : ajoute TOUJOURS à la liste visible pour la cohérence.
    """
    if not all([url, format_id, title, platform]):
        return "⚠️ Informations manquantes. Veuillez d'abord analyser une URL et sélectionner un format."

    item = {
        'id': next(item_id_counter), 'url': url, 'format_id': format_id, 'download_type': download_type,
        'title': title, 'platform': platform, 'timestamp': datetime.now().strftime("%H:%M:%S")
    }

    with queue_lock:
        is_first_in_line = not current_download['active'] and download_queue.empty()
        
        # On ajoute TOUJOURS l'élément à la file et à la liste visible
        queue_list.append(item)
        download_queue.put(item)

        if is_first_in_line:
            return "🚀 Lancement du téléchargement..."
        else:
            return f"✅ Ajouté à la file (position {len(queue_list)})"

def toggle_queue_pause():
    """Met en pause ou reprend la file d'attente."""
    if queue_pause_event.is_set():
        queue_pause_event.clear()  # Met en pause
        return gr.update(value="▶️ Reprendre", variant="primary")
    else:
        queue_pause_event.set()  # Reprend
        return gr.update(value="⏸️ Mettre en Pause", variant="secondary")

def remove_from_queue(item_id_to_remove):
    """Supprime un élément spécifique de la file d'attente."""
    if item_id_to_remove is None: 
        return "⚠️ Aucun élément sélectionné.", gr.update() # gr.update() sans argument = ne rien changer

    with queue_lock:
        # ... (la logique interne reste la même)
        queue_list[:] = [item for item in queue_list if item['id'] != item_id_to_remove]
        temp_queue = queue.Queue()
        for item in queue_list:
            temp_queue.put(item)

def remove_from_queue(item_id_to_remove):
    global download_queue  # Déclarer en début
    # ...
    download_queue = temp_queue
            
    # On retourne un message ET l'ordre de vider la sélection du dropdown
    return f"🗑️ Élément supprimé.", gr.update(value=None)

# --- Fonctions de mise à jour de l'interface Gradio ---

def get_queue_status():
    """Retourne l'état actuel de la file pour l'affichage."""
    with queue_lock:
        queue_choices = [(f"{item['title'][:50]}...", item['id']) for item in queue_list]
        queue_len = len(queue_list)

    if current_download['active']:
        status = f"📥 Téléchargement : {current_download['title']}\nProgression : {current_download['progress']:.1f}%\n\n"
    else:
        status = "✅ Prêt à télécharger\n\n"

    if not queue_pause_event.is_set():
        status = "⏸️ FILE EN PAUSE\n\n" + status

    if queue_len > 0:
        status += f"📋 File d'attente ({queue_len}) :\n"
        for i, item in enumerate(queue_list[:5], 1):
            status += f"{i}. {item['title'][:45]}...\n"
    else:
        status += "📋 File d'attente vide"
        
    return (
        status,
        # On ne touche plus à la 'value', on met juste à jour les choix et la visibilité
        gr.update(choices=queue_choices, visible=bool(queue_choices)), # <-- LIGNE CORRIGÉE
        gr.update(visible=bool(queue_choices))
    )

def get_download_history():
    """Retourne l'historique formaté pour l'affichage."""
    if not download_history: return "📝 Aucun téléchargement."
    history_md = "| Titre | Plateforme | Taille | Date |\n|---|---|---|---|\n"
    for entry in reversed(download_history[-20:]):
        title_short = entry['title'].replace('|', ' ')[:40]
        history_md += f"| {title_short} | {entry['platform']} | {entry['size']} | {entry['timestamp']} |\n"
    return history_md

def analyze_url_and_update_ui(url):
    """Analyse l'URL et met à jour l'interface avec les informations et formats."""
    yield (gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
           gr.update(visible=False), gr.update(visible=False),
           gr.update(value="🔍 Analyse en cours...", visible=True),
           "", "", gr.update(choices=[]), gr.update(choices=[]), gr.update(choices=[]),
           gr.update(choices=[]), gr.update(choices=[]))

    try:
        if not url or not url.startswith('http'): raise ValueError("URL invalide")
        
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)
        
        video_formats, audio_formats, combined_formats = [], [], []
        if 'formats' in info:
            for f in info.get('formats', []):
                size_mb = f" (~{f['filesize']/(1024*1024):.1f}MB)" if f.get('filesize') else ""
                if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    label = f"{f.get('height', 0)}p ({f.get('ext', 'vid')}){size_mb}"
                    combined_formats.append({'label': label, 'format_id': f['format_id'], 'height': f.get('height', 0)})
                elif f.get('vcodec') != 'none' and f.get('acodec') == 'none':
                    label = f"{f.get('height', 0)}p (vidéo seule, {f.get('ext', 'vid')}){size_mb}"
                    video_formats.append({'label': label, 'format_id': f['format_id'], 'height': f.get('height', 0)})
                elif f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                    label = f"Audio {f.get('abr', 0)}kbps ({f.get('ext', 'aud')}){size_mb}"
                    audio_formats.append({'label': label, 'format_id': f['format_id'], 'abr': f.get('abr', 0)})

        combined_formats.sort(key=lambda x: x['height'], reverse=True)
        video_formats.sort(key=lambda x: x['height'], reverse=True)
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        
        title, thumbnail, platform = info.get('title', 'Vidéo'), info.get('thumbnail'), detect_platform(url)
        
        yield (
            gr.update(value=f"## {platform}", visible=True),
            gr.update(value=thumbnail, visible=bool(thumbnail)),
            gr.update(value=f"### {title}", visible=True),
            gr.update(value=f"✅ Vidéo trouvée ({format_duration(info.get('duration'))})", visible=True),
            gr.update(visible=True), gr.update(visible=False),
            title, platform,
            gr.update(choices=[(f['label'], f['format_id']) for f in combined_formats], value=combined_formats[0]['format_id'] if combined_formats else None),
            gr.update(choices=[(f['label'], f['format_id']) for f in video_formats], value=video_formats[0]['format_id'] if video_formats else None),
            gr.update(choices=[(f['label'], f['format_id']) for f in audio_formats], value=audio_formats[0]['format_id'] if audio_formats else None),
            gr.update(choices=[(f['label'], f['format_id']) for f in video_formats]),
            gr.update(choices=[(f['label'], f['format_id']) for f in audio_formats]),
        )
    except Exception as e:
        yield (gr.update(visible=False), gr.update(visible=False), gr.update(visible=False),
               gr.update(visible=False), gr.update(visible=False),
               gr.update(value=f"❌ Erreur: {e}", visible=True),
               "", "", gr.update(choices=[]), gr.update(choices=[]), gr.update(choices=[]),
               gr.update(choices=[]), gr.update(choices=[]))

# --- Démarrage de l'application et du thread ---
download_history = load_history()
queue_thread = threading.Thread(target=process_queue, daemon=True)
queue_thread.start()

# ==============================================================================
# --- INTERFACE GRADIO ---
# ==============================================================================
with gr.Blocks(theme=gr.themes.Soft(primary_hue="purple", secondary_hue="blue"), title="Téléchargeur Universel - vidéo/son") as app:
    video_title_state = gr.State("")
    platform_state = gr.State("")

    gr.HTML("""
        <div style="text-align: center; font-size: 2.5em; font-weight: bold;">🌐 Téléchargeur Universel</div>
        <div style="text-align: center; color: #666; margin-bottom: 1.5em;">
            Téléchargement direct et file d'attente automatique.
        </div>
    """)
    with gr.Row():
        with gr.Column(scale=2):
            with gr.Row():
                url_input = gr.Textbox(label="URL de la vidéo", placeholder="https://...", scale=4)
                analyze_btn = gr.Button("🔍 Analyser", variant="primary", scale=1)
            
            message_box = gr.Markdown(visible=False)
            platform_badge = gr.Markdown(visible=False)
            thumbnail_img = gr.Image(label="Aperçu", visible=False, height=300)
            video_title_md = gr.Markdown(visible=False)
            video_info_md = gr.Markdown(visible=False)

            with gr.Tabs(visible=False) as tabs:
                with gr.Tab("🎬 Vidéo + Audio"):
                    combined_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_combined_btn = gr.Button("📥 Télécharger", variant="primary")
                with gr.Tab("🎥 Vidéo Seule"):
                    video_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_video_btn = gr.Button("📥 Télécharger", variant="primary")
                with gr.Tab("🎵 Audio Seul"):
                    audio_list = gr.Radio(label="Qualité", choices=[], interactive=True)
                    download_audio_btn = gr.Button("📥 Télécharger", variant="primary", interactive=FFMPEG_AVAILABLE)
                with gr.Tab("🔧 Fusion Manuelle"):
                    with gr.Row():
                        video_merge_list = gr.Dropdown(label="Vidéo", choices=[])
                        audio_merge_list = gr.Dropdown(label="Audio", choices=[])
                    download_merge_btn = gr.Button("📥 Télécharger et Fusionner", variant="primary", interactive=FFMPEG_AVAILABLE)
            
            download_message = gr.Markdown()

        with gr.Column(scale=1):
            gr.Markdown("### 📊 Gestion de la File")
            queue_status = gr.Textbox(label="État", lines=8, interactive=False, max_lines=10)
            pause_resume_btn = gr.Button("⏸️ Mettre en Pause", variant="secondary")
            
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
    **Avertissement légal :** Cet outil est fourni à des fins éducatives et de convenance personnelle. Il est de votre responsabilité de vous assurer que vous avez le droit de télécharger le contenu que vous ciblez. Veuillez respecter les lois sur le droit d'auteur de votre pays ainsi que les conditions d'utilisation des plateformes. Le développeur de cet outil ne peut être tenu responsable d'une utilisation illégale de celui-ci.
    """)

    # --- Événements Gradio ---
    analyze_btn.click(
        fn=analyze_url_and_update_ui,
        inputs=[url_input],
        outputs=[platform_badge, thumbnail_img, video_title_md, video_info_md, tabs, message_box,
                 video_title_state, platform_state,
                 combined_list, video_list, audio_list, video_merge_list, audio_merge_list]
    )
    url_input.submit(
        fn=analyze_url_and_update_ui,
        inputs=[url_input],
        outputs=[platform_badge, thumbnail_img, video_title_md, video_info_md, tabs, message_box,
                 video_title_state, platform_state,
                 combined_list, video_list, audio_list, video_merge_list, audio_merge_list]
    )

    download_combined_btn.click(fn=handle_download_request, inputs=[url_input, combined_list, gr.State("combined"), video_title_state, platform_state], outputs=[download_message])
    download_video_btn.click(fn=handle_download_request, inputs=[url_input, video_list, gr.State("video_only"), video_title_state, platform_state], outputs=[download_message])
    download_audio_btn.click(fn=handle_download_request, inputs=[url_input, audio_list, gr.State("audio_only"), video_title_state, platform_state], outputs=[download_message])
    download_merge_btn.click(fn=lambda u, v, a, t, p: handle_download_request(u, f"{v}+{a}", "merge", t, p), inputs=[url_input, video_merge_list, audio_merge_list, video_title_state, platform_state], outputs=[download_message])

    pause_resume_btn.click(fn=toggle_queue_pause, outputs=[pause_resume_btn])
    remove_from_queue_btn.click(fn=remove_from_queue, inputs=[queue_dropdown], outputs=[clear_message, queue_dropdown])
    
    refresh_history_btn.click(fn=get_download_history, outputs=[history_display])
    clear_history_btn.click(fn=clear_history, outputs=[clear_message, history_display])
    clear_downloads_btn.click(fn=clear_downloads_folder, outputs=[clear_message])

    def queue_status_updater():
        """Générateur qui met à jour le statut de la file en continu."""
        while True:
            yield get_queue_status()
            time.sleep(1) # Rafraîchit toutes les secondes

    app.load(queue_status_updater, None, [queue_status, queue_dropdown, queue_management_row])


if __name__ == "__main__":
    print(f"Lancement de l'application... Accédez à http://localhost:7860")
    app.launch(server_name="127.0.0.1", server_port=7860)