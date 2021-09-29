import socket
import os
from _thread import *
import utils
import logger
import time
from configobj import ConfigObj

''' this is a simulated dfm server'''
class dfmserver:

    def __init__(self, base_directory, config_file, logger=None):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'dfmserver')
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
    
    def listen(self):

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            conn, addr = s.accept()
            with conn:
                self.logger.info('Connected by' + str(addr))
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    time.sleep(5) # takes some time to process command
                    conn.sendall(data)
                    self.logger.info(data)

if __name__ == '__main__':
    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-T15':
        base_directory = 'C:/Users/jdeas/Documents/GitHub/tres-guider'
    else:
        print('unsupported system')
        sys.exit()

    dfmserver = dfmserver(base_directory,'dfmserver.ini')
    dfmserver.listen()

    ipdb.set_trace()
