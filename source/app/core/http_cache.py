"""Revalidate unversioned ESM graphs without disabling conditional requests."""


async def revalidate_frontend(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        # A versioned entry module can import unversioned children. Neither may
        # remain fresh for an hour after deployment. Preserve StaticFiles' ETag
        # and Last-Modified headers, including on 304 responses.
        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    elif response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response
