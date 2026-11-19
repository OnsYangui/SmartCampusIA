"""SA-28 — create an account from the command line (the first administrator, a manager…).

    uv run python -m app.create_user --email admin@iit.tn --role admin
    uv run python -m app.create_user --email resp@iit.tn --role academic_manager --institution IIT

The password is asked on the terminal (never passed as an argument, so it stays out of the shell
history). Academic and interview managers must be attached to an institution (its code).
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.core.security import ROLES
from app.services import auth

MIN_PASSWORD_LENGTH = 12


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=sorted(ROLES))
    parser.add_argument("--institution", help="institution code (IIT, ISB…), for manager roles")
    args = parser.parse_args()

    from app.core.db import SessionLocal
    from app.models import Institution

    password = getpass.getpass("Mot de passe : ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LENGTH} caractères.")
    if password != getpass.getpass("Confirmation : "):
        sys.exit("Les deux mots de passe sont différents.")

    with SessionLocal() as session, session.begin():
        institution_id = None
        if args.institution:
            institution_id = session.scalar(
                select(Institution.id).where(Institution.code == args.institution.upper())
            )
            if institution_id is None:
                sys.exit(f"Établissement inconnu : {args.institution}")
        if auth.find_by_email(session, args.email) is not None:
            sys.exit("Un compte existe déjà avec cet e-mail.")
        try:
            user = auth.create_user(
                session,
                email=args.email,
                password=password,
                role=args.role,
                institution_id=institution_id,
            )
        except ValueError as error:
            sys.exit(str(error))
        print(f"Compte créé : {user.email} ({user.role}).")


if __name__ == "__main__":
    main()
