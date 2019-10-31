from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os

class calstage:

    def __init__(self, base_directory, config_file):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # read the config file
        config = ConfigObj(self.config_file)

        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            print 'Config file not found: (' + self.config_file + ')'
            sys.exit()

        self.science_position = float(config['SCIENCEPOS'])
        self.sky_position = float(config['SKYPOS'])
        self.out_position = float(config['OUTPOS'])
        self.sncontroller = config['SNCONTROLLER']
        self.minpos = None
        self.maxpos = None

        # use the PI python library to initialize the device
        self.calstage = GCSDevice()

    def connect(self):
        usbdevices = self.calstage.EnumerateUSB()

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

        self.calstage.ConnectUSB(serialnum=self.sncontroller)
        if not self.calstage.IsConnected():
            print 'Error connecting to device'

        # enable servo and home to negative limit if necessary
        pitools.startup(self.calstage, refmodes=('FNL'))
        
        # enable servo home to center if necessary
        #pitools.startup(self.calstage, refmodes=('FRF')) 


    def allowedMove(self,position):
        if self.minpos == None: self.minpos = self.calstage.qTMN()['1']
        if self.maxpos == None: self.maxpos = self.calstage.qTMX()['1']

        if position > self.maxpos: return False
        if position < self.minpos: return False
        return True

    def move(self, position):

        # make sure we're connected
        if not self.calstage.IsConnected():
            self.connect()
            if not self.calstage.IsConnected():
              print("Error connecting to stage")
              return False

        # make sure the move is in range
        if not self.allowedMove(position):
          print("Requested move out of bounds")
          return False
           
        # move the stage
        self.calstage.MOV('1',position)

        # success!
        return True

    def move_and_wait(self,position, tol=0.001):

        # move the stage
        if not self.move(position): return False

        # wait for it to stop
        pitools.waitontarget(self.calstage, axes=['1'])

        # make sure it moved where we wanted (within tolerance)
        if abs(position - self.get_position()) > tol:
          print("Error moving to requested position")
          return False
        
        # success!
        return True

    def get_position(self):
        return self.calstage.qPOS()['1']

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
        print 'unsupported system'
        sys.exit()

    config_file = 'calstage.ini'
    calstage = calstage(base_directory, config_file)

    calstage.connect()
    ipdb.set_trace()
    calstage.move_to_science()
    calstage.move_to_sky()
    calstage.move_to_out()

    ipdb.set_trace()
