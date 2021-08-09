from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os
import utils
import logging
import time

class calstage:

    def __init__(self, base_directory, config_file, logger=None, simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'calstage')
        else: self.logger = logger

        # read the config file
        config = ConfigObj(self.config_file)

        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        self.science_position = float(config['SCIENCEPOS'])
        self.sky_position = float(config['SKYPOS'])
        self.out_position = float(config['OUTPOS'])
        self.sn = config['SNCALSTAGE']
        self.model = config['MODEL']
        self.sn_controller = config['SNCONTROLLER']
        self.model_controller = config['MODELCONTROLLER']
        self.minpos = None
        self.maxpos = None
        self.simulate = simulate
        self.simulated_position = 0.0
        self.port = config['PORT']
        
        # use the PI python library to initialize the device
        if not self.simulate: self.calstage = GCSDevice()


    def connect_direct(self):
        self.serial = serial.Serial(self.port)
        return self.serial.is_open()

    def send(self, cmd):
        if self.serial.is_open():
            pass
        self.serial.write(cmd)
        
    def get_position(self):
        return self.send('POS?')

    def get_id(self):
        return self.send('*IDN?')

    def ref_to_positive_limit(self):
        return self.send('FPL')

    def ref_to_negative_limit(self):
        return self.send('FNL')
    
    def connect(self):

        # if simulating, just wait a second and return
        if self.simulate:
            time.sleep(1.0)
            return


        junk = self.calstage.ConnectRS232("/dev/ttyUSB0",115200)
        if not self.calstage.IsConnected():
            self.logger.error('Error connecting to device; check power and USB')
            sys.exit()		

        self.calstage.SVO('1',1)
            
#        ipdb.set_trace()
            
        # enable servo and home to negative limit if necessary
#        pitools.startup(self.calstage, refmodes=('FNL'))

        # enable servo and home to center if necessary
#        pitools.startup(self.calstage, refmodes=('FRF'))


        # enable servo and home to positive limit if necessary
#        pitools.startup(self.calstage, refmodes=('FPL'))

        # this one doesn't fail (right away...)
#        pitools.startup(self.calstage, refmodes=('POS'))
#        pitools.startup(self.calstage, refmodes=('ATZ'))
#        pitools.startup(self.calstage, refmodes=('RON'))
#        pitools.startup(self.calstage)

        
    def allowedMove(self,position):
        if self.minpos == None:
            if self.simulate: self.minpos = 0.0
            else: self.minpos = self.calstage.qTMN()['1']
        if self.maxpos == None:
            if self.simulate: self.maxpos = 26.0
            else: self.maxpos = self.calstage.qTMX()['1']
            
        if position > self.maxpos: return False
        if position < self.minpos: return False
        return True

    def move(self, position):

        if self.simulate:
            time.sleep(1.0)
            return True
        else:
            # make sure we're connected
            if not self.calstage.IsConnected():
                self.connect()
                if not self.calstage.IsConnected():
                    self.logger.error("Error connecting to stage")
                    return False

        # make sure the move is in range
        if not self.allowedMove(position):
            self.logger.error("Requested move out of bounds")
            return False
           
        # move the stage
        self.logger.info("moving the stage to " + str(position))
        if self.simulate:
            time.sleep(1.0)
            self.simulated_position = position
        else: self.calstage.MOV('1',position)
        
        # success!
        return True

    def move_and_wait(self,position, tol=0.001):

        # move the stage
        if not self.move(position): return False

        # wait for it to stop
        if not self.simulate:
            pitools.waitontarget(self.calstage, axes=['1'])

        # make sure it moved where we wanted (within tolerance)
        if abs(position - self.get_position()) > tol:
            self.logger.error("Error moving to requested position")
            return False
        
        # success!
        return True

    def get_position(self):
        if self.simulate: return self.simulated_position
        return self.calstage.qPOS()['1']

    def get_position_string(self, tolerance=0.01):
        position = self.get_position()
        
        if abs(position - self.science_position) < tolerance: return 'Science'
        if abs(position - self.sky_position) < tolerance: return 'Sky'
        if abs(position - self.out_position) < tolerance: return 'Out'
        return 'Unknown'
        
    def move_to_science(self):
        return self.move_and_wait(self.science_position)

    def move_to_sky(self):
        return self.move_and_wait(self.sky_position)

    def move_to_out(self):
        return self.move_and_wait(self.out_position)

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'calstage.ini'
    calstage = calstage(base_directory, config_file)

    calstage.connect()

    ipdb.set_trace()

    calstage.move_to_science()
    calstage.move_to_sky()
    calstage.move_to_out()

    ipdb.set_trace()
