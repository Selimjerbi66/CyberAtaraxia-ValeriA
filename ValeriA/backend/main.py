import json
import time
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

import database as db
import auth
import search_engine
import ollama_client

app = FastAPI(title="ClaudiA - Ollama Web Search Chat")


class NoCacheMiddleware(BaseHTTPMiddleware):
    """Empeche le navigateur de mettre en cache index.html/app.js/style.css.
    Sans ca, une mise a jour du code peut ne pas s'appliquer visuellement
    tant que l'utilisateur ne vide pas son cache manuellement."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response


app.add_middleware(NoCacheMiddleware)

COOKIE_NAME = "session_token"


def build_system_prompt(custom_instructions: str) -> str:
    base = (
        "Tu es un assistant IA utile et honnete. Pour repondre a la question de "
        "l'utilisateur, on t'a fourni des resultats de recherche web recents "
        "ci-dessous, numerotes [1], [2], etc. Utilise-les en priorite pour "
        "repondre, surtout pour tout ce qui concerne l'actualite, les faits "
        "recents ou les informations que tu ne connais pas avec certitude. Si "
        "les resultats ne contiennent pas l'information demandee, dis-le "
        "clairement au lieu d'inventer une reponse. Quand tu utilises une "
        "source, cite son numero entre crochets directement dans le texte, "
        "par exemple [1] ou [2][3].\n\n"
        "Regle de langue : reponds TOUJOURS dans la meme langue que la langue "
        "dominante de la conversation (c'est-a-dire la langue utilisee dans la "
        "majorite des messages precedents et du message actuel), SAUF si "
        "l'utilisateur demande explicitement une reponse dans une langue "
        "specifique (par exemple \"reponds en anglais\"), auquel cas tu suis "
        "cette demande explicite pour ce message."
    )
    if custom_instructions and custom_instructions.strip():
        base += "\n\nInstructions personnalisees de l'utilisateur (a respecter en priorite) :\n" + custom_instructions.strip()
    return base


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    db.init_db()


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def require_auth(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not auth.is_session_valid(token):
        raise HTTPException(status_code=401, detail="Non authentifie")
    return token


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

class LoginBody(BaseModel):
    password: str


class SetupBody(BaseModel):
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


@app.get("/api/auth/status")
def auth_status(request: Request):
    needs_setup = not auth.has_password_set()
    token = request.cookies.get(COOKIE_NAME)
    authenticated = auth.is_session_valid(token)
    return {"needs_setup": needs_setup, "authenticated": authenticated}


@app.post("/api/auth/setup")
def setup_password(body: SetupBody):
    if auth.has_password_set():
        raise HTTPException(status_code=400, detail="Un mot de passe est deja configure")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (6 caracteres min)")
    auth.set_password(body.password)
    token = auth.create_session()
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


@app.post("/api/auth/login")
def login(body: LoginBody):
    if not auth.verify_password(body.password):
        raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    token = auth.create_session()
    resp = JSONResponse({"ok": True})
    resp.set_cookie(COOKIE_NAME, token, httponly=True, max_age=60 * 60 * 24 * 30, samesite="lax")
    return resp


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        auth.destroy_session(token)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordBody, _=Depends(require_auth)):
    if not auth.verify_password(body.old_password):
        raise HTTPException(status_code=401, detail="Ancien mot de passe incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (6 caracteres min)")
    auth.set_password(body.new_password)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

class CreateChatBody(BaseModel):
    title: Optional[str] = "Nouvelle discussion"


class RenameChatBody(BaseModel):
    title: str


class PinBody(BaseModel):
    pinned: bool


class ModelOverrideBody(BaseModel):
    model: Optional[str] = None  # None = revient au modele global


@app.get("/api/chats")
def get_chats(search: str = "", _=Depends(require_auth)):
    return db.list_chats(search)


@app.post("/api/chats")
def new_chat(body: CreateChatBody, _=Depends(require_auth)):
    chat_id = db.create_chat(body.title or "Nouvelle discussion")
    return {"id": chat_id}


@app.get("/api/chats/{chat_id}/messages")
def get_messages(chat_id: int, _=Depends(require_auth)):
    return db.list_messages(chat_id)


@app.patch("/api/chats/{chat_id}")
def rename_chat(chat_id: int, body: RenameChatBody, _=Depends(require_auth)):
    db.rename_chat(chat_id, body.title)
    return {"ok": True}


@app.patch("/api/chats/{chat_id}/pin")
def pin_chat(chat_id: int, body: PinBody, _=Depends(require_auth)):
    db.set_pinned(chat_id, body.pinned)
    return {"ok": True}


@app.patch("/api/chats/{chat_id}/model")
def set_chat_model(chat_id: int, body: ModelOverrideBody, _=Depends(require_auth)):
    db.set_model_override(chat_id, body.model)
    return {"ok": True}


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: int, _=Depends(require_auth)):
    db.delete_chat(chat_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackBody(BaseModel):
    feedback: Optional[str] = None  # 'up' | 'down' | None


@app.patch("/api/messages/{message_id}/feedback")
def set_feedback(message_id: int, body: FeedbackBody, _=Depends(require_auth)):
    db.set_feedback(message_id, body.feedback)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def get_settings(_=Depends(require_auth)):
    return db.get_settings()


@app.post("/api/settings")
def save_settings(body: dict, _=Depends(require_auth)):
    db.update_settings(body)
    return {"ok": True}


@app.get("/api/models")
def get_models(_=Depends(require_auth)):
    settings = db.get_settings()
    models = ollama_client.list_models(settings.get("ollama_url", "http://localhost:11434"))
    return {"models": models}


# ---------------------------------------------------------------------------
# Chat streaming (SearXNG -> scraping parallele -> Ollama)
# ---------------------------------------------------------------------------

class ChatStreamBody(BaseModel):
    chat_id: int
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _run_generation(chat_id: int, user_message: str, history: list, settings: dict):
    """Generateur partage entre l'envoi normal et la regeneration."""
    chat = db.get_chat(chat_id)
    model = (chat.get("model_override") if chat else None) or settings.get("ollama_model", "gemma3:4b")
    temperature = float(settings.get("temperature", 0.7))
    ollama_url = settings.get("ollama_url", "http://localhost:11434")
    auto_detect = settings.get("auto_detect_search", "true") == "true"

    sources = []
    t_search = 0.0
    do_search = True

    if auto_detect:
        yield _sse("status", {"phase": "thinking", "label": "Analyse de la question…"})
        do_search = ollama_client.needs_web_search(ollama_url, model, user_message)

    if do_search:
        yield _sse("status", {"phase": "searching", "label": "Recherche web en cours…"})
        t_start = time.time()
        try:
            sources = search_engine.build_search_context(user_message, settings)
        except Exception as e:
            yield _sse("error", {"message": str(e)})
            return
        t_search = time.time() - t_start

    yield _sse("sources", {"sources": [
        {"title": s["title"], "url": s["url"], "method": s["method"]} for s in sources
    ]})
    yield _sse("status", {"phase": "generating", "label": "Generation de la reponse…"})

    context_blocks = []
    for i, s in enumerate(sources, 1):
        if s["content"]:
            context_blocks.append(f"[{i}] {s['title']} ({s['url']})\n{s['content']}")

    system_prompt = build_system_prompt(settings.get("custom_instructions", ""))
    messages = [{"role": "system", "content": system_prompt}]
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})

    if context_blocks:
        context_text = "\n\n".join(context_blocks)
        user_content = f"Question : {user_message}\n\nResultats de recherche web :\n{context_text}"
    else:
        # Pas de recherche effectuee (ou aucun resultat exploitable) :
        # on envoie juste la question, sans bloc de contexte web qui
        # polluerait une conversation normale avec des resultats hors-sujet.
        user_content = user_message

    messages.append({"role": "user", "content": user_content})

    full_response = ""
    token_count = 0
    t_gen_start = time.time()
    try:
        for piece in ollama_client.stream_chat(ollama_url, model, messages, temperature):
            full_response += piece
            token_count += 1
            yield _sse("token", {"content": piece})
    except Exception as e:
        yield _sse("error", {"message": f"Erreur Ollama : {e}"})
        if not full_response:
            return
    gen_seconds = time.time() - t_gen_start

    simple_sources = [
        {"title": s["title"], "url": s["url"], "method": s["method"]} for s in sources
    ]
    db.add_message(chat_id, "assistant", full_response, simple_sources, gen_seconds, token_count)
    db.touch_chat(chat_id)

    yield _sse("stats", {
        "search_seconds": round(t_search, 2),
        "gen_seconds": round(gen_seconds, 2),
        "tokens": token_count,
        "tokens_per_sec": round(token_count / gen_seconds, 1) if gen_seconds > 0 else 0,
        "model": model,
    })
    yield _sse("done", {})


@app.post("/api/chat/stream")
def chat_stream(body: ChatStreamBody, _=Depends(require_auth)):
    chat_id = body.chat_id
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message vide")

    settings = db.get_settings()
    history = db.list_messages(chat_id)
    db.add_message(chat_id, "user", user_message)

    # Renomme immediatement la discussion des le premier message, INDEPENDAMMENT
    # du succes de la recherche/generation qui suit (evite que ca ne marche pas
    # si SearXNG ou Ollama sont indisponibles).
    if len(history) == 0:
        auto_title = user_message[:50] + ("…" if len(user_message) > 50 else "")
        db.rename_chat(chat_id, auto_title)

    return StreamingResponse(
        _run_generation(chat_id, user_message, history, settings),
        media_type="text/event-stream",
    )


@app.post("/api/chat/regenerate/{chat_id}")
def regenerate(chat_id: int, _=Depends(require_auth)):
    """Supprime la derniere reponse assistant et la regenere."""
    messages = db.list_messages(chat_id)
    if not messages or messages[-1]["role"] != "assistant":
        raise HTTPException(status_code=400, detail="Rien a regenerer")

    # dernier message utilisateur = celui juste avant la derniere reponse
    last_user = None
    for m in reversed(messages[:-1]):
        if m["role"] == "user":
            last_user = m
            break
    if not last_user:
        raise HTTPException(status_code=400, detail="Aucun message utilisateur trouve")

    db.delete_last_assistant_message(chat_id)
    history = db.list_messages(chat_id)[:-1]  # tout sauf le dernier message utilisateur
    settings = db.get_settings()

    return StreamingResponse(
        _run_generation(chat_id, last_user["content"], history, settings),
        media_type="text/event-stream",
    )


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

import os as _os
FRONTEND_DIR = _os.environ.get("FRONTEND_DIR", "/app/frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
