from configobj import ConfigObj
from pipython import GCSDevice, pitools
import socket
import math
import ipdb
import sys, os
import utils
import logging
import time
import pdu
import redis

class CalStage:

    def __init__(self, base_directory, config_file, logger=None, simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'calstage')
        else: self.logger = logger

        # read the config f7ile
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
        self.block_sky_position = float(config['BLOCK_SKYPOS'])
        self.block_science_position = float(config['BLOCK_SCIENCEPOS'])

        self.sn = config['SNCALSTAGE']
        self.model = config['MODEL']
        self.sn_controller = config['SNCONTROLLER']
        self.model_controller = config['MODELCONTROLLER']
        self.minpos = None
        self.maxpos = None
        self.simulate = simulate
        self.simulated_position = 0.0
        self.port = config['PORT']
        self.pdu = pdu.PDU(self.base_directory, 'pdu.ini', logger=self.logger)

        self.redis = redis.Redis(host=config['REDIS_SERVER'],
                                 port=config['REDIS_PORT'])
        
        # use the PI python library to initialize the device
        if not self.simulate: self.calstage = GCSDevice()       

    def power_on(self):
        if not self.pdu.calstage.status():
            self.pdu.calstage.on()

    def power_off(self):
        if self.pdu.calstage.status():
            self.pdu.calstage.off()
            
    def power_cycle(self,offtime=30):
        self.power_off()
        time.sleep(offtime)
        self.power_on()

    def connect(self):

        # if simulating, just wait a second and return
        if self.simulate:
            time.sleep(1.0)
            return

        junk = self.calstage.ConnectRS232(self.port,115200)
        if not self.calstage.IsConnected():
            self.logger.error('Error connecting to device; check power and USB')
            sys.exit()
        else:
            self.logger.info("Connection successful")

#        self.calstage.SVO('1',1)
            
#        ipdb.set_trace()
            
        # enable servo and home to negative limit if necessary
        self.logger.info("Initializing stage")
        pitools.startup(self.calstage, refmodes=('FNL'))
        self.logger.info("Initializing complete")
        

        # enable servo and home to center if necessary
#        pitools.startup(self.calstage, refmodes=('FRF'))


        # enable servo and home to positive limit if necessary
#        pitools.startup(self.calstage, refmodes=('FPL'))

        # this one doesn't fail (right away...)
#        pitools.startup(self.calstage, refmodes=('POS'))
#        pitools.startup(self.calstage, refmodes=('ATZ'))
#        pitools.startup(self.calstage, refmodes=('RON'))
#        pitools.startup(self.calstage)

    def populate_header(self,hdr):
        hdr['CSPOS'] = (self.get_position_string(),"Position of the cal stage (string)")
        hdr['CSPOSN'] = (self.get_position(),"Position of the cal stage (mm)")
        hdr['CSMODEL'] = (self.model,"Model Number of the cal stage")
        hdr['CSSN'] = (self.sn,"Serial number of the calibration stage")
        hdr['CSCMODEL'] = (self.model_controller,"Model of the cal stage controller")
        hdr['CSCSN'] = (self.sn_controller,"Serial number of the cal stage controller")

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
                    self.redis.set('calstage_status','not_connected')
                    self.redis.publish('calstage_status','not_connected')
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

        self.redis.set('calstage_status','moving')
        self.redis.publish('calstage_status','moving')
        
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
            self.redis.set('calstage_status','error')
            self.redis.publish('calstage_status','error')
            return False
        
        # success!
        return True

    def get_position(self):
        if self.simulate: position = self.simulated_position
        else:
            try: position = self.calstage.qPOS()['1']
            except: position = -99.0
            
        self.redis.set('calstage_status',self.position_to_string(position))
        self.redis.publish('calstage_status',self.position_to_string(position))
        return position

    def position_to_string(self, position, tolerance=0.01):
        if abs(position + 99.0) < tolerance: return 'error'
        if abs(position - self.science_position) < tolerance: return 'science'
        if abs(position - self.sky_position) < tolerance: return 'sky'
        if abs(position - self.out_position) < tolerance: return 'out'
        if abs(position - self.block_sky_position) < tolerance: return 'block_sky'
        if abs(position - self.block_science_position) < tolerance: return 'block_science'
        return str(position)
                           
    def get_position_string(self, tolerance=0.01):
        return self.position_to_string(self.get_position(),tolerance=tolerance)
        
    def move_to_science(self):
        return self.move_and_wait(self.science_position)

    def move_to_sky(self):
        return self.move_and_wait(self.sky_position)

    def move_to_out(self):
        return self.move_and_wait(self.out_position)

    def move_to_block_sky(self):
        return self.move_and_wait(self.block_sky_position)

    def move_to_block_science(self):
        return self.move_and_wait(self.block_science_position)

    def event_handler(msg):
        
        if msg == self.science_position: return self.move_to_science()
        if msg == self.sky_position: return self.move_to_sky()
        if msg == self.out_position: return self.move_to_out()
        if msg == self.block_sky_position: return self.move_to_block_sky()
        if msg == self.block_science_position: return self.move_to_block_science()
        return move_and_wait(msg)
        
if __name__ == '__main__':

    if socket.gethostname() == 'tres-new-guider':
        base_directory = '/home/tres/jan/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'calstage.ini'
    calstage = CalStage(base_directory, config_file)

    calstage.connect()

    while True:

        try:
            request = calstage.redis.get('calstage').decode()
            # calstage.logger.info("request=" + str(request))
            try:
                request = float(request)
                if abs(request - calstage.get_position()) > 0.01:
                    calstage.move_and_wait(request)
            except: 
                #calstage.logger.info('position=' + calstage.get_position_string())
                if request != calstage.get_position_string():
                    calstage.logger.info("request = " + request + ", current position = " + calstage.get_position_string())
                    if request == 'science': calstage.move_to_science()
                    elif request == 'sky': calstage.move_to_sky()
                    elif request == 'out': calstage.move_to_out()
                    elif request == 'block_sky': calstage.move_to_block_sky()
                    elif request == 'block_science': calstage.move_to_block_science()
        except:
            calstage.logger.exception("Could not decode calstage keyword. Redis server rebooted/down? Attempting to re-initialize the keywords")
            # if the redis server restarts, we need to re-initialize the values
            if calstage.redis.get('calstage') == None:
                calstage.redis.set('calstage',calstage.get_position_string()) 
                
            if calstage.redis.get('calstage_status') == None:
                calstage.redis.set('calstage_status','error') 
            
        time.sleep(0.1)

    calstage.move_to_science()
    ipdb.set_trace()

    calstage.move_to_sky()
    calstage.move_to_out()

    ipdb.set_trace()

    
    
