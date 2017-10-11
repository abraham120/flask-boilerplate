import sqlalchemy
import pandas as pd
import time
import os

def connect(user, password, db, host='localhost', port=5432):
    url = 'postgresql://{}:{}@{}:{}/{}'
    url = url.format(user, password, host, port, db)
    con = sqlalchemy.create_engine(url, client_encoding='utf8')
    return con

engine = connect('sensor_log', 'sensor1234', 'sensor_log')

engine.execute('create table if not exists test(time timestamptz not null, temp double precision null)')
pd.read_sql("select * from test limit 1", engine)

insert_cmd = 'insert into test(time, temp) values (now(), {});'

while (True):
    f = open("/sys/class/hwmon/hwmon1/temp2_input", 'r')
    temp = f.read()
    f.close()
    sql_cmd = insert_cmd.format(float(temp)/1000)
    engine.execute(sql_cmd)
    time.sleep(5)

