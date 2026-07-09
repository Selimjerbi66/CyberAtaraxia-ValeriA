"""
Script de récupération de mot de passe.

À utiliser si tu as oublié ton mot de passe et que tu es bloqué dehors.
Se lance directement sur le serveur (dans le conteneur), donc il n'y a
pas besoin d'email ni de question secrète : si tu as accès au serveur,
tu as le droit de réinitialiser le mot de passe.

Usage (depuis l'hôte, le conteneur doit être démarré) :

    docker exec -it ollama-chat python reset_password.py

Ça va te demander un nouveau mot de passe et déconnecter toutes les
sessions actives par sécurité.
"""
import getpass
import sys

from database import init_db
from auth import set_password, destroy_all_sessions


def main():
    init_db()
    print("=== Réinitialisation du mot de passe ===")
    pw1 = getpass.getpass("Nouveau mot de passe : ")
    if len(pw1) < 6:
        print("Le mot de passe doit faire au moins 6 caractères.")
        sys.exit(1)
    pw2 = getpass.getpass("Confirme le nouveau mot de passe : ")
    if pw1 != pw2:
        print("Les deux mots de passe ne correspondent pas. Rien n'a été changé.")
        sys.exit(1)

    set_password(pw1)
    destroy_all_sessions()
    print("Mot de passe mis à jour avec succès.")
    print("Toutes les sessions actives ont été déconnectées par sécurité.")


if __name__ == "__main__":
    main()
