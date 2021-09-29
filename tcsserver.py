import socket
import os
from _thread import *
import utils
import logger
from configobj import ConfigObj
import time

class tcsserver:

    def __init__(self, base_directory, config_file, logger=None):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'tcsserver')
        else: self.logger = logger

        # read the config file
        config = ConfigObj(self.config_file)

        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        self.host = config['HOST']
        self.port = int(config['PORT'])
        
        self.tcshost = config['TCSHOST']
        self.tcsport = int(config['TCSPORT'])

        self.dfmsocket = socket.socket()
        self.dfmsocket.connect((self.tcshost,self.tcsport))

        self.lock = False
    
    def threaded_client(self,connection):
        connection.send(str.encode('Welcome to the Server\n'))
        while True:
            data = connection.recv(2048)

            while self.lock:
                self.logger.info("Waiting for another client to finish")
                time.sleep(0.1)
            self.lock = True 
            self.dfmsocket.send(data)
            reply = self.dfmsocket.recv(2048)
            self.lock = False
            
#            reply = 'Server Says: ' + data.decode('utf-8')
            if not data:
                break
#            connection.sendall(str.encode(reply))
            connection.sendall(reply)
        connection.close()

    def listen(self):

        ServerSocket = socket.socket()
        ThreadCount = 0
        try:
            ServerSocket.bind((self.host, self.port))
        except socket.error as e:
            print(str(e))

        self.logger.info('Waiting for a Connection...')
        ServerSocket.listen(5)
        while True:
            Client, address = ServerSocket.accept()
            self.logger.info('Connected to: ' + address[0] + ':' + str(address[1]))
            start_new_thread(self.threaded_client, (Client, ))
            ThreadCount += 1
            self.logger.info('Thread Number: ' + str(ThreadCount))
        ServerSocket.close()

if __name__ == '__main__':
    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-T15':
        base_directory = 'C:/Users/jdeas/Documents/GitHub/tres-guider'
    else:
        print('unsupported system')
        sys.exit()


tcsserver = tcsserver(base_directory,'tcsserver.ini')
tcsserver.listen()

ipdb.set_trace()
