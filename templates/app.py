@app.get("/")
def index():
    return render_template("upload.html")
