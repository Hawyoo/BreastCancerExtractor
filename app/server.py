"""Production ASGI entrypoint.

Keep the large legacy app module unchanged while composing small feature routers
before the catch-all static-file mount. Windows Portable and Docker should serve
this module rather than importing app.main directly.
"""

from starlette.routing import Mount

from app.main import app
from app.text_learning_api import router as text_learning_router


# app.main ends with a catch-all StaticFiles mount at "/". Temporarily move that
# route to the end so newly composed /api routes remain reachable.
static_mounts = [
    route
    for route in app.router.routes
    if isinstance(route, Mount) and getattr(route, "name", None) == "static"
]
for route in static_mounts:
    app.router.routes.remove(route)

app.include_router(text_learning_router)
app.router.routes.extend(static_mounts)
