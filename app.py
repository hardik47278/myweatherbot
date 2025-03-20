from flask import Flask,request,make_response
import os
from flask_cors import CORS,cross_origin

app = Flask(__name__)

@app.route('/')
def index():
    return "Web app with python flask"

@app.route('/webhook',method=['POST'])
def webhook():
    req = request.get_json(silent=True,force=True)#getting request from postman
    print("Requst")

    print(json.dumps(req))

    res = object.processRquest(req)

    res = json.dumps(res)
    print(res)
    r = make_response(res)
    r.headers['Content-Type'] = 'application/jsom'   


if __name__ =='__main__':
    app.run(host='127.0.0.1',port=5000)



