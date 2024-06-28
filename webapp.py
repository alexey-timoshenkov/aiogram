from flask import Flask, request, url_for, render_template

app = Flask(__name__)

@app.route("/")
def index():
   c = 1
   c += 1
   c += 1
   print(c)
   return render_template("index.html")

if __name__ == "__main__":
   app.run(debug=False)