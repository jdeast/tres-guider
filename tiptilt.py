from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os

class tiptilt:

    def __init__(self, base_directory, config_file):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file
        
        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            print 'Config file not found: (' + self.config_file + ')'
            sys.exit()

        # serial number of the TIP/TILT stage and controller
        self.sntiptilt = config['SN_TIPTILT']
        self.sncontroller = config['SN_CONTROLLER']

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
            print "No PI devices found"
            sys.exit()
            
        for device in usbdevices:
	    if self.sncontroller in device:
		found = True
        if not found:
	    print 'Serial number supplied for controller (' + self.sncontroller + ') does not match any of the connected USB devices; check ' + self.config_file
	    print "The connected devices are:"
	    print usbdevices
            sys.exit()		

        self.tiptilt.ConnectUSB(serialnum=self.sncontroller)
        #self.tiptilt.ConnectUSB(serialnum=self.sntiptilt)
        if not self.tiptilt.IsConnected():
            print 'Error connecting to device'

        pitools.startup(self.tiptilt)
        
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

        # translate north & east (arcsec on sky) to 
        # tip and tilt (stage steps)
        # requires angle, magnitude, and flip
        tip  = self.sign*self.steps_per_arcsec*(north*math.cos(self.theta) - east*math.sin(self.theta))
        tilt =           self.steps_per_arcsec*(north*math.sin(self.theta) + east*math.cos(self.theta))

        # move the tip/tilt
        return self.move_tip_tilt(tip,tilt)

    def get_position(self):
        return self.tiptilt.qPOS()
        return (self.tiptilt.qPOS('A'),self.tiptilt.qPOS('B'))

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    else:
        print 'unsupported system'
        sys.exit()
    
    config_file = 'tiptilt.ini'
    tiptilt = tiptilt(base_directory, config_file)
    tiptilt.connect()
    tiptilt.move_tip_tilt(0.2,0.2)

    ipdb.set_trace()

