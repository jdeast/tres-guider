from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os
import logging
import utils

class tiptilt:

    def __init__(self, base_directory, config_file, logger=None, simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'calstage')
        else: self.logger = logger
        
        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        # serial number of the TIP/TILT stage and controller
        self.sn = config['SN_TIPTILT']
        self.model = config['MODEL_TIPTILT']
        self.sn_controller = config['SN_CONTROLLER']
        self.model_controller = config['MODEL_CONTROLLER']

        # stage steps per arcsecond on the sky 
        self.steps_per_arcsec = float(config['STEPS_PER_ARCSEC'])
        
        # angle between North and axis A, in radians
        self.theta = float(config['THETA'])*math.pi/180.0

        # if there's a flip in the mapping, apply it
        if config['FLIP']: self.sign = -1.0 
        else: self.sign = 1.0

        # use the PI python library to initialize the device
        self.tiptilt = GCSDevice()

    def allowedMove():
        self.tiptilt.qTMN() # minimum of each axis
        self.tiptilt.qTMX() # maximum of each axis
        self.tiptilt.qPOS() # current position

    def connect(self):
        usbdevices = self.tiptilt.EnumerateUSB()


        #"*** GCSError: There is no interface or DLL handle with the given ID (-9)" That error requires a power cycle

        found = False
        if len(usbdevices) == 0:
            self.logger.error("No PI devices found")
            sys.exit()
            
        for device in usbdevices:
            if self.sn_controller in device:
                found = True
        if not found:
            self.logger.error('Serial number in ' + self.config_file + ' (' + self.sn_controller + ') does not match any of the connected USB devices; check power and USB')
            for device in usbdevices:
                self.logger.info(str(device) + ' is connected')
            sys.exit()

        self.tiptilt.ConnectUSB(serialnum=self.sn_controller)
        #self.tiptilt.ConnectUSB(serialnum=self.sntiptilt)
        if not self.tiptilt.IsConnected():
            self.logger.error('Error connecting to device')

        pitools.startup(self.tiptilt)#, stages=['S-340'], servostates=[True])#, refmodes=('FNL'))
        
    '''
    Move the tip/tilt stage directly in stage coordinates. Check for
    limits, connectivity, etc
    '''
    def move_tip_tilt(self, tip, tilt):
        # make sure we're connected
        if not self.tiptilt.IsConnected():
            self.connect()

        # TODO: check bounds of requested move

        # move
        self.tiptilt.MOV('A',tip)
        self.tiptilt.MOV('B',tilt)

        # make sure it moved where we wanted
        #if position != self.get_position():
        #    pass

        return

    '''
    Move the tip/tilt stage North and East a specified number of
    arcseconds on the sky 
    '''
    def move_north_east(self, north, east):


        # get current position
        ttpos = self.get_position()
                
        # translate north & east (arcsec on sky) to 
        # tip and tilt (stage steps)
        # requires angle, magnitude, and flip
        tip  = self.sign*self.steps_per_arcsec*(north*math.cos(self.theta) - east*math.sin(self.theta)) - ttpos['A']
        tilt =           self.steps_per_arcsec*(north*math.sin(self.theta) + east*math.cos(self.theta)) - ttpos['B']

        ipdb.set_trace()
        
        # move the tip/tilt
        return self.move_tip_tilt(tip,tilt)

    def get_position(self):
        # make sure we're connected
        if not self.tiptilt.IsConnected():
            self.connect()

        return self.tiptilt.qPOS()
        return (self.tiptilt.qPOS('A'),self.tiptilt.qPOS('B'))

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'tiptilt.ini'
    tiptilt = tiptilt(base_directory, config_file)

    tiptilt.connect()
    tiptilt.move_tip_tilt(0.2,0.2)
    print(tiptilt.get_position())
    tiptilt.move_tip_tilt(0.0,0.0)
    print(tiptilt.get_position())

    ipdb.set_trace()

