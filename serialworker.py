import serial
import time
import multiprocessing

## Change this to match your local settings
SERIAL_PORT = '/dev/ttymxc0'	## node1
#SERIAL_PORT = '/dev/ttymxc1'	## node2
SERIAL_BAUDRATE = 115200

class SerialProcess(multiprocessing.Process):
 
    def __init__(self, input_queue, output_queue):
        multiprocessing.Process.__init__(self)
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.sp = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
 
    def close(self):
        self.sp.close()
 
    def writeSerial(self, data):
        self.sp.write(data)
        # time.sleep(1)
        
    def readSerial(self):
        return self.sp.read()
 
    def run(self):
 
    	self.sp.flushInput()
 
        while True:
            time.sleep(0.001)
            # look for incoming tornado request
            if not self.input_queue.empty():
                data = self.input_queue.get()
 
                # send it to the serial device
                self.writeSerial(data)
 
            data = ''
            i = 0
            # look for incoming serial data
            waitlen = self.sp.inWaiting()
            while (waitlen > 0 and i < 1024):
            	data += self.sp.read(waitlen)
            	i += waitlen
                waitlen = self.sp.inWaiting()

            if data is not '':
                # send it back to tornado
            	self.output_queue.put(data)

