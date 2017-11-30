import sqlalchemy
import pandas as pd
import time
import os
import subprocess

def connect(user, password, db, host='localhost', port=5432):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user, password, host, port, db)
    con = sqlalchemy.create_engine(url, client_encoding='utf8')
    return con

engine = connect('sensor_log', 'sensor1234', 'sensor_log')

engine.execute('create table if not exists test(time timestamptz not null, temp double precision null)')
pd.read_sql("select * from test limit 1", engine)

insert_cmd = 'insert into test(time, temp) values (now(), {});'
delete_cmd = "delete from test where age(now(),time) >= interval '2 hour';"

while (True):
    #f = open("/sys/class/hwmon/hwmon1/temp2_input", 'r')
    f = subprocess.Popen(['/usr/bin/sensortool','3','0'],stdout=subprocess.PIPE).stdout
    temp = f.read()
    f.close()
    temp = temp.split(' ')[2]
    sql_cmd = insert_cmd.format(float(temp))
    engine.execute(sql_cmd)
    time.sleep(5)
    engine.execute(delete_cmd)

