# 🌐 Téléchargeur Universel

## 🚀 Application de téléchargement vidéo/audio multi-plateforme avec interface Gradio

### ✨ Fonctionnalités

#### 📥 Téléchargement Intelligent
- **Formats multiples**: Vidéo+Audio combinés, Vidéo seule, Audio seul, Merge manuel
- **Détection automatique**: Reconnaît YouTube, Facebook, Instagram, TikTok, Twitter/X, Vimeo, Dailymotion, Twitch, Reddit et plus
- **Aperçu complet**: Miniature, titre, durée, plateforme affichés avant téléchargement
- **Formats optimaux**: Tri automatique par qualité (hauteur vidéo, bitrate audio)

#### 📋 File d'Attente Avancée
- **Ajout multiple**: Empile plusieurs vidéos à télécharger successivement
- **Traitement automatique**: Thread daemon qui traite la queue en arrière-plan
- **Pause/Reprise**: Contrôle complet du flux de téléchargements
- **Suppression ciblée**: Retire des éléments spécifiques de la file via dropdown
- **État en temps réel**: Progression actuelle + liste des vidéos en attente

#### 📊 Historique Persistant
- **Sauvegarde automatique**: Fichier `download_history.json` créé automatiquement
- **Informations complètes**: Titre, plateforme, taille, date/heure, chemin du fichier
- **Affichage tableau**: 20 derniers téléchargements formatés en Markdown
- **Nettoyage**: Bouton pour effacer l'historique sans toucher aux fichiers

#### 🗑️ Gestion des Fichiers
- **Dossier centralisé**: Tous les téléchargements dans `./downloads`
- **Création auto**: Le dossier est créé s'il n'existe pas
- **Suppression totale**: Bouton pour vider complètement le dossier downloads
- **Statut visible**: Chemin du dossier affiché dans l'interface

#### 🎵 Extraction Audio
- **FFmpeg intégré**: Détection automatique de FFmpeg au démarrage
- **Conversion MP3**: Audio extrait et converti en MP3 192kbps
- **Fallback gracieux**: Si FFmpeg absent, télécharge le format audio natif

---

## 📦 Installation

### Prérequis

**Python 3.12+** et **FFmpeg** (optionnel mais recommandé pour l'extraction audio)

#### Installer FFmpeg (Windows)

```bash
# Via Chocolatey
choco install ffmpeg

# Ou télécharger depuis https://ffmpeg.org/download.html
# Ajouter ffmpeg.exe au PATH Windows
```

#### Installer FFmpeg (Linux)

```bash
sudo apt install ffmpeg  # Debian/Ubuntu
sudo yum install ffmpeg  # RedHat/CentOS
```

### Installation de l'Application

```bash
# Cloner ou télécharger le projet
cd universal-downloader

# Créer un environnement virtuel (recommandé)
python -m venv venv

# Activer l'environnement
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
python universal_downloader.py
```

### Fichier requirements.txt

```txt
Flask
yt-dlp
Werkzeug
gradio
```

---

## 📖 Guide d'Utilisation

### Interface Principale

L'application se divise en **deux colonnes** :

#### Colonne Gauche : Téléchargement

1. **Coller une URL** dans le champ de texte
2. **Cliquer "🔍 Analyser"** pour extraire les informations
3. La **plateforme**, **miniature**, **titre** et **durée** s'affichent
4. **Choisir un format** dans les onglets (Combiné, Vidéo, Audio, Merge)
5. **Cliquer "📥 Télécharger"** pour ajouter à la file d'attente

#### Colonne Droite : Gestion

- **État de la file** : Progression actuelle et liste des téléchargements en attente
- **Contrôles** :
  - `⏸️ Mettre en Pause` / `▶️ Reprendre` : Contrôle le flux de téléchargements
  - `🗑️ Retirer de la file` : Sélectionne et supprime un élément spécifique
  - `🔄 Actualiser` : Met à jour manuellement l'affichage
- **Historique** : Tableau des 20 derniers téléchargements
  - `🔄 Actualiser` : Recharge l'historique
  - `🗑️ Effacer historique` : Nettoie le fichier JSON
- **Fichiers** :
  - `🗑️ Vider dossier downloads` : Supprime tous les fichiers téléchargés

---

## 🎯 Cas d'Usage

### Téléchargement Unique

```
1. Coller URL → Analyser
2. Choisir format dans l'onglet approprié
3. Cliquer "📥 Télécharger"
→ Vidéo ajoutée à la file et téléchargée automatiquement
```

### Téléchargement en Lot

```
1. URL #1 → Analyser → Choisir format → Télécharger
2. URL #2 → Analyser → Choisir format → Télécharger
3. URL #3 → Analyser → Choisir format → Télécharger
...
→ Toutes les vidéos se téléchargent successivement
```

### Gestion de la File

```
# Pause temporaire
1. Cliquer "⏸️ Mettre en Pause"
→ Le téléchargement en cours se termine, mais la file s'arrête

# Retirer un élément
1. Sélectionner la vidéo dans le dropdown "🗑️ Retirer de la file"
2. Cliquer le bouton
→ L'élément disparaît de la file sans être téléchargé

# Reprendre
1. Cliquer "▶️ Reprendre"
→ La file redémarre automatiquement
```

### Extraire l'Audio Uniquement

```
1. Analyser URL
2. Aller dans l'onglet "🎵 Audio Seul"
3. Choisir le meilleur bitrate
4. Télécharger
→ Si FFmpeg installé : fichier .mp3
→ Sinon : format audio natif (m4a, webm, etc.)
```

---

## 📁 Structure des Fichiers

```
universal-downloader/
├── universal_downloader.py      # Application principale
├── requirements.txt             # Dépendances Python
├── README.md                    # Ce fichier
├── downloads/                   # Dossier des téléchargements (créé auto)
│   ├── Ma_video_1.mp4
│   ├── Ma_video_2.mp4
│   └── Audio_track.mp3
└── download_history.json        # Historique (créé auto)
```
## ⚠️ Avertissement YouTube - Configuration des Cookies Requise

### 🚨 Depuis **octobre 2025**, YouTube bloque activement les téléchargements via `yt-dlp` sans authentification.
Conseil : utilisez très occasionnellement cette application pour télécharger les vidéos Youtube (risque de blocage IP)
---

## 🔧 Configuration

### Changer le Dossier de Téléchargement

Éditer `universal_downloader.py`, ligne ~22 :

```python
# Par défaut : dossier downloads à côté du script
DOWNLOADS_DIR = Path(__file__).parent / "downloads"

# Personnalisé Windows
DOWNLOADS_DIR = Path("D:/Mes Vidéos")

# Personnalisé Linux/Mac
DOWNLOADS_DIR = Path.home() / "Videos" / "Downloads"

# Toujours créer le dossier
DOWNLOADS_DIR.mkdir(exist_ok=True)
```

### Modifier la Taille de l'Historique

Ligne ~242 dans `get_download_history()` :

```python
# Par défaut : 20 derniers
for entry in reversed(download_history[-20:]):

# Afficher les 50 derniers
for entry in reversed(download_history[-50:]):

# Tout afficher
for entry in reversed(download_history):
```

### Personnaliser la File d'Attente Affichée

Ligne ~182 dans `get_queue_status()` :

```python
# Par défaut : 5 premiers éléments
for i, item in enumerate(queue_list[:5], 1):

# Afficher 10 éléments
for i, item in enumerate(queue_list[:10], 1):
```

---

## 🎓 Fonctionnalités Techniques

### Architecture Multi-Thread

**Thread principal** : Interface Gradio (interface utilisateur)  
**Thread daemon** : `process_queue()` qui traite la file d'attente en boucle

- Le thread vérifie `queue_pause_event` pour la pause/reprise
- Traite un élément à la fois pour éviter la surcharge
- Utilise un `queue.Queue()` thread-safe pour la synchronisation

### Gestion de l'État

```python
current_download = {
    'active': bool,      # Téléchargement en cours ?
    'should_stop': bool, # Annulation demandée ?
    'title': str,        # Titre de la vidéo actuelle
    'progress': float    # Pourcentage (0-100)
}
```

### Progress Hook

Fonction callback appelée par `yt-dlp` pendant le téléchargement :

```python
def progress_hook(d):
    # Vérifie si annulation demandée
    if current_download['should_stop']:
        raise yt_dlp.utils.DownloadError("Annulé")

    # Met à jour la progression
    if d['status'] == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        if total:
            current_download['progress'] = (d.get('downloaded_bytes', 0) / total) * 100
```

### Détection de Plateforme

Mapping URL → Plateforme dans `detect_platform()` :

```python
platforms = {
    'YouTube': ['youtube.com', 'youtu.be'],
    'Facebook': ['facebook.com', 'fb.watch'],
    'Instagram': ['instagram.com'],
    'TikTok': ['tiktok.com'],
    # ... 9 plateformes au total
}
```

### Persistance JSON

Format de `download_history.json` :

```json
[
  {
    "title": "Ma Super Vidéo",
    "platform": "YouTube",
    "size": "45.3 MB",
    "timestamp": "2025-10-30 14:25:33",
    "path": "/chemin/vers/downloads/Ma_Super_Video.mp4"
  }
]
```


### Gérer l'Espace Disque

- Surveiller la taille du dossier downloads régulièrement
- Déplacer les vidéos importantes ailleurs après téléchargement
- Utiliser "🗑️ Vider dossier downloads" pour nettoyer

### Performance

- **Une vidéo à la fois** : Optimal pour la stabilité et la vitesse
- **Pause inutile** : Laisser tourner, la queue gère automatiquement
- **Suppression ciblée** : Retire uniquement ce qui ne t'intéresse plus

### Formats Recommandés

| Usage | Format | Onglet |
|-------|--------|--------|
| Vidéo standard | 1080p combiné | Combiné |
| Haute qualité | 1440p/2160p vidéo + audio | Merge |
| Audio podcast | Meilleur bitrate | Audio Seul |
| Économiser espace | 720p combiné | Combiné |

---

## 📝 Crédits

- **yt-dlp** : Bibliothèque de téléchargement vidéo ([GitHub](https://github.com/yt-dlp/yt-dlp))
- **Gradio** : Framework d'interface utilisateur ([Site officiel](https://gradio.app))
- **FFmpeg** : Traitement audio/vidéo ([Site officiel](https://ffmpeg.org))

---

## 📄 Licence

Ce projet est open-source. Utilise-le librement pour tes besoins personnels ou professionnels.

---
Avertissement : Cet outil est fourni à des fins éducatives et de convenance personnelle. Il est de votre responsabilité de vous assurer que vous avez le droit de télécharger le contenu que vous ciblez. Veuillez respecter les lois sur le droit d'auteur de votre pays ainsi que les conditions d'utilisation des plateformes. Le développeur de cet outil ne peut être tenu responsable d'une utilisation illégale de celui-ci.
