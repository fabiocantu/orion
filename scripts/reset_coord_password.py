from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import database_label, execute, query_one  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redefine a senha do usuario de coordenacao.")
    parser.add_argument("--login", default="coord", help="Nome ou e-mail do usuario de coordenacao. Padrao: coord")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    login = args.login.strip().lower()
    if not login:
        raise SystemExit("Informe um login valido.")

    user = query_one(
        """
        SELECT id, name, email, role
        FROM users
        WHERE role = 'coordenacao'
          AND (lower(name) = ? OR lower(email) = ?)
        """,
        (login, login),
    )
    if not user:
        raise SystemExit(f"Usuario de coordenacao nao encontrado para login: {args.login}")

    password = getpass.getpass("Nova senha da coordenacao: ").strip()
    confirmation = getpass.getpass("Confirmar nova senha: ").strip()
    if password != confirmation:
        raise SystemExit("As senhas nao conferem.")
    if len(password) < 4:
        raise SystemExit("A senha deve ter pelo menos 4 caracteres.")

    execute("UPDATE users SET password = ? WHERE id = ?", (password, user["id"]))
    print(f"Senha redefinida para {user['name']} ({user['email']}) em {database_label()}.")


if __name__ == "__main__":
    main()
