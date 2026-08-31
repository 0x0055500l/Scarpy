import asyncio

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI()

# 1. Selector cambiado (Changed selector)
@app.get("/changed-selector", response_class=HTMLResponse)
async def changed_selector():
    return """
    <html><body>
        <div id="new-login-btn">Login</div> <!-- Used to be #login-btn -->
    </body></html>
    """

# 2. Botón renombrado (Renamed button)
@app.get("/renamed-button", response_class=HTMLResponse)
async def renamed_button():
    return """
    <html><body>
        <button id="submit">Continue</button> <!-- Used to be 'Next' -->
    </body></html>
    """

# 3. DOM dinámico (Dynamic DOM)
@app.get("/dynamic", response_class=HTMLResponse)
async def dynamic():
    return """
    <html><body>
        <div id="content">Loading...</div>
        <script>
            setTimeout(() => {
                document.getElementById('content').innerHTML = '<div class="product">Product A - $10</div>';
            }, 3000);
        </script>
    </body></html>
    """

# 4. Página lenta (Slow page)
@app.get("/slow", response_class=HTMLResponse)
async def slow():
    await asyncio.sleep(4)
    return "<html><body><div>Delayed Content</div></body></html>"

# 5. Error 500 (500 Error)
@app.get("/error500")
async def error500():
    return Response("Internal Server Error", status_code=500)

# 6. Redirect (Redirect)
@app.get("/redirect-source")
async def redirect_source():
    return RedirectResponse(url="/redirect-target", status_code=302)

@app.get("/redirect-target", response_class=HTMLResponse)
async def redirect_target():
    return "<html><body><div id='target'>Target reached</div></body></html>"

# 7. Login incorrecto (Invalid login)
@app.get("/login", response_class=HTMLResponse)
async def login(request: Request):
    return """
    <html><body>
        <form method="POST" action="/login">
            <input type="text" name="username">
            <input type="password" name="password">
            <button type="submit">Sign In</button>
        </form>
        <div id="error">Invalid credentials</div>
    </body></html>
    """

# 8. Sesión expirada (Expired session)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    return RedirectResponse(url="/login", status_code=302)

# 9. Elemento desaparece (Disappearing element)
@app.get("/disappearing", response_class=HTMLResponse)
async def disappearing():
    return """
    <html><body>
        <button id="magic" onmouseover="this.remove()">Hover Me</button>
    </body></html>
    """

# 10. Paginación diferente (Different pagination)
@app.get("/infinite-scroll", response_class=HTMLResponse)
async def infinite_scroll():
    return """
    <html><body>
        <div id="items">
            <div class="item">Item 1</div>
        </div>
        <button id="load-more" onclick="document.getElementById('items').innerHTML += '<div class=item>Item X</div>'">Load More</button>
    </body></html>
    """

# 11. Página sin resultados (Empty results)
@app.get("/empty", response_class=HTMLResponse)
async def empty():
    return "<html><body><div class='results'>0 items found</div></body></html>"

# 12. Datos corruptos (Corrupted data)
@app.get("/corrupted", response_class=HTMLResponse)
async def corrupted():
    return "<html><body><div id='data'>{malformed json: true,</div></body></html>"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
