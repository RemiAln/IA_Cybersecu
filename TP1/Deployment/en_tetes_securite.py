"""
TP2 : en-têtes HTTP de sécurité ajoutés à TOUTES les réponses de l'API.

Branché dans api.py juste après la création de l'application :
    app.middleware("http")(ajouter_entetes_securite)

Le nom du serveur (en-tête "server: uvicorn", repéré par le scan nmap) est,
lui, retiré au lancement d'uvicorn (option --no-server-header, Dockerfile).
"""

# Documentation interactive (Swagger) : elle charge des scripts externes, on ne
# lui applique donc pas la politique de contenu stricte.
PAGES_DOC = ("/docs", "/redoc", "/openapi.json")

EN_TETES = {
    "X-Content-Type-Options": "nosniff",       # le navigateur ne devine pas le type du contenu
    "X-Frame-Options": "DENY",                 # l'API ne peut pas être affichée dans une iframe
    "Referrer-Policy": "no-referrer",          # aucune URL transmise à un autre site
    "Cache-Control": "no-store",               # les verdicts ne sont pas gardés en cache
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# L'API ne renvoie que du JSON : aucune ressource ne doit être chargée
CSP_STRICTE = "default-src 'none'; frame-ancestors 'none'"


async def ajouter_entetes_securite(request, call_next):
    """Middleware FastAPI : ajoute les en-têtes de sécurité à la réponse."""
    reponse = await call_next(request)
    for nom, valeur in EN_TETES.items():
        reponse.headers[nom] = valeur
    if not request.url.path.startswith(PAGES_DOC):
        reponse.headers["Content-Security-Policy"] = CSP_STRICTE
    # HSTS (forcer HTTPS) n'est utile qu'une fois l'API en HTTPS : non ajouté ici
    return reponse
