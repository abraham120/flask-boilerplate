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

input_queue = [multiprocessing.Queue(), multiprocessing.Queue()]
output_queue = [multiprocessing.Queue(), multiprocessing.Queue()]
tempMonRunning = 0
fanRunning = 0

app = Flask(__name__)
app.config.from_object('config')
app.secret_key = "secret"
#db = SQLAlchemy(app)
socketio = SocketIO(app)
thread = None
threadRunning = False
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

def setFanMode(mode):
    for i in range(6):
        os.system('/usr/bin/sensortool 3 ' + str(21+i) + ' ' + str(mode))

def getFanMode(fanid):
    fd = subprocess.Popen(['/usr/bin/sensortool',str(3),str(21+fanid)],stdout=subprocess.PIPE).stdout
    data = fd.read()
    fd.close()
    data = data.split(' ')
    return int(data[2])
    

def initFanPwmMode():
    setFanMode(1)
    for i in range(6):
        #fd = open('/sys/class/hwmon/hwmon4/pwm'+str(i+1)+'_enable','w')
        #fd.write('1')
        #fd.close()
        os.system('/usr/bin/sensortool 3 ' + str(9+i) + ' 0')
    for i in [0,1,4,5]:
        os.system('/usr/bin/sensortool 3 ' + str(9+i) + ' 50')
        #setFanPwm(i,50)

def getFanPwm(fanid):
    #fd = open('/sys/class/hwmon/hwmon4/pwm'+str(fanid+1),'r')
    fd = subprocess.Popen(['/usr/bin/sensortool',str(3),str(9+fanid)],stdout=subprocess.PIPE).stdout
    data = fd.read()
    fd.close()
    data = data.split(' ')
    return int(data[2])

def setFanPwm(fanid,pwm):
    #fd = subprocess.Popen(['/usr/bin/sensortool',3,8+fanid,pwm],stdout=subprocess.PIPE).stdout
    #fd = open('/sys/class/hwmon/hwmon4/pwm'+str(fanid+1),'w')
    #fd.read(str(pwm))
    #fd.close()
    os.system('/usr/bin/sensortool 3 ' + str(9+fanid) + ' ' + str(pwm))

def getFanRpm(fanid):
    #fd = open('/sys/class/hwmon/hwmon4/fan'+str(fanid+1)+'_input','r')
    fd = subprocess.Popen(['/usr/bin/sensortool',str(3),str(3+fanid)],stdout=subprocess.PIPE).stdout
    data = fd.read()
    data = data.split(' ')
    fd.close()
    return int(data[2])

def setFanRpm(fanid,rpm):
    os.system('/usr/bin/sensortool 3 ' + str(15+fanid) + ' ' + str(rpm))

@app.route('/')
def home():
    return sensors()

def parseSensorList(node):
    sensor_list = []
    sensor_tmp = getSensorData(node)

    for data_str in sensor_tmp :
    	sensor_dic = {}
        idxname = data_str.split(':')
        if len(idxname) == 2:
       	    sensor_dic['value'] = idxname[1]
        else:
            sensor_dic['value'] = ''
        idxname = idxname[0]
        if len(idxname) == 0:
            break
        if idxname[0] == '[':
            sensor_dic['index'] = idxname.split(']')[0][1:]
            sensor_dic['name'] = idxname.split(']')[1][1:]
        else:
            sensor_dic['index'] = ''
            sensor_dic['name'] = idxname
        sensor_list.append(sensor_dic)

    return sensor_list
            

@app.route('/sensors')
def sensors():
    sensor_node1 = parseSensorList('1')
    sensor_node2 = parseSensorList('2')
    sensor_bmc = parseSensorList('3')

    status = runPowerTool(['status'])
    status1 = status.split('\n')[0].split(':')[1].strip()
    status2 = status.split('\n')[1].split(':')[1].strip()

    return render_template('pages/placeholder.sensors.html', sensor_node1=sensor_node1, sensor_node2=sensor_node2, sensor_bmc=sensor_bmc, status1=status1, status2=status2)


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
            runPowerTool(['forceoff'])

    status = runPowerTool(['status'])
    status1 = status.split('\n')[0].split(':')[1].strip()
    status2 = status.split('\n')[1].split(':')[1].strip()

    return render_template('pages/placeholder.power.html', status1=status1, status2=status2)

@app.route('/tempmon')
def tempmon():
    status = runPowerTool(['status'])
    status1 = status.split('\n')[0].split(':')[1].strip()
    status2 = status.split('\n')[1].split(':')[1].strip()
    return render_template('pages/placeholder.temp.html', status1=status1, status2=status2)

@app.route('/fanctrl')
def fanctrl():
    return render_template('pages/placeholder.fan.html')

@app.route('/terminal')
def terminal():
    status = runPowerTool(['status'])
    status1 = status.split('\n')[0].split(':')[1].strip()
    status2 = status.split('\n')[1].split(':')[1].strip()
    return render_template('pages/placeholder.console.html', status1=status1, status2=status2)


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

@socketio.on('connect', namespace='/term')
def connect():
    global thread
    global threadRunning
    print('term-socket : connected')
    if thread is None:
        threadRunning = True
        thread = Thread(target=checkQueue)
        thread.start()
    result = runPowerTool(['consolestat'])
    result1 = result.split('\n')[0].split(':')[1]
    result2 = result.split('\n')[1].split(':')[1]
    socketio.emit("setting", {'node1':result1, 'node2':result2}, namespace='/term')

@socketio.on('setting', namespace='/term')
def term_setup(message):
    print(str(message['node']) + ":" + message['cmd'].encode("utf-8"));
    n = message['node']
    if n == 0 or n == 1:
        node = str(n+1)
        cmd = message['cmd'].encode("utf-8")
        if cmd == 'on':
            runPowerTool(['consoleon', node])
        elif cmd == 'off':
            runPowerTool(['consoleoff', node])
    result = runPowerTool(['consolestat'])
    result1 = result.split('\n')[0].split(':')[1]
    result2 = result.split('\n')[1].split(':')[1]
    socketio.emit("setting", {'node1':result1, 'node2':result2}, namespace='/term')

@socketio.on('disconnect', namespace='/term')
def disconnect():
    global thread
    global threadRunning
    if thread is not None:
        threadRunning = False
        thread = None

@socketio.on('input', namespace='/term')
def term_input(message):
    #print('input:' + str(message['node']) + message['data'].encode("utf-8"))
    input_queue[message['node']].put(message['data'].encode("UTF-8"))

@socketio.on('connect', namespace='/fan')
def connect():
    global fanRunning

    print("fan-ws: connected")
# send all of data
    for i in range(6):
        pwm = getFanPwm(i)
        socketio.emit("data", {'fanid':i+1,'value':pwm}, namespace='/fan')
        rpm = getFanRpm(i)
        socketio.emit("rpmData", {'fanid':i+1,'rpm':rpm}, namespace='/fan')
    mode = getFanMode(0)
    if (mode == 2):
        mode = 'on'
    else:
        mode = 'off'
    socketio.emit("fanmode", {'mode':mode}, namespace='/fan')
    fanRunning += 1
    if fanRunning == 1:
        Thread(target=broadcastFanRpm).start()

@socketio.on('disconnect', namespace='/fan')
def disconnect():
    global fanRunning
    if fanRunning > 0: 
        fanRunning -= 1
    print("fan-ws: disconnected")

@socketio.on('request', namespace='/fan')
def request_mon(message):
    print("fan-ws: request")
    setFanPwm(message['fanid'], message['pwm'])

@socketio.on('fanmode_toggle', namespace='/fan')
def fanmode_toggle(message):
    mode = getFanMode(0)
    if (mode == 2):
        setFanMode(1)
        mode = 'off'
    else:
        setFanMode(2)
        mode = 'on'
    socketio.emit("fanmode", {'mode':mode}, namespace='/fan')

@socketio.on('connect', namespace='/mon')
def connect():
    global db_engine
    global tempMonRunning
    print("mon-ws: connected")
# connect to db
    if db_engine is None:
        url = 'postgresql://{}:{}@localhost:5432/{}'
        url = url.format('sensor_log', 'sensor1234', 'sensor_log')
        db_engine = sqlalchemy.create_engine(url, client_encoding='utf8')
    db_data = pandas.read_sql('select * from test order by time desc limit 100', db_engine)
# send all of data
    for i in range(db_data.index.max()+1):
        socketio.emit("data", {'tempBMC':db_data.tempbmc[db_data.index.max()-i],'tempNODE1':db_data.tempnode1[db_data.index.max()-i],'tempNODE2':db_data.tempnode2[db_data.index.max()-i]}, namespace='/mon')
    tempMonRunning = tempMonRunning + 1 
    if tempMonRunning == 1:
        Thread(target=broadcastTemp).start()

@socketio.on('disconnect', namespace='/mon')
def disconnect():
    global tempMonRunning
    print("mon-ws: disconnected")
    if tempMonRunning > 0:
        tempMonRunning = tempMonRunning - 1

@socketio.on('request', namespace='/mon')
def request_mon(message):
    print("mon-ws: request")

@socketio.on('connect', namespace='/ws')
def connect():
    print("websock: connected")

@socketio.on('disconnect', namespace='/ws')
def disconnect():
    print("websock: disconnected")

#----------------------------------------------------------------------------#
# Launch.
#----------------------------------------------------------------------------#

def broadcastFanRpm():
    global fanRunning
    while fanRunning > 0:
        time.sleep(1)
        for i in range(6):
	    rpm = getFanRpm(i)
	    socketio.emit("rpmData", {'fanid':i+1,'rpm':rpm}, namespace='/fan')
        
def broadcastTemp():
    global tempMonRunning
    while tempMonRunning > 0:
        time.sleep(5)
        db_data = pandas.read_sql('select * from test order by time desc limit 1', db_engine)
        socketio.emit("data", {'tempBMC':db_data.tempbmc[0],'tempNODE1':db_data.tempnode1[0]}, namespace='/mon')
        
def checkQueue():
    global threadRunning
    while threadRunning:
        time.sleep(0.001)
        for node in range(2):
            if not output_queue[node].empty():
                message = output_queue[node].get()
                #print("send: " + message)
                socketio.emit("output", {'node':node,'buf':message}, namespace='/term')
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

    socketio.run(app, host='0.0.0.0', port=5000, use_reloader=False)

# Or specify port manually:
'''
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
'''
