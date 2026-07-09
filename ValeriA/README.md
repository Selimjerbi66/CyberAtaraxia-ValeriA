# Chat IA local avec recherche web (SearXNG + Ollama)

Interface de chat façon Claude, 100% auto-hébergée, sans clé API.
Flux pour chaque message :

```
ta question → SearXNG (recherche web) → scraping des pages trouvées
           → question + pages web envoyées à Ollama → réponse générée en streaming
```

## Prérequis

- Ollama qui tourne déjà sur la machine (`http://localhost:11434`)
- SearXNG qui tourne déjà avec le format JSON activé (`http://localhost:8081/search`)
  — voir la conversation précédente si ce n'est pas encore fait.
- Docker installé.

## 1. Construire l'image

Depuis le dossier du projet (là où se trouve le `Dockerfile`) :

```bash
docker build -t ollama-chat .
```

## 2. Lancer le conteneur

En `--network host`, comme Ollama et Open WebUI, pour que `localhost`
fonctionne directement à l'intérieur du conteneur :

```bash
docker run -d \
  --name ollama-chat \
  --network host \
  -v ollama_chat_data:/data \
  --restart unless-stopped \
  ollama-chat
```

Le volume `ollama_chat_data` garde tes conversations, tes paramètres et
ton mot de passe même si tu recrées le conteneur.

## 3. Ouvrir l'application

Va sur :

```
http://<IP_DE_TA_MACHINE>:8090
```

Au premier lancement, l'appli te demande de créer un mot de passe
(configuration initiale, il n'y a pas de mot de passe par défaut).

## 4. Configurer dans l'interface

Clique sur **Paramètres** (en bas de la barre latérale) pour ajuster :

- **URL du moteur SearXNG** (par défaut `http://localhost:8081/search`)
- **Nombre de sources** récupérées par recherche (par défaut 10)
- **Mode de récupération** :
  - *Hybride* (recommandé) : scrape la page complète, et si ça échoue,
    retombe sur l'extrait fourni par SearXNG
  - *Scraping complet uniquement* : ignore les pages qui échouent
  - *Extraits SearXNG uniquement* : ne scrape jamais, plus rapide mais
    moins riche
- **URL Ollama** et **modèle** utilisé (la liste des modèles se
  charge automatiquement depuis ton serveur Ollama)

## Mot de passe oublié / bloqué dehors

Aucune récupération par email n'est nécessaire : si tu as accès au
serveur, tu as le droit de réinitialiser. Lance simplement :

```bash
docker exec -it ollama-chat python reset_password.py
```

Ça te demande un nouveau mot de passe et déconnecte automatiquement
toutes les sessions actives par sécurité.

## Mettre à jour l'application après une modification du code

```bash
docker stop ollama-chat
docker rm ollama-chat
docker build -t ollama-chat .
docker run -d --name ollama-chat --network host -v ollama_chat_data:/data --restart unless-stopped ollama-chat
```

Tes conversations et ton mot de passe sont conservés grâce au volume.

## Vérifier les logs

```bash
docker logs -f ollama-chat
```

## Structure du projet

```
ollama-chat/
├── backend/
│   ├── main.py            # Routes FastAPI + streaming SSE
│   ├── database.py        # SQLite (chats, messages, settings, user)
│   ├── auth.py             # Hash de mot de passe + sessions
│   ├── reset_password.py  # Script CLI de récupération
│   ├── search_engine.py   # Requête SearXNG + scraping des pages
│   ├── ollama_client.py   # Liste des modèles + chat en streaming
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── Dockerfile
```

## Limitations connues

- Un seul utilisateur/mot de passe (pas de multi-compte).
- Le scraping de pages peut échouer sur des sites qui bloquent les bots
  ou nécessitent du JavaScript (mode hybride recommandé pour ça).
- Pas de gestion de très longs historiques : au-delà d'un certain
  nombre de messages, pense à démarrer une nouvelle discussion pour
  rester dans la fenêtre de contexte de ton modèle.
