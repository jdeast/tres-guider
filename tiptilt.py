from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os
import logging
import utils
import numpy as np
import argparse
import time

class TipTilt:

    def __init__(self, base_directory, config_file, logger=None,
                 simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        self.simulate=simulate
        
        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'tiptilt')
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

        self.steps_per_arcsec_tip = float(config['STEPS_PER_ARCSEC_TIP']) 
        self.steps_per_arcsec_tilt = float(config['STEPS_PER_ARCSEC_TILT']) 
        
        # angle between North and axis A, in radians
        self.theta = float(config['THETA'])*math.pi/180.0

        # if there's a flip in the mapping, apply it
        if config['FLIP'] == 'True':
            self.sign = -1.0 
        else:
            self.sign = 1.0

        # use the PI python library to initialize the device
        if not self.simulate:
            self.tiptilt = GCSDevice()

        # range of motion
        self.mintip_cmd = None
        self.maxtip_cmd = None
        self.mintilt_cmd = None
        self.maxtilt_cmd = None
        self.tip_0 = None
        self.tilt_0 = None
        
        self.position = {'A':None,'B':None,'N': None, 'E': None}
        
    def get_allowed_ranges(self):

        if self.simulate:
            self.mintip_cmd = 0.0
            self.maxtip_cmd = 2.0
            self.mintilt_cmd = 0.0
            self.maxtilt_cmd = 2.0
        else:
            self.mintip_cmd = self.tiptilt.qTMN()['A']
            self.maxtip_cmd = self.tiptilt.qTMX()['A']
            self.mintilt_cmd = self.tiptilt.qTMN()['B']
            self.maxtilt_cmd = self.tiptilt.qTMX()['B']
            
        self.tip_0  = (self.mintip_cmd  +  self.maxtip_cmd)/2.0
        self.tilt_0 = (self.mintilt_cmd + self.maxtilt_cmd)/2.0
            
    def connect(self):

        if self.simulate:
            self.get_allowed_ranges()
            self.move_tip_tilt(0, 0)
            return

        if self.tiptilt.IsConnected():
            self.logger.info('Already connected')
        
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

        # get the allowed ranges
        self.get_allowed_ranges()
        
        # move to the middle of the range
        self.move_tip_tilt(0, 0)


    def sky_to_mirror(self,north_arcsec,east_arcsec):
        # Rotate sky angles in arcsec through theta ccw rotation to get angles
        # in mirror axes and convert to mirror units of steps
        tip_cmd  = (self.sign * self.steps_per_arcsec_tip *
                    (north_arcsec * math.cos(self.theta) -
                     east_arcsec * math.sin(self.theta)))
        tilt_cmd = (self.steps_per_arcsec_tilt *
                    (north_arcsec * math.sin(self.theta) +
                     east_arcsec * math.cos(self.theta)))
        print(north_arcsec,east_arcsec,tip_cmd,tilt_cmd)
        
        return(tip_cmd,tilt_cmd)

    def mirror_to_sky(self,tip_cmd,tilt_cmd):
        # Rotate mirror angles through theta cw rotation to get angles in sky
        # axes
        tip_arcsec = ((tip_cmd - self.tip_0) / self.sign /
                      self.steps_per_arcsec_tip)
        tilt_arcsec = ((tilt_cmd - self.tilt_0) /
                       self.steps_per_arcsec_tilt)
        
        north_arcsec  = (tip_arcsec * math.cos(self.theta) +
                         tilt_arcsec * math.sin(self.theta))
        east_arcsec = (-1* tip_arcsec * math.sin(self.theta) +
                       tilt_arcsec * math.cos(self.theta))
        
        return(north_arcsec,east_arcsec)


    def move_tip_tilt(self,tip,tilt):
        '''
        Pass in tip (Axis A) and tilt (Axis B) in mirror units (steps), where
        0,0 is the center of travel.
        This code checks for limits, connectivity, etc
        This is the lowest level move
        '''

        # Include center position in cmds
        tip_cmd = tip + self.tip_0
        tilt_cmd = tilt + self.tilt_0
        
        # check bounds of requested move
        if ((tip_cmd < self.mintip_cmd) or (tip_cmd > self.maxtip_cmd) or
            (tilt_cmd < self.mintilt_cmd) or (tilt_cmd > self.maxtilt_cmd)):
            self.logger.error("Requested move (tip=" + str(tip) +
                              ", tilt=" + str(tilt) + " out of range")
            return False

        
        self.logger.info('moving to tip_cmd = ' + \
                         str(tip_cmd) + ', tilt_cmd =' + \
                         str(tilt_cmd))
        
        # move
        if not self.simulate:
            if not self.tiptilt.IsConnected():
                self.connect()
            print("%f %f" % (tip,tilt))
            self.tiptilt.MOV('A',tip_cmd)
            self.tiptilt.MOV('B',tilt_cmd)
            
        # qPOS doesn't work, so we must update the position whenever we move it
        # (and we have no way to check it went where we commanded it)

        # A and B are raw stage commands
        self.position['A'] = tip_cmd
        self.position['B'] = tilt_cmd

        (self.position['N'],self.position['E']) = self.mirror_to_sky(tip_cmd,
                                                                     tilt_cmd)

        print("Moved mirror A: %f B: %f N: %f E: %f" % (self.position['A'],
                                                        self.position['B'],
                                                        self.position['N'],
                                                        self.position['E']))
        # wait for move?
        
        # make sure it moved where we wanted
        #if position != self.get_position():
        #    pass

        return True
    
    '''
    Move the tip/tilt stage North and East a specified number of
    arcseconds on the sky 
    '''
    def move_north_east(self, north, east):

        # get current position
        # ttpos = self.get_position()
                
        # translate north & east (arcsec on sky) to 
        # tip and tilt (stage steps)
        # requires angle, magnitude, and flip
        
#        tip  = (ttpos['A'] + self.sign * self.steps_per_arcsec *
#                (north * math.cos(self.theta) - east * math.sin(self.theta)))
#        tilt = (ttpos['B'] + self.steps_per_arcsec *
#                (north * math.sin(self.theta) + east * math.cos(self.theta)))

        (tip_cmd,tilt_cmd) =  self.sky_to_mirror(north, east)
        # move the tip/tilt
        return self.move_tip_tilt(tip_cmd,tilt_cmd)


    def inject_offset_north_east(self,north_offset,east_offset):
        '''Not working yet'''
        (tip_offset,tilt_offset) =  self.sky_to_mirror(north_offset,
                                                       east_offset)
        current_tip = self.position['A']
        current_tilt = self.position['B']
        print("current_tip: %f tip_offset: %f current_tilt: %f tilt_offset: %f" %(current_tip,tip_offset,current_tilt,tilt_offset))
        self.move_tip_tilt(current_tip + tip_offset,
                           current_tilt + tilt_offset)
        
    
    # qPOS doesn't seem to work, but it seems to move
    # keep track of the position ourselves
    def get_position(self):
        return self.position
        

    def populate_header(self,hdr):
        ttpos = self.get_position()
        hdr['TTTIPPOS'] = (ttpos['A'],
                           "Tip Position of the tip/tilt stage (arcsec)")
        hdr['TTTILPOS'] = (ttpos['B'],
                           "Tilt Position of the tip/tilt stage (arcsec)")
        hdr['TTMODEL'] = (self.model,
                          "Model number of the tip/tilt stage")
        hdr['TTSN'] = (self.sn,
                       "Serial number of the tip/tilt stage")
        hdr['TTCMODEL'] = (self.model_controller,
                           "Model number of the tip/tilt stage controller")
        hdr['TTCSN'] = (self.sn_controller,
                        "Serial number of the tip/tilt stage controller")

    

if __name__ == '__main__':


    parser = argparse.ArgumentParser(description='Control the tip/tilt stage for the TRES front end')
    parser.add_argument('--home'  , dest='home'  , action='store_true', default=False, help='Move the tip/tilt stage to the center of motion')
    parser.add_argument('--move1'  , dest='move1'  , action='store_true', default=False, help='Move the tip/tilt stage to the (0,0) extreme')
    parser.add_argument('--move2'  , dest='move2'  , action='store_true', default=False, help='Move the tip/tilt stage to the (0,2) extreme')
    parser.add_argument('--move3'  , dest='move3'  , action='store_true', default=False, help='Move the tip/tilt stage to the (2,2) extreme')
    parser.add_argument('--move4'  , dest='move4'  , action='store_true', default=False, help='Move the tip/tilt stage to the (2,0) extreme')
    opt = parser.parse_args()
    
    if socket.gethostname() == 'tres-new-guider':
        base_directory = '/home/tres/jan/tres-guider'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'tip_tilt.ini'
    tiptilt = TipTilt(base_directory, config_file)

    tiptilt.connect()

    if opt.home:
        tiptilt.move_tip_tilt(-1.0,-1.0)
        time.sleep(5)
        tiptilt.move_tip_tilt(0.0,0.0)
        time.sleep(5)
        tiptilt.move_tip_tilt(1.0,1.0)
        time.sleep(5)
        tiptilt.move_tip_tilt(0.0,0.0)
    elif opt.move1:
        tiptilt.move_tip_tilt(-1.0,-1.0)
    elif opt.move2:
        tiptilt.move_tip_tilt(-1.0,1.0)
    elif opt.move3:
        tiptilt.move_tip_tilt(1.0,1.0)
    elif opt.move4:
        tiptilt.move_tip_tilt(1.0,-1.0)

#    print(tiptilt.get_position())

#    tiptilt.move_tip_tilt(0.0,0.0)
#    print(tiptilt.get_position())

