from configobj import ConfigObj
from pipython import GCSDevice
import socket
import math
import ipdb

class tiptilt:

    def __init__(self, base_directory, config_file):
        self.base_directory=base_directory
        self.config_file = config_file
        
        # read the config file
        config = ConfigObj(self.base_directory + '/config/' + self.config_file)

        # serial number of the TIP/TILT stage and controller
        self.sntiptilt = config['SN_TIPTILT']
        self.sncontroller = config['SN_CONTROLLER']

        # stage steps per arcsecond on the sky
        self.steps_per_arcsec = config['STEPS_PER_ARCSEC']
        
        # angle between North and axis A, in radians
        self.theta = config['THETA']*math.pi()/180.0

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
        self.tiptilt.EnumerateUSB()
        self.tiptilt.ConnectUSB(serialnum=self.sncontroller)
        #self.tiptilt.ConnectUSB(serialnum=self.sntiptilt)
        if !self.tiptilt.IsConnected():
            print 'Error connecting to device'
        
    '''
    Move the tip/tilt stage directly in stage coordinates. Check for
    limits, connectivity, etc
    '''
    def move_tip_tilt(self, tip, tilt):
        # make sure we're connected
        if !self.tiptilt.IsConnected():
            self.connect()

        # TODO: check bounds of requested move

        # move
        self.tiptilt.MOV('A',north)
        self.tiptilt.MOV('B',east)

        # make sure it moved where we wanted
        if position != self.get_position():
            pass

        return

    '''
    Move the tip/tilt stage North and East a specified number of
    arcseconds on the sky 
    '''
    def move_north_east(self, north, east):

        # translate north & east (arcsec on sky) to 
        # tip and tilt (stage steps)
        # requires angle, magnitude, and flip
        tip  = self.sign*self.steps_per_arcsec*(north*math.cos(self.theta) - east*math.sin(theta))
        tilt =           self.steps_per_arcsec*(north*math.sin(self.theta) + east*math.cos(theta))

        # move the tip/tilt
        return self.move_tip_tilt(tip,tilt)

    def get_position(self):
        return self.tiptilt.qPOS()
        return (self.tiptilt.qPOS('A'),self.tiptilt.qPOS('B'))

if __name__ == '__main__':

    if socket.gethostname() = 'onion':
        base_directory = '/h/onion0/tres/'
    else:
        base_directory = 'C:/tres-guider/'
    
    config_file = 'tiptilt.ini'
    tiptilt = tiptilt(base_directory, config_file)

    ipdb.set_trace()

