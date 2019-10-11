from configobj import ConfigObj
from pipython import GCSDevice
import math
import ipdb

class tiptilt:

    def __init__(self, base_directory, config_file):
		self.base_directory=base_directory
		self.config_file = config_file

		# read the config file
		config = ConfigObj(self.base_directory + '/config/' + self.config_file)
        	#self.science_position = float(config['SCIENCEPOS'])
        	#self.sky_position = float(config['SKYPOS'])
        	#self.out_position = float(config['OUTPOS'])
        	self.sntiptilt = config['SERIALNUM_TIPTILT']
        	self.sncontroller = config['SERIALNUM_CONTROLLER']

		# stage steps per arcsecond on the sky
		self.steps_per_arcsec = config['STEPS_PER_ARCSEC']

		# angle between North and axis A, in radians
		self.theta = config['THETA']*math.pi()/180.0

		# if there's a flip in the mapping, apply it
        	if config['FLIP']: self.sign = -1.0 
		else: self.sign = 1.0

		sncontroller = config['SERIALNUM_CONTROLLER']
        	self.sncontroller = config['SERIALNUM_CONTROLLER']

        	# use the PI python library to initialize the device
		self.tiptilt = GCSDevice()

    def allowedMove():
        self.tiptilt.qTMN() #minimum of each axis
        self.tiptilt.qTMX() #maximum of each axis
        self.tiptilt.qPOS() #current position

    def connect(self):
        self.tiptilt.ConnectUSB(serialnum=self.sncontroller)
        #self.tiptilt.ConnectUSB(serialnum=self.sntiptilt)

    def movetiptilt(self, tip, tilt):
        # make sure we're connected

        # check bounds

        # move

    def move(self, north, east):

        # translate north & east (arcsec on sky) to 
        # tip and tilt (stage steps)
        tip = self.steps_per_arcsec*self.sign*(north*math.cos(self.theta) - east*math.sin(theta))
        tilt = self.steps_per_arcsec*(north*math.sin(self.theta) + east*math.cos(theta))



        # move the tip/tilt
        self.tiptilt.MOV('A',north)
        self.tiptilt.MOV('B',east)

        # make sure it moved where we wanted
        if position != self.get_position():
            pass

        return

    def get_position(self):
        return (self.tiptilt.qPOS('A'),self.tiptilt.qPOS('B'))

if __name__ == '__main__':

    #base_directory = '/h/onion0/tres/'
    base_directory = 'C:/tres-guider/'

    config_file = 'tiptilt.ini'
    tiptilt = tiptilt(base_directory, config_file)

    ipdb.set_trace()

