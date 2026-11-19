# Authentification et rôles (SA-28)

Implémente les routes `/auth/*` et les règles d'accès de SA-5 : connexion, renouvellement,
déconnexion, protection CSRF et contrôle des rôles.

## Principe

| Élément | Choix |
| --- | --- |
| Mots de passe | Argon2id (`argon2-cffi`), re-hachage automatique si les paramètres changent |
| Session | JWT signé HS256 dans un cookie `HttpOnly`, `SameSite=Lax`, `Secure` hors développement |
| Access token | 15 min (`ACCESS_TOKEN_MINUTES`), contient `sub`, `role`, `inst`, `sid` |
| Refresh token | 7 jours (`REFRESH_TOKEN_DAYS`), cookie limité au chemin `/api/v1/auth` |
| CSRF | cookie `csrf_token` lisible par le JS, à renvoyer dans l'en-tête `X-CSRF-Token` |
| Rôle et établissement | lus dans le JWT, jamais dans la requête |

Le jeton CSRF est un HMAC de l'identifiant de session (`sid`) : il ne peut pas être fabriqué sans
`JWT_SECRET_KEY`, et il reste le même pendant toute la session.

## Routes

| Route | Rôle | Effet |
| --- | --- | --- |
| `POST /auth/login` | public | `{email, password}` → pose les 3 cookies, renvoie le compte. 401 identique pour e-mail inconnu, mauvais mot de passe et compte désactivé |
| `POST /auth/refresh` | cookie refresh + CSRF | nouveaux jetons ; rôle et établissement relus en base, compte désactivé refusé |
| `POST /auth/logout` | public | supprime les cookies (204) |
| `GET /auth/me` | connecté | compte courant |

## Protéger une route

```python
from fastapi import Depends
from app.api.security import PrincipalDep, require_roles
from app.core.security import ADMIN, MANAGEMENT

@router.get("/stats/pending", dependencies=[Depends(require_roles(MANAGEMENT))])
def pending(): ...

@router.get("/applications/{id}")
def application(id: uuid.UUID, principal: PrincipalDep): ...   # principal.role, .institution_id
```

Sans cookie valide : 401. Mauvais rôle ou CSRF absent sur une écriture : 403. Le filtre par
établissement (RM-09) reste à appliquer dans les services avec `principal.can_manage(...)`.

## Configuration

| Variable | Rôle |
| --- | --- |
| `JWT_SECRET_KEY` | 32 caractères minimum. Facultative en développement (secret aléatoire par processus), **obligatoire** en staging et production |
| `ACCESS_TOKEN_MINUTES`, `REFRESH_TOKEN_DAYS` | durées de vie |
| `COOKIE_SECURE` | `true`/`false` ; par défaut `true` hors développement |
| `DEMO_PASSWORD` | développement uniquement : mot de passe des comptes de démonstration |

## Comptes

- Démonstration : renseigner `DEMO_PASSWORD`, puis `uv run python -m app.seed`. Comptes :
  `admin@example.com`, `direction@example.com`, `resp.academique.iit@example.com`,
  `resp.entretien.iit@example.com`, `candidat.c04@example.com` (et c05 à c13).
- Réels : `uv run python -m app.create_user --email admin@iit.tn --role admin`
  (ajouter `--institution IIT` pour un responsable académique ou entretien). Le mot de passe est
  demandé au clavier, 12 caractères minimum.

## Appeler l'API depuis le frontend

```ts
const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/)?.[1] ?? ""
await fetch("/api/v1/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password }),
})
await fetch("/api/v1/manage/programs", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
  body: JSON.stringify(payload),
})
```

Les cookies passent par le proxy Next.js (même origine), aucun `credentials` spécial n'est requis.

## Frontend (page de connexion)

- `/login` : formulaire e-mail + mot de passe, valable pour les cinq rôles. Après connexion, chaque
  acteur arrive dans son espace : candidat → `/candidat`, responsable académique, direction et
  administrateur → `/dashboard`, responsable entretien → `/entretiens`. Le paramètre `?next=` ramène
  à la page demandée (chemins du site uniquement, pas de redirection externe).
- En développement, la page propose des boutons qui pré-remplissent l'e-mail des comptes de démo.
- `lib/auth.ts` : `login`, `logout`, `fetchCurrentUser` et `apiFetch`, qui ajoute l'en-tête
  `X-CSRF-Token` aux écritures et renouvelle la session une fois si l'API répond 401.
  **Toute future requête vers l'API doit passer par `apiFetch`.**
- `components/auth-provider.tsx` : contexte `useAuth()` (utilisateur courant, `signIn`, `signOut`).
  Rien n'est stocké dans le navigateur : l'état vient des cookies.
- `components/require-role.tsx` : `<RequireRole roles={["admin"]}>` redirige vers `/login` si la
  personne n'est pas connectée, et affiche « Accès refusé » si son rôle n'est pas autorisé.
  C'est un confort d'affichage : la vraie protection reste celle de l'API.

## Limites connues

- Pas de limitation du nombre de tentatives de connexion (à prévoir avec un cache partagé).
- Les refresh tokens sont sans état : la déconnexion supprime les cookies mais ne révoque pas un
  jeton déjà copié avant son expiration. Un compte désactivé est bloqué au prochain refresh.
- Pas encore de journal des connexions dans `audit_logs`.
- Le chat reste public (visiteurs sans compte, SA-24) ; l'inscription d'un candidat depuis le site
  (`POST /applications`) n'est pas encore faite.
