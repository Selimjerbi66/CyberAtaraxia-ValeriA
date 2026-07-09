"""
Client minimal pour l'API Ollama : liste des modèles disponibles et
génération de réponse en streaming (token par token).
"""
import json
import requests


def needs_web_search(ollama_url: str, model: str, message: str) -> bool:
    """
    Appel rapide et separe au modele pour decider si la question necessite
    une recherche web (actualite, faits recents, donnees changeantes,
    informations specifiques) ou si c'est une conversation normale
    (salutations, remerciements, culture generale stable, questions sur
    l'assistant lui-meme) qui n'en a pas besoin.

    C'est une version simplifiee du "tool calling" utilise par Claude/
    ChatGPT/Grok : eux laissent le modele decider lui-meme d'invoquer un
    outil de recherche ; ici on isole cette decision dans un appel court
    et rapide (quelques tokens de reponse) avant de lancer le pipeline
    complet de recherche+scraping.
    """
    classification_prompt = (
        "Reponds uniquement par un seul mot : OUI ou NON. "
        "Question : est-ce que le message suivant necessite une recherche web "
        "pour y repondre correctement (actualite, evenement recent, "
        "information specifique changeante, prix, meteo, resultat sportif, "
        "fait que tu ne connais pas avec certitude) ? "
        "Reponds NON pour les salutations, le small talk, les remerciements, "
        "les questions de culture generale stable, les questions sur "
        "l'assistant lui-meme, ou toute conversation normale qui ne demande "
        "pas d'information a jour.\n\n"
        f"Message : \"{message}\"\n\n"
        "Reponds uniquement OUI ou NON, rien d'autre."
    )
    try:
        resp = requests.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": classification_prompt}],
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 5},
            },
            timeout=15,
        )
        resp.raise_for_status()
        answer = resp.json().get("message", {}).get("content", "").strip().upper()
        return answer.startswith("OUI") or answer.startswith("YES")
    except Exception:
        # En cas de doute (ex: Ollama indisponible), on part du principe
        # qu'une recherche pourrait aider plutot que de risquer une reponse
        # hors-sujet sans aucun contexte.
        return True


def list_models(ollama_url: str) -> list[str]:
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def stream_chat(ollama_url: str, model: str, messages: list[dict], temperature: float = 0.7):
    """
    Genere les tokens de reponse au fur et a mesure.
    `messages` suit le format Ollama : [{"role": "user"|"assistant"|"system", "content": "..."}]
    """
    with requests.post(
        f"{ollama_url}/api/chat",
        json={
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": temperature},
        },
        stream=True,
        timeout=300,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line.decode("utf-8"))
            content_piece = chunk.get("message", {}).get("content", "")
            if content_piece:
                yield content_piece
            if chunk.get("done"):
                break
