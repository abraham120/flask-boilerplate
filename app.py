#----------------------------------------------------------------------------#
# Imports
#----------------------------------------------------------------------------#

from gevent import monkey
#monkey.patch_all()
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
# from flask.ext.sqlalchemy import SQLAlchemy
import logging
from logging import Formatter, FileHandler
from forms import *
import os
import time
import subprocess
import multiprocessing
import serialworker
from threading import Thread

import sqlalchemy
import pandas

#----------------------------------------------------------------------------#
# App Config.
#----------------------------------------------------------------------------#

input_queue = multiprocessing.Queue()
output_queue = multiprocessing.Queue()

app = Flask(__name__)
app.config.from_object('config')
app.secret_key = "secret"
#db = SQLAlchemy(app)
socketio = SocketIO(app)
thread = None
sp = None
db_engine = None
# Automatically tear down SQLAlchemy.
'''
@app.teardown_request
def shutdown_session(exception=None):
    db_session.remove()
'''

# Login required decorator.
'''
def login_required(test):
    @wraps(test)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return test(*args, **kwargs)
        else:
            flash('You need to login first.')
            return redirect(url_for('login'))
    return wrap
'''
#----------------------------------------------------------------------------#
# Controllers.
#----------------------------------------------------------------------------#

def getSensorData(node_number):
    fd = subprocess.Popen(['/usr/bin/sensortool',node_number],stdout=subprocess.PIPE).stdout
    data = fd.read()
    fd.close()
    return data.split('\n')

def runPowerTool(args):
    cmd = ['/usr/bin/powertool'] + args
    fd = subprocess.Popen(cmd, stdout=subprocess.PIPE).stdout
    data = fd.read()
    fd.close()
    return data

def initFanPwmMode():
    for i in range(6):
        fd = open('/sys/class/hwmon/hwmon4/pwm'+str(i+1)+'_enable','w')
        fd.write('1')
        fd.close()
        setFanPwm(i,50)

def getFanPwm(fanid):
    fd = open('/sys/class/hwmon/hwmon4/pwm'+str(fanid+1),'r')
    data = fd.read()
    fd.close()
    return int(data)

def setFanPwm(fanid,pwm):
    fd = open('/sys/class/hwmon/hwmon4/pwm'+str(fanid+1),'w')
    fd.write(str(pwm))
    fd.close()

def getFanRpm(fanid):
    fd = open('/sys/class/hwmon/hwmon4/fan'+str(fanid+1)+'_input','r')
    data = fd.read()
    fd.close()
    return int(data)

@app.route('/')
def home():
    return render_template('pages/placeholder.home.html', node_name='Node 1')

@app.route('/node/<node_number>')
def node(node_number):
    if node_number == '1' or node_number == '2':
        node_name = 'Node ' + node_number
    elif node_number == '3':
        node_name = 'BMC'
    else:
        return render_template('errors/404.html'), 404

    return render_template('pages/placeholder.home.html', node_number=node_number, node_name=node_name, messages=getSensorData(node_number))

@app.route('/power', methods=['GET', 'POST'])
def power():
    if request.method == 'POST':
        power_control = request.form['power']
        if power_control == 'Power On':
            ''' power on '''
            print('power on')
            runPowerTool(['poweron'])
        elif power_control == 'Power Off':
            ''' power off '''
            print('power off')
            runPowerTool(['poweroff'])
        elif power_control == 'Power Force Off':
            ''' power force off '''
            print('power force off')
            runPowerTool(['poweroff','force'])

    status = runPowerTool(['status','2'])
    status = status.split(':')[1]

    return render_template('pages/placeholder.power.html', status=status)

@app.route('/tempmon')
def tempmon():
    return render_template('pages/placeholder.temp.html')

@app.route('/fanctrl')
def fanctrl():
    return render_template('pages/placeholder.fan.html')

@app.route('/terminal')
def terminal():
    global thread
    if thread is None:
        thread = Thread(target=checkQueue)
        thread.start()
    return render_template('pages/placeholder.console.html')


@app.route('/about')
def about():
    return render_template('pages/placeholder.about.html')


@app.route('/login')
def login():
    form = LoginForm(request.form)
    return render_template('forms/login.html', form=form)


@app.route('/register')
def register():
    form = RegisterForm(request.form)
    return render_template('forms/register.html', form=form)


@app.route('/forgot')
def forgot():
    form = ForgotForm(request.form)
    return render_template('forms/forgot.html', form=form)

# Error handlers.


@app.errorhandler(500)
def internal_error(error):
    #db_session.rollback()
    return render_template('errors/500.html'), 500


@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

if not app.debug:
    file_handler = FileHandler('error.log')
    file_handler.setFormatter(
        Formatter('%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')
    )
    app.logger.setLevel(logging.INFO)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.info('errors')

@socketio.on('connect', namespace='/fan')
def connect():
    print("fan-ws: connected")
# send all of data
    for i in range(6):
        pwm = getFanPwm(i)
        socketio.emit("data", {'fanid':i+1,'value':pwm}, namespace='/fan')
        rpm = getFanRpm(i)
        socketio.emit("rpmData", {'fanid':i+1,'rpm':rpm}, namespace='/fan')
        

@socketio.on('disconnect', namespace='/fan')
def disconnect():
    print("fan-ws: disconnected")

@socketio.on('request', namespace='/fan')
def request_mon(message):
    print("fan-ws: request")
    setFanPwm(message['fanid'], message['pwm'])

@socketio.on('rpmRequest', namespace='/fan')
def request_mon(message):
    print("fan-ws: rpm request")
    for i in range(6):
        rpm = getFanRpm(i)
        socketio.emit("rpmData", {'fanid':i+1,'rpm':rpm}, namespace='/fan')

@socketio.on('connect', namespace='/mon')
def connect():
    global db_engine
    print("mon-ws: connected")
# connect to db
    if db_engine is None:
        url = 'postgresql://{}:{}@localhost:5432/{}'
        url = url.format('sensor_log', 'sensor1234', 'sensor_log')
        db_engine = sqlalchemy.create_engine(url, client_encoding='utf8')
    db_data = pandas.read_sql('select * from test order by time desc limit 100', db_engine)
# send all of data
    for i in range(db_data.index.max()+1):
        socketio.emit("data", {'temp':db_data.temp[db_data.index.max()-i]}, namespace='/mon')

@socketio.on('disconnect', namespace='/mon')
def disconnect():
    print("mon-ws: disconnected")

@socketio.on('request', namespace='/mon')
def request_mon(message):
    print("mon-ws: request")
    db_data = pandas.read_sql('select * from test order by time desc limit 1', db_engine)
    socketio.emit("data", {'temp':db_data.temp[0]}, namespace='/mon')

@socketio.on('connect', namespace='/ws')
def connect():
    print("websock: connected")

@socketio.on('disconnect', namespace='/ws')
def disconnect():
    print("websock: disconnected")

@socketio.on('request', namespace='/ws')
def request_ws(message):
    print("websock: request: " + message['data'])
    input_queue.put(message['data'].encode("UTF-8"))

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

def checkQueue():
    while True:
        time.sleep(0.01)
        if not output_queue.empty():
            message = output_queue.get()
            print("send: " + message)
            socketio.emit("response", {'data':message}, namespace='/ws')
            eventlet.sleep(0)
        if not sp.is_alive():
            break

# Default port:
if __name__ == '__main__':
    #app.run('0.0.0.0')
    print('start')
    sp = serialworker.SerialProcess(input_queue, output_queue)
    sp.daemon = True
    sp.start()
    
    initFanPwmMode()
    runPowerTool(['console_on','2'])

    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False)

# Or specify port manually:
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
