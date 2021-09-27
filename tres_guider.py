#!/usr/bin/python3

import time
import socket
import os
import math
import logging
import redis
import asyncio
import aioredis
import concurrent.futures
import json
import struct
from configobj import ConfigObj
from astropy.io import fits
from astropy.coordinates import SkyCoord
import astropy.units as u
import numpy as np
import datetime
import cv2
import base64
import ipdb
import astrometry
import dfm_telescope
import star_projector

import simulated_cam
#import asi_cam
import andor_cam
#import adimec_q4a180

import utils
import tiptilt
import pid
import calstage

import cv2_image_processor
import sep_image_processor
import quad_image_processor
import model_image_processor

#import centroid_image_processor as image_processor

################################################################################
class TelemetrySender():
    '''Send guider images and derived telemetry to redis for GUI usage'''
    
#-------------------------------------------------------------------------------
    def __init__(self,config):
        self.redis = redis.Redis(host=config['REDIS_SERVER'],
                                 port=config['REDIS_PORT'])
        print("Connected Telemetry sender to REDIS server")
        print(config['REDIS_SERVER'])
        print(config['REDIS_PORT'])
        if not self.redis.ping():
            print("Failed to connect to redis")
            exit
#        self.pub_tracking_data = self.redis.pubsub()

#-------------------------------------------------------------------------------
    def send(self,key,data):
        print(key,len(data))
        res = self.redis.publish(key,data)
        
################################################################################
class EventSender():
    '''Send guider events to Redis for GUI usage'''
    
#-------------------------------------------------------------------------------
    def __init__(self,config):
        self.server_host = config['REDIS_SERVER']
        self.server_port = config['REDIS_PORT']
        self.redis = redis.Redis(host=self.server_host,
                                 port=self.server_port)
        print("Connected Event sender to REDIS server")
        print(config['REDIS_SERVER'])
        print(config['REDIS_PORT'])
        if not self.redis.ping():
            print("Failed to connect to redis")
            exit
        self.command_counter = 0
        
#-------------------------------------------------------------------------------
    def send(self,command_dict):
        '''
        Pass in a dict of key value pairs to set in underlying code
        '''
        command_json_struct = json.dumps(command_dict)
        res = self.redis.publish('guider_state',command_json_struct)
        print("Sent event %i" % (self.command_counter,))
        self.command_counter += 1
        return(0)
        
################################################################################
class EventReceiver():
    '''Receive gui events from Redis to modify guider operation'''    
    def __init__(self,config,callback):
        self.config = config
        self.command_callback = callback
        
        self.receive_task = asyncio.ensure_future(
            self.receive_telem(self.command_callback,
                               self.config['REDIS_SERVER'],
                               self.config['REDIS_PORT'],
                               'guider_commands'))
        
#-------------------------------------------------------------------------------
    @staticmethod
    async def receive_telem(callback,server,port,data_name):
        redis_sub = await aioredis.create_redis('redis://'+server+':'+port)
        res = await redis_sub.subscribe(data_name)
        sub_channel = res[0]        
        
        receive_counter = 0        
        while (await sub_channel.wait_message()):
            msg = await sub_channel.get_json()
            callback(msg)
            receive_counter += 1

        

################################################################################
class SimulatedTelescope():
    '''Manage telescope interface'''
    
    def __init__(self,config):
        pass

#-------------------------------------------------------------------------------
    def get_objname(self):
        return('test')
    
#-------------------------------------------------------------------------------
    def populate_header(self,hdr):
        '''Retrieve and set telescope information FITS headers 
        (requires communication with TCS) '''
        
        #hdr['SITELAT'] = (latitude,"Site Latitude (deg)")
        #hdr['SITELONG'] = (longitude,"Site East Longitude (deg)")
        #hdr['SITEALT'] = (elevation,"Site Altitude (m)")
        #hdr['RA'] = (ra, "Solved RA (J2000 deg)")
        #hdr['DEC'] = (dec,"Solved Dec (J2000 deg)")
        #hdr['ALT'] = (alt,'Telescope altitude (deg)')
        #hdr['AZ'] = (az,'Telescope azimuth (deg E of N)')
        #hdr['AIRMASS'] = (airmass,"airmass (plane approximation)")
        #hdr['HOURANG'] = (hourang,"Hour angle")
        #hdr['PMODEL'] = ('',"Pointing Model File")
        #hdr['FOCPOS'] = (focus,"Focus Position (microns)")
        #hdr['ROTPOS'] = (rotpos,"Mechanical rotator position (degrees)")
        #hdr['PARANG'] = (parang,"Parallactic Angle (degrees)")
        #hdr['SKYPA' ] = (skypa,"Position angle on the sky (degrees E of N)")

        #hdr['MOONRA'] = (moonra, "Moon RA (J2000 deg)")
        #hdr['MOONDEC'] =  (moondec, "Moon Dec (J2000 deg)")
        #hdr['MOONPHAS'] = (moonphase, "Moon Phase (Fraction)")
        #hdr['MOONDIST'] = (moonsep, "Distance between pointing and moon (deg)")
        
        pass

#-------------------------------------------------------------------------------
    def populate_header(self,hdr):
        '''Retrieve and set telescope information FITS headers 
        (requires communication with TCS) '''
        
        #hdr['SITELAT'] = (latitude,"Site Latitude (deg)")
        #hdr['SITELONG'] = (longitude,"Site East Longitude (deg)")
        #hdr['SITEALT'] = (elevation,"Site Altitude (m)")
        #hdr['RA'] = (ra, "Solved RA (J2000 deg)")
        #hdr['DEC'] = (dec,"Solved Dec (J2000 deg)")
        #hdr['ALT'] = (alt,'Telescope altitude (deg)')
        #hdr['AZ'] = (az,'Telescope azimuth (deg E of N)')
        #hdr['AIRMASS'] = (airmass,"airmass (plane approximation)")
        #hdr['HOURANG'] = (hourang,"Hour angle")
        #hdr['PMODEL'] = ('',"Pointing Model File")
        #hdr['FOCPOS'] = (focus,"Focus Position (microns)")
        #hdr['ROTPOS'] = (rotpos,"Mechanical rotator position (degrees)")
        #hdr['PARANG'] = (parang,"Parallactic Angle (degrees)")
        #hdr['SKYPA' ] = (skypa,"Position angle on the sky (degrees E of N)")

        #hdr['MOONRA'] = (moonra, "Moon RA (J2000 deg)")
        #hdr['MOONDEC'] =  (moondec, "Moon Dec (J2000 deg)")
        #hdr['MOONPHAS'] = (moonphase, "Moon Phase (Fraction)")
        #hdr['MOONDIST'] = (moonsep, "Distance between pointing and moon (deg)")
        
        pass
    
    
################################################################################
class WeatherStation():
    '''Manage weather data interface'''
    
    def __init__(self,config):
        pass

#-------------------------------------------------------------------------------
    def populate_header(self,hdr):
        '''Retrieve and set weather information FITS headers'''
        
        pass
    
################################################################################
class GuidingSystem():
    def __init__(self,base_directory,cam_type='simulated',
                 tiptilt_type='pi',
                 calstage_type='simulated',
                 telescope_type='simulated'):
        '''
        This code is the central actor in performing the TRES guiding 
        operations. Here we instantiate the required software components, 
        listen for and process events, receive and process images, send
        corrections, generate and send telemetry, and log data.
 
        base_directory is where the code resides
        cam_type: 'simulated', 'adimec', 'andor'
        tiptilt_type = 'simulated', 'pi'
        calstage_type: 'simulated', 'pi'
        telescope_type: 'simulated', 'projector', 'dfm'
        '''
        
        self.base_directory = base_directory
        self.config_file = 'tres_guider.ini'
        self.config_file = self.base_directory + '/config/' + self.config_file

        self.logger = utils.setup_logger(base_directory + '/log/', 'tres')
        
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            logging.error('Config file not found: ('
                          + self.config_file + ')')
            exit()

        self.cam_type = cam_type
        self.tiptilt_type = tiptilt_type
        self.calstage_type = calstage_type
        self.telescope_type = telescope_type

        # Telescope focal plane magnification
        self.arcsec_per_um_guider_ccd = \
            float(config['ARCSEC_PER_UM_GUIDER_CCD'])
        self.guider_magnification = float(config['GUIDER_MAGNIFICATION'])
        
        self.init_ipc(config)
        self.init_camera(config)
        self.init_calstage(config)
        self.init_image_processing(config)
        self.init_pid(config)
        self.init_tiptilt(config)
        self.init_telescope(config)
        self.weather_station = WeatherStation(config)
        
        # Position of science fiber with respect to on-axis in arcsec
        self.sci_fiber_x = float(config['SCI_FIBER_X'])
        self.sci_fiber_y = float(config['SCI_FIBER_Y'])

        # Diameter of science fiber bucket in arcsec        
        self.sci_fiber_xwidth = float(config['SCI_FIBER_XWIDTH'])
        self.sci_fiber_ywidth = float(config['SCI_FIBER_YWIDTH'])

        self.sci_hole_xwidth = float(config['SCI_HOLE_XWIDTH'])
        self.sci_hole_ywidth = float(config['SCI_HOLE_YWIDTH'])
        
        # Position of sky reference fiber with respect to on-axis in arcsec
        self.sky_fiber_x = float(config['SKY_FIBER_X'])
        self.sky_fiber_y = float(config['SKY_FIBER_Y'])
        
        # Diameter of sky reference fiber bucket in arcsec                
        self.sky_fiber_xwidth = float(config['SKY_FIBER_XWIDTH'])
        self.sky_fiber_ywidth = float(config['SKY_FIBER_YWIDTH'])

        self.sky_hole_xwidth = float(config['SKY_HOLE_XWIDTH'])
        self.sky_hole_ywidth = float(config['SKY_HOLE_YWIDTH'])

        # Set star ROI to be on-axis initially
        self.star_xcenter = 0.0
        self.star_ycenter = 0.0

        (self.camera_ydim_pix,self.camera_xdim_pix) = self.cam.get_camera_dims()

        # This is our on-axis position in camera pixels
        self.camera_xcenter_pix = (float(self.camera_xdim_pix)/2 -
                                   self.cam_decenter_x_pixels) - 0.5
        self.camera_ycenter_pix = (float(self.camera_ydim_pix)/2 -
                                   self.cam_decenter_y_pixels) - 0.5


        # The science fiber is on-axis, so sci_fiber_x and sci_fiber_y are
        # normally zero, but we allow for this not to be the case so
        # make sure to add the science fiber position to the cam on-axis point
        self.sci_fiber_xcenter_pix = (self.camera_xcenter_pix +
                                      self.sci_fiber_x / self.arcsec_per_pixel)
        self.sci_fiber_ycenter_pix = (self.camera_ycenter_pix +
                                      self.sci_fiber_y / self.arcsec_per_pixel)

        # The sky fiber is off-axis, so sky_fiber_x and sky_fiber_y are
        # normally zero, but we allow for this not to be the case so
        # make sure to add the science fiber position to the cam on-axis point
        self.sky_fiber_xcenter_pix = (self.camera_xcenter_pix +
                                      self.sky_fiber_x / self.arcsec_per_pixel)
        self.sky_fiber_ycenter_pix = (self.camera_ycenter_pix +
                                      self.sky_fiber_y / self.arcsec_per_pixel)

        

        # The ROI center must be an integer that specifies which pixels are
        # used for the ROI readout
        self.star_roi_xcenter_pix = (self.camera_xdim_pix/2 + 
                                      self.cam_decenter_x_pixels)

        self.star_roi_ycenter_pix = (self.camera_xdim_pix/2 + 
                                     self.cam_decenter_x_pixels)
        
        # Where we store our 
        self.datapath = config['DATAPATH']
        
        #Set default tracking setpoint in arcsec with respect to on-axis
        self.pid.setPoint((self.sci_fiber_y,self.sci_fiber_x))

        # Default to no detected stars, and no offsets
        self.stars = []

        # Set initial guiding offset to 0" in both axes
        self.offset = (0.0,0.0)

        # Default to zero until computed
        self.peak_counts = 0

        # For each possible incoming command, define a handler.
        self.command_tree = {'loop_state':self.set_loop_state,
                             'framing':self.set_framing_state,
                             'exposure_time':self.set_exposure_time,
                             'cadence':self.set_cadence,
                             'toggle_framing':self.toggle_framing_state,
                             'roi':self.set_roi,
                             'star_position':self.set_star_roi,
                             'guiding_mode':self.set_guiding_mode,
                             'fsm_angle':self.set_fsm_angle,
                             'offset_angle':self.set_offset_angle,
                             'loop_gains':self.set_loop_gains,
                             'plate_solve':self.on_plate_solve,
                             'offset_mount':self.on_offset_mount}
        
        # Start with camera framing but in open loop
        self.framing = True
        self.loop_state = 'open'
        self.guiding_mode = 'annulus_sep'
        self.plate_solve_running = False
        self.plate_solve_success = False
        self.plate_solve_ra_mispointing_arcsec = None
        self.plate_solve_dec_mispointing_arcsec = None
        self.wcs_hdr_dict = {}
        self.fits_hdr = {}

        # Inform GUI
        res = self.event_sender.send({'framing':1})
        res = self.event_sender.send({'loop_state':0})

        self.save_images = False
        
        # Send data via redis telem channel?
        self.telemetry = True

        self.counter = 0
        
#-------------------------------------------------------------------------------
    def init_ipc(self,config):
        '''Establish inter-process communicaiton mechanisms for telemetry and
        GUI interactions'''
        
        self.telem_out = TelemetrySender(config)
        self.event_sender = EventSender(config)
        self.event_receiver = EventReceiver(config,self.command_callback)

#-------------------------------------------------------------------------------
    def init_camera(self,config):
        '''
        Open camera specified by self.cam_type and register new image callback
        to process data
        '''        

        # How many pixels is the camera center displaced from on-axis
        # Use DS9 coords.  0,0 is in the lower left.
        self.cam_decenter_x_pixels = float(config['CAM_DECENTER_X_PIX'])
        self.cam_decenter_y_pixels = float(config['CAM_DECENTER_Y_PIX'])

        # Rotation of camera with respect to telescope axes
        self.cam_rotation = float(config['CAM_ROTATION_DEGREES'])
        self.cam_rotation_rad = self.cam_rotation * math.pi/180
        self.cam_flip_x = float(config['CAM_FLIP_X'])
        self.cam_flip_y = float(config['CAM_FLIP_Y'])        

        if self.cam_type == 'simulated':
            self.cam = simulated_cam.SimulatedGuiderCam(base_directory,
                                                        'simulated_cam.ini',
                                                        new_image_callback=\
                                                        self.new_image_callback)
        elif self.cam_type == 'adimec':
            self.cam = adimec_q4a180.AdimecGuiderCam(base_directory,
                                                     'adimec_cam.ini',
                                                     new_image_callback=\
                                                     self.new_image_callback)
        elif self.cam_type == 'andor':
            self.cam = andor_cam.AndorGuiderCam(base_directory,'zyla.ini',
                                                new_image_callback=\
                                                self.new_image_callback)
        elif self.cam_type == 'asi':
            self.cam = asi_cam.ASIGuiderCam(base_directory,'asi_cam.ini',
                                            new_image_callback=\
                                            self.new_image_callback)
        else:
            self.logger.error("Unknown cam type")
            exit()

        # Different cameras have different pixels sizes, so compute the
        # platescale here
        self.arcsec_per_pixel = self.arcsec_per_um_guider_ccd * \
            self.cam.get_pixel_size()

        self.pixel_size_um = self.cam.get_pixel_size();

        # Note: We force all ROIs to be square. Force to be an even number here.
        self.roi_size_pixels = int(np.round( 
            2. * float(config['ROI_SIZE_ARCSEC']) /self.arcsec_per_pixel))/2
        

#-------------------------------------------------------------------------------
    def init_calstage(self,config):
        '''Instantiate calstage object and initialize it'''
        
        if (self.calstage_type == 'simulated'):
            self.calstage = calstage.CalStage(self.base_directory,
                                              'calstage.ini',
                                              logger = self.logger,
                                              simulate = True)
        elif (self.calstage_type == 'pi'):
            self.calstage = calstage.CalStage(self.base_directory,
                                              'calstage.ini',
                                              logger = self.logger,
                                              simulate = False)
            
#-------------------------------------------------------------------------------
    def init_image_processing(self,config):
        '''
        Instantiate object that ingests raw images and returns centroids
        '''
        
        # Only pull in stars that are within this distance from the trackpoint
        self.guiding_tolerance = float(config['GUIDING_TOLERANCE']) # arcsec

        self.cv2_image_processor = \
            cv2_image_processor.ImageProcessor(config,logger=self.logger)
        self.sep_image_processor = \
            sep_image_processor.ImageProcessor(config,logger=self.logger)
        self.quad_image_processor = \
            quad_image_processor.ImageProcessor(config,logger=self.logger)
        self.model_image_processor = \
            model_image_processor.ImageProcessor(config,logger=self.logger)
        
#-------------------------------------------------------------------------------
    def init_pid(self,config):
        '''
        Instantiate PID object that takes centroids and computes steering
        mirror commands. Initialize it with default servo parameters
        '''
        self.KP = float(config['KP'])
        self.KI = float(config['KI'])
        self.KD = float(config['KD'])
        self.Imax = float(config['Imax'])
        self.Dband = float(config['Dband'])
        self.Corr_max = float(config['Corr_max'])
        
        self.pid = pid.PID(P=np.array([self.KP, self.KP]),
                           I=np.array([self.KI, self.KI]),
                           D=np.array([self.KD, self.KD]),
                           Integrator_max = self.Imax,
                           Deadband = self.Dband,
                           Correction_max = self.Corr_max,
                           logger = self.logger)
        
#-------------------------------------------------------------------------------
    def init_tiptilt(self,config):
        '''Instantiate tiptilt object and initialize tiptilt stage'''
        if (self.tiptilt_type == 'simulated'):
            self.tiptilt = tiptilt.TipTilt(self.base_directory,'tip_tilt.ini',
                                           logger = self.logger,
                                           simulate = True)
        elif (self.tiptilt_type == 'pi'):
            self.tiptilt = tiptilt.TipTilt(self.base_directory,'tip_tilt.ini',
                                           logger = self.logger,
                                           simulate = False)
            self.tiptilt.connect()
        # Move to middle of range to start
        self.tiptilt.move_tip_tilt(0.0,0.0)

#-------------------------------------------------------------------------------
    def init_telescope(self,config):
        '''Instantiate telescope object and initialize telescope connection'''
        if (self.telescope_type == 'simulated'):
            self.telescope = SimulatedTelescope(config)
        if (self.telescope_type == 'projector'):
            self.telescope = star_projector.StarProjector("./",
                                                          "star_projector.ini")
        elif (self.telescope_type == 'dfm'):
            self.telescope = dfm_telescope.DFMTelescope(config)

#-------------------------------------------------------------------------------
    def get_header(self):
        '''Latch current values to create header for FITS file'''
        hdr = fits.Header()

        hdr['INSTRUME'] = ('TRES','Name of the instrument')
        hdr['OBSERVER'] = ('',"Observer") # do we have this info?
        hdr['DATE-OBS'] = (self.dateobs.strftime('%Y-%m-%dT%H:%M:%S.%f'),
                           'YYYY-MM-DDThh:mm:ss.ssssss (UTC)')
        hdr['PIXSCALE'] = (self.arcsec_per_pixel,'arcsec/pixel')
        hdr['GUIDSTAT'] = (self.loop_state,'Status of the guiding loop')

        # Fiber info
        hdr['XSCIFIB'] = (self.sci_fiber_x,
                          'X position of sci fiber centroid in arcsec')
        hdr['YSCIFIB'] = (self.sci_fiber_y,
                          'Y position of sci fiber centroid in arcsec')
        hdr['XSKYFIB'] = (self.sky_fiber_x,
                          'X position of sky fiber centroid in arcsec')
        hdr['YSKYFIB'] = (self.sky_fiber_y,
                          'Y position of sky fiber centroid in arcsec')
        
        self.cam.populate_header(hdr)
        self.calstage.populate_header(hdr)
        self.tiptilt.populate_header(hdr)
        self.telescope.populate_header(hdr)
        self.sep_image_processor.populate_header(hdr)
        self.weather_station.populate_header(hdr)


        # target information (do we have this?)
        #hdr['TARGRA'] = (ra, "Target RA (J2000 deg)")
        #hdr['TARGDEC'] = (dec,"Target Dec (J2000 deg)")
        #hdr['PMRA'] = (pmra, "Target Proper Motion in RA (mas/yr)")
        #hdr['PMDEC'] = (pmdec, "Target Proper Motion in DEC (mas/yr)")
        #hdr['PARLAX'] = (parallax, "Target Parallax (mas)")
        #hdr['RV'] = (rv, "Target RV (km/s)")

        
        return(hdr)

#-------------------------------------------------------------------------------
    def save_image(self,image,overwrite=False):
        '''
        Populate a FITS header by probing objects and attach it to the image.
        Write the image to disk
        '''
        self.logger.info("Saving " + filename)
        hdr = self.get_header()
        hdu = fits.PrimaryHDU(self.image, header=hdr)
        hdulist = fits.HDUList([hdu])
        hdulist.writeto(filename, overwrite=overwrite)

#-------------------------------------------------------------------------------
    def save_image_in_thread(self,image):
        '''
        Construct a filename and start the thread that writes the image to disk
        Return thread descriptor so that code can join on the thread.
        '''
        
        objname = self.telescope.get_objname()
        files = glob.glob(self.guider.datapath + "*.fits")
        index = str(len(files)+1).zfill(4)
        datestr = datetime.datetime.utcnow().strftime('%m%d%y') 
        filename = self.guider.datapath + objname + '.' + datestr + \
            '.guider.' + index + '.fits'

        # saving can go on in the background
        save_image_thread = threading.Thread(target=self.save_image,
                                             args=(filename,))
        save_image_thread.name = 'save_image_thread'
        save_image_thread.start()
        return(save_image_thread)

#-------------------------------------------------------------------------------
    def new_image_callback(self,dateobs,camera_ydim_pix,camera_xdim_pix,
                           camera_y1,camera_x1,camera_y2,camera_x2,image):
        '''
        Process new image through guiding code.  Pass in datetime of image
        acquisition, camera full y and x dimension in pixels, plus the current
        ROI in use, followed by the image
        '''
        self.logger.info("Frame %i" % (self.counter,))
        self.counter += 1
        self.dateobs = dateobs
        self.fits_hdr = self.get_header()
        self.image = image
        self.camera_xdim_pix = camera_xdim_pix
        self.camera_ydim_pix = camera_ydim_pix
        self.camera_xcenter_pix = (float(self.camera_xdim_pix)/2 -
                                   self.cam_decenter_x_pixels) - 0.5
        self.camera_ycenter_pix = (float(self.camera_ydim_pix)/2 -
                                   self.cam_decenter_y_pixels) - 0.5
        self.sci_fiber_xcenter_pix = self.camera_xcenter_pix + \
                                     self.sci_fiber_x/self.arcsec_per_pixel
        self.sci_fiber_ycenter_pix = self.camera_ycenter_pix + \
                                     self.sci_fiber_y/self.arcsec_per_pixel
        self.sky_fiber_xcenter_pix = self.camera_xcenter_pix + \
                                     self.sky_fiber_x/self.arcsec_per_pixel
        self.sky_fiber_ycenter_pix = self.camera_ycenter_pix + \
                                     self.sky_fiber_y/self.arcsec_per_pixel
        self.star_xcenter_pix = self.camera_xcenter_pix + \
                                self.star_xcenter/self.arcsec_per_pixel
        self.star_ycenter_pix = self.camera_ycenter_pix + \
                                self.star_ycenter/self.arcsec_per_pixel

        
        self.x1 = camera_x1
        self.y1 = camera_y1
        self.x2 = camera_x2
        self.y2 = camera_y2

        # Sanity check
        if ((self.image.shape[0] != self.y2-self.y1) or
            (self.image.shape[1] != self.x2-self.x1)):
            print(self.image.shape[0])
            print(self.image.shape[1])
            print(self.x1)
            print(self.x2)
            print(self.y1)
            print(self.y2)
            print(self.camera_xdim_pix)
            print(self.camera_ydim_pix)
            self.logger.error("Mismatch in image dimensions")
            return

        self.sci_roi_x1 = int(round(self.sci_fiber_xcenter_pix)) - \
                          int(self.roi_size_pixels/2)
        self.sci_roi_x2 = int(round(self.sci_fiber_xcenter_pix)) + \
                          int(self.roi_size_pixels/2)
        self.sci_roi_y1 = int(round(self.sci_fiber_ycenter_pix)) - \
                          int(self.roi_size_pixels/2)
        self.sci_roi_y2 = int(round(self.sci_fiber_ycenter_pix)) + \
                          int(self.roi_size_pixels/2)
        self.sci_roi = self.image[self.sci_roi_y1:self.sci_roi_y2,
                                  self.sci_roi_x1:self.sci_roi_x2]
        
        self.sky_roi_x1 = int(round(self.sky_fiber_xcenter_pix)) - \
                              int(self.roi_size_pixels/2)
        self.sky_roi_x2 = int(round(self.sky_fiber_xcenter_pix)) + \
                          int(self.roi_size_pixels/2)
        self.sky_roi_y1 = int(round(self.sky_fiber_ycenter_pix)) - \
                              int(self.roi_size_pixels/2)
        self.sky_roi_y2 = int(round(self.sky_fiber_ycenter_pix)) + \
                          int(self.roi_size_pixels/2)
        self.sky_roi = self.image[self.sky_roi_y1:self.sky_roi_y2,
                                  self.sky_roi_x1:self.sky_roi_x2]

        self.star_roi_x1 = int(round(self.star_xcenter_pix)) - \
                              int(self.roi_size_pixels/2)
        self.star_roi_x2 = int(round(self.star_xcenter_pix)) + \
                              int(self.roi_size_pixels/2)
        self.star_roi_y1 = int(round(self.star_ycenter_pix)) - \
                              int(self.roi_size_pixels/2)
        self.star_roi_y2 = int(round(self.star_ycenter_pix)) + \
                              int(self.roi_size_pixels/2)
        self.star_roi = self.image[self.star_roi_y1:self.star_roi_y2,
                                   self.star_roi_x1:self.star_roi_x2]

#        print(self.sci_roi_x1,self.sci_roi_x2,self.sci_roi_y1,self.sci_roi_y2)
#        print(self.sky_roi_x1,self.sky_roi_x2,self.sky_roi_y1,self.sky_roi_y2)
#        print(self.star_roi_x1,self.star_roi_x2,self.star_roi_y1,self.star_roi_y2)
#        print(self.sci_roi.shape)
#        print(self.sky_roi.shape)
#        print(self.star_roi.shape)
        
        # Analyze and act on the new image
        if self.guiding_mode == 'full_frame':
            try:
                self.perform_guiding(self.image,self.camera_ydim_pix,
                                     self.camera_xdim_pix,self.y1,self.y2,
                                     self.x1,self.x2)
            except Exception as e:
                print("Error performing full frame guiding")
                print(e)
        elif ((self.guiding_mode == 'annulus_quad') or
              (self.guiding_mode == 'annulus_sep') or
              (self.guiding_mode == 'annulus_model')):
            try:
                self.perform_annulus_guiding(self.guiding_mode,
                                             self.sci_roi,
                                             self.camera_ydim_pix,
                                             self.camera_xdim_pix,
                                             self.sci_roi_y1,
                                             self.sci_roi_y2,
                                             self.sci_roi_x1,
                                             self.sci_roi_x2)
            except Exception as e:
                print("Error performing annulus guiding in mode",
                      self.guiding_mode )
                print(e)
        elif self.guiding_mode == 'offset':
            try:
                self.perform_offset_guiding(self.star_roi,self.camera_ydim_pix,
                                            self.camera_xdim_pix,
                                            self.star_roi_y1,
                                            self.star_roi_y2,self.star_roi_x1,
                                            self.star_roi_x2)
            except Exception as e:
                print("Error performing offset guiding")
                print(e)

        if self.telemetry:
            self.send_telemetry()
        
        if self.save_images:
            save_thread = self.save_image_in_thread()

#-------------------------------------------------------------------------------
    def set_loop_state(self,param):
        if param == 0:
            self.loop_state = 'open'
            res = self.event_sender.send({'loop_state':0})
            print('Opened loops')            
        elif param == 1:
            self.loop_state = 'closed'
            res = self.event_sender.send({'loop_state':1})
#            self.x_correction_arcsec += 3.0
            self.pid.reset()
            print('Closed loops')
        return(0)

#-------------------------------------------------------------------------------
    def set_guiding_mode(self,param):
        if param == 'full_frame':
            print("Setting guiding mode to full_frame guiding")
            self.guiding_mode = 'full_frame'        
        elif param == 'annulus_sep':
            print("Setting guiding mode to annulus sep guiding")
            self.guiding_mode = 'annulus_sep'
        elif param == 'annulus_quad':
            print("Setting guiding mode to annulus quad guiding")
            self.guiding_mode = 'annulus_quad'
        elif param == 'annulus_model':
            print("Setting guiding mode to annulus model guiding")
            self.guiding_mode = 'annulus_model'            
        elif param == 'offset':
            print("Setting guiding mode to offset guiding")
            self.guiding_mode = 'offset'            
        return(0)
    
#-------------------------------------------------------------------------------
    def set_fsm_angle(self,param):
        ''' Pass in absolute fsm angle in north,east relative to fsm center of
        range'''
        if len(param) != 2:
            return(-1)
        else:
            print("Setting FSM to angle %f %f" % (param[1],param[0]))
            try:
                self.tiptilt.move_north_east(param[1],param[0])
            except Exception as e:
                print(e)

#-------------------------------------------------------------------------------
    def set_offset_angle(self,param):
        if len(param) != 2:
            return(-1)
        else:
            print("Setting offset to angle y:%f x:%f arcsec" % (param[1],param[0]))
            self.offset=(param[1],param[0])

#-------------------------------------------------------------------------------
    def set_loop_gains(self,param):
        if len(param) != 3:
            return(-1)
        else:
            print("Setting loop gains to P:%f I:%f D: %f" %
                  (param[0],param[1],param[2]))

            self.KP = param[0]
            self.KI = param[1]
            self.KD = param[2]
            self.pid.setKp(np.array([self.KP,self.KP]))
            self.pid.setKi(np.array([self.KI,self.KI]))
            self.pid.setKd(np.array([self.KD,self.KD]))
            self.event_sender.send({'loop_gains':(self.KP,self.KI,self.KD)})

#-------------------------------------------------------------------------------
    def on_plate_solve(self,param):
        self.plate_solve_success = False
        self.plate_solve_running = True
        self.wcs_hdr_dict = {'WCSSOLVE': 'False'}
        self.plate_solve_ra_mispointing_arcsec = None
        self.plate_solve_dec_mispointing_arcsec = None
        self.event_sender.send({'plate_solve_event':
                                (self.plate_solve_success,
                                 self.plate_solve_running,
                                 self.wcs_hdr_dict,
                                 None,None,None)})

        # Get this from telescope
        coords = {'HA':0.0,
                  'RA':266.5166725/15, 
                  'Dec':-28.9665813,     
                  'equinox':2000,   # not sure this is right (or relevant)
                  'airmass':1.0,
                  'zenith_distance':0.0,
                  'azimuth': 0.0,
                  'sidereal_time':'??',
                  'date': datetime.datetime.utcnow()}
        
        filename = "./images/platesolving/input_image.fits"
        hdr = self.fits_hdr
        hdr['RA'] = coords['RA']*15
        hdr['DEC'] = coords['Dec']
        hdr['PIXSCALE'] = self.arcsec_per_pixel
        hdu = fits.PrimaryHDU(self.image,header=hdr)
        hdulist = fits.HDUList([hdu])
        hdulist.writeto(filename, overwrite=True)
        
        res = self.wcs_acquire(filename,coords)
        self.plate_solve_success = res[0]
        self.targety = res[1]
        self.targetx = res[2]
        self.wcs_hdr_dict = res[3]        
        
        science_fiber_sky = astrometry.pixels2sky(self.wcs_hdr_dict,
                                                  self.sci_fiber_ycenter_pix,
                                                  self.sci_fiber_xcenter_pix)
        print(science_fiber_sky)
        target_skycoord = SkyCoord(hdr['RA'],hdr['DEC'],unit="deg",
                                   frame='fk5')
#        print(science_fiber_sky)
#        print(target_skycoord)
        dra, ddec = science_fiber_sky.spherical_offsets_to(target_skycoord)
        self.plate_solve_ra_mispointing_arcsec = dra.to(u.arcsec).value
        self.plate_solve_dec_mispointing_arcsec = ddec.to(u.arcsec).value
        print('Pointing error RA: %f" Dec: %f"' %
              (self.plate_solve_ra_mispointing_arcsec,
               self.plate_solve_dec_mispointing_arcsec))
        print('Done with plate solving')
        self.plate_solve_running = False
        self.event_sender.send({'plate_solve_event':
                                (self.plate_solve_success,
                                 self.plate_solve_running,
                                 self.wcs_hdr_dict,res,
                                 self.plate_solve_ra_mispointing_arcsec,
                                 self.plate_solve_dec_mispointing_arcsec)})

#-------------------------------------------------------------------------------
    def on_offset_mount(self,param):
        ra_offset = param[0]
        dec_offset = param[1]
        print('Offsetting mount by RA("): %f DEC ("): %f' %
              (ra_offset,dec_offset))
        if self.telescope_type == 'projector':
            self.telescope.offset_target_object(-1*ra_offset*self.arcsec_per_pixel,-1*dec_offset*self.arcsec_per_pixel)
                                     
#-------------------------------------------------------------------------------
    def set_framing_state(self,param):
        # Not working yet.
        return(0)
    
        if param == 0:
            self.framing = False
            self.cam.stop_framing()
            res = self.event_sender.send({'framing':0})
            print('Stopping camera framing')            
        elif param == 1:
            self.framing = True
            self.cam.start_framing()
            res = self.event_sender.send({'framing':1})
            print('Starting camera framing')
        return(0)

#-------------------------------------------------------------------------------
    def set_exposure_time(self,param):
        print("Got message to set exposure time to %f" % (param,))
        if param >= 0 and param < 1000:
            self.cam.set_exposure_time(param)
            res = self.event_sender.send({'exposure_time':self.cam.get_exposure_time()})                                    
            res = self.event_sender.send({'cadence':self.cam.get_frame_period()})
        return(0)

#-------------------------------------------------------------------------------
    def set_cadence(self,param):
        print("Got message to set cadence to %f" % (param,))
        if param >= 0 and param < 1000:
            self.cam.set_frame_period(param)
            res = self.event_sender.send({'cadence':self.cam.get_frame_period()})
            res = self.event_sender.send({'exposure_time':self.cam.get_exposure_time()})            
        return(0)

    
#-------------------------------------------------------------------------------
    def toggle_framing_state(self,param):
        if param > 0:
            if self.framing:
                self.cam.stop_framing()
                self.framing = False
                res = self.event_sender.send({'framing':0})
                print('Stopping camera framing')
            elif param == 0:
                self.framing = True
                self.cam.start_framing()
                res = self.event_sender.send({'framing':1})
                print('Starting camera framing')
        return(0)
    
#-------------------------------------------------------------------------------
    def validate_roi(self,y1,x1,y2,x2):
        if x1 >= x2:
            return(False)
        if y1 >= y2:
            return(False)
        if (x2-x1 > self.camera_xdim):
            return(False)
        if (y2-y1 > self.camera_ydim):
            return(False)
        if x1 < 0:
            return(False)
        if y1 < 0:
            return(False)
        if x1 > self.camera_xdim-1:
            return(False)
        if y1 > self.camera_ydim-1:
            return(False)
        if x2 > self.camera_xdim-1:
            return(False)
        if y2 > self.camera_ydim-1:
            return(False)
        return(True)
        
#-------------------------------------------------------------------------------
    def set_roi(self,param):
        print(param)
        print(len(param))
        if len(param) != 4:
            return(-1)
        
#        res = self.validate_roi(param[0],param[1],param[2],param[3])
#        if not res:
#            print("Error validating ROI")
#            return(False)
        
        self.cam.set_roi(param[0],param[1],param[2],param[3])
        
        return(0)
    
#-------------------------------------------------------------------------------
    def set_star_roi(self,param):
        # Pass in [Y,X]
        print("In set_star_roi")
        if len(param) != 2:
            return(-1)
        
#        res = self.validate_star_position(param[0],param[1])
#        if not res:
#            print("Error validating ROI")
#            return(False)

        star_roi_xcenter_pix = param[1]
        star_roi_ycenter_pix = param[0]

        # Convert to arcseconds from on-axis
        self.star_xcenter = ((star_roi_xcenter_pix  -
                              (self.camera_xdim_pix/2) + 
                              self.cam_decenter_x_pixels) * 
                             self.arcsec_per_pixel)
        self.star_ycenter = ((star_roi_ycenter_pix -
                              (self.camera_ydim_pix/2) + 
                              self.cam_decenter_y_pixels) *
                             self.arcsec_per_pixel)
        print("Setting offset star position to pixels x:%f y:%f, x:%f y:%f arcsec from on-axis" %
              (star_roi_xcenter_pix,star_roi_ycenter_pix,
               self.star_xcenter,self.star_ycenter))
        
        return(0)

#-------------------------------------------------------------------------------
    def command_callback(self,command_dict):
        '''
        This is where events from the GUI arrive, and we act on them.
        '''
        for command in command_dict:
            try:
                res = self.command_tree[command](command_dict[command])
            except Exception as e:
                print(e)
        print("Done with command processing")

#------------------------------------------------------------------------------
    def sky_to_cam(self,north_arcsec,east_arcsec):
        '''
        Takes north, east angles and converts to x,y angles
        '''
        ycen_pixels  = (self.sign * self.steps_per_arcsec_tip *
                    (north_arcsec * math.cos(self.cam_rotation_rad) -
                     east_arcsec * math.sin(self.cam_rotation_rad)))
        xcen_pixels = (self.steps_per_arcsec_tilt *
                    (north_arcsec * math.sin(self.cam_rotation_rad) +
                     east_arcsec * math.cos(self.cam_rotation_rad)))
        
        return(ycen_pixels,xcen_pixels)

#------------------------------------------------------------------------------
    def cam_to_sky(self,ycen_pixels,xcen_pixels):
        '''
        Takes y, x angles and rotatotes to north, east angles
        '''        
        
        ycen_arcsec = ((ycen_pixels - self.camera_ycenter_pix) *
                       self.arcsec_per_pixel / self.sign)
        xcen_arcsec = ((xcen_pixels - self.camera_xcenter_pix) *
                       self.arcsec_per_pixel)
        
        north_arcsec  = (ycen_arcsec * math.cos(self.cam_rotation_rad) +
                         xcen_arcsec * math.sin(self.cam_rotation_rad))
        east_arcsec = (-1* ycen_arcsec * math.sin(self.cam_rotation_rad) +
                       xcen_arcsec * math.cos(self.cam_rotation_rad))
        
        return(north_arcsec,east_arcsec)

#------------------------------------------------------------------------------ 
    def wcs_acquire(self,image_name,mount_coords,offset=(0.0,0.0),
                    verbose=False, use_centroid=True):
        ''' Plate solve image to compute RA/Dec of pixel grid'''
        t0 = datetime.datetime.utcnow()
        
        # get target position from TCS
        targetra = mount_coords['RA']*15.0 # convert to degrees
        targetdec = mount_coords['Dec']
        equinox = mount_coords['equinox']

#        # or do we want read_target_object_coordinates??
#        # is there a practical difference?
#        # we don't want to initiate large slews this way...
#        coords = self.telescope.read_target_object_coordinates()
#        targetra = coords['mean_ra']*15.0 # convert to degrees
#        targetdec = coords['mean_dec']
#        equinox = coords['equinox']
        
        # do a plate solve on the image
        # we could probably shave off a few seconds
        # if it worked with a star list, not an image...
        (self.plate_solve_success,self.wcs_hdr_dict) = astrometry.astrometry(image_name,radius=0.1,
                                                                   logger=self.logger, verbose=verbose)
        if self.plate_solve_success:
            # identify target
            targetx,targety = astrometry.sky2pixels(self.wcs_hdr_dict,
                                                    targetra,targetdec)

            if targetx < self.x1 or targety < self.y1 or \
               targetx > self.x2 or targety > self.y2:
                if use_centroid:
                    self.logger.warning("Centroid requested, but star is outside the frame, using input coordinates")
                    use_centroid=False
                
            self.logger.info("Target RA=" + str(targetra) + " (deg), Dec=" + str(targetdec) +\
                             " (deg) is at (x,y)=(" + str(targetx) + "," + str(targety) + ")")

            self.logger.info("WCS-based acquisition finished in " + str((datetime.datetime.utcnow() - t0).total_seconds()) + " seconds")
                
            # slew telescope
#            return self.acquire(targetx,targety, offset=offset, use_centroid=use_centroid)
            return (True,targety,targetx,self.wcs_hdr_dict)
        else:
            self.logger.error("WCS Solution failed -- try longer exposure or acquire by click")
            return (False,None,None,self.wcs_hdr_dict)
    
#-------------------------------------------------------------------------------
    def perform_guiding(self,image,camera_ydim_pix,camera_xdim_pix,y1,y2,x1,x2):
        '''
        This is where the action happens.
        Find stars in image and compute centroids of starlike objects.
        Use star closest to desired position and use for feedback
        '''

        # Find stars and compute centroids in pixels
        self.stars = self.sep_image_processor.get_stars(image)

        if (len(self.stars) == 0):
            self.logger.info("No stars passed to perform_guiding.")
            self.ndx = 0
            self.x_mispointings_arcsec = [0.0]
            self.y_mispointings_arcsec = [0.0]
            self.ra_mispointings_arcsec = [0.0]
            self.dec_mispointings_arcsec = [0.0]
            self.x_correction_arcsec = 0.0
            self.y_correction_arcsec = 0.0
            self.ra_correction_arcsec = 0.0
            self.dec_correction_arcsec = 0.0
            self.flux_counts = 0.0
            self.peak_counts = 0.0
            self.star_fwhm = 0.0
            self.stars = np.array([])
            return
        else:
            print("Guiding on %i stars" % (len(self.stars)))

        # Add bottom left corner of ROI in order to have centroids be with
        # respect to full camera frame and then offset to place 0,0 in the
        # center of the camera
        self.stars[:,0] += x1 - camera_xdim_pix/2
        self.stars[:,1] += y1 - camera_ydim_pix/2
        
        # find the closest star to the desired science fiber position, keeping
        # offsets in mind. Fiber positions and offsets are in arcseconds, so
        # convert them to pixels
        x_errors_pixels = self.stars[:,0] + \
                          self.cam_decenter_x_pixels - \
            ((self.sci_fiber_x + self.offset[0]) / self.arcsec_per_pixel)
        y_errors_pixels = self.stars[:,1] + \
                          self.cam_decenter_y_pixels - \
            ((self.sci_fiber_y - self.offset[1]) / self.arcsec_per_pixel)

        self.x_mispointings_arcsec = x_errors_pixels * self.arcsec_per_pixel
        self.y_mispointings_arcsec = y_errors_pixels * self.arcsec_per_pixel
        
        # Compute star distance from trackpoint in arcseconds
        dists_arcsec = np.sqrt(x_errors_pixels**2 + y_errors_pixels**2) * \
            self.arcsec_per_pixel

        # Find index of closest star to trackpoint
        self.ndx = np.argmin(dists_arcsec)

        self.logger.info("Using guide star "+ str(self.ndx) +" (" +
                         str(self.stars[self.ndx,0] * self.arcsec_per_pixel) + \
                         ',' + str(self.stars[self.ndx,1] * \
                                   self.arcsec_per_pixel) +
                         ') dist: ' + str(dists_arcsec[self.ndx]) +
                         ' arcsec from the requested position Trackpoint:(' +
                         str(self.sci_fiber_x - self.offset[0]) + ',' +
                         str(self.sci_fiber_y - self.offset[1]) + ')')
        
        # if the star disappears, don't correct to a different star
        # magnitude tolerance, too? (probably not -- clouds could cause trouble)
        if (dists_arcsec[self.ndx] < self.guiding_tolerance):
            # Set desired position of star to be on the fiber, plus whatever
            # offset we want on top of that.
            self.pid.setPoint((self.sci_fiber_y - self.offset[1],
                               self.sci_fiber_x - self.offset[0]))

            # calculate the X & Y corrections needed in this step of the PID
            # loop in arcsec
            self.y_correction_arcsec,self.x_correction_arcsec = \
                self.pid.update(np.array([self.stars[self.ndx,1] *
                                          self.arcsec_per_pixel,
                                          self.stars[self.ndx,0] *
                                          self.arcsec_per_pixel]))
            self.logger.info('X Correction": '+ str(self.x_correction_arcsec) +\
                             ' Y Correction": ' + str(self.y_correction_arcsec))
                         
            if ((self.cam_type == 'simulated' or self.cam_type == 'zyla'
                 or self.cam_type == 'asi') and self.loop_state == 'closed'):
                self.cam.set_simulated_fsm_correction(self.y_correction_arcsec,
                                                      self.x_correction_arcsec)
            
            # convert X & Y pixel to North & East arcsec offset
            # don't need cos(dec) term unless we send via mount
            PA = 0.0 # get from Telescope? Config file? user?

            self.dec_mispointings_arcsec = \
                (self.x_mispointings_arcsec * math.cos(PA) -
                 self.y_mispointings_arcsec * math.sin(PA))
            self.ra_mispointings_arcsec  = \
                (self.x_mispointings_arcsec * math.sin(PA) +
                 self.y_mispointings_arcsec * math.cos(PA))
                
            self.dec_correction_arcsec = \
                (self.x_correction_arcsec * math.cos(PA) - \
                 self.y_correction_arcsec * math.sin(PA))
            self.ra_correction_arcsec  = \
                (self.x_correction_arcsec * math.sin(PA) + \
                 self.y_correction_arcsec * math.cos(PA))

            self.flux_counts = self.stars[self.ndx,2]
            self.star_fwhm = 1.0+np.random.uniform(low=-0.1,high=0.1)

            if self.loop_state == 'closed':
                self.tiptilt.move_north_east(
                    self.y_mispointings_arcsec[self.ndx],
                    self.y_mispointing_arcsec[self.ndx])
            # TODO: make sure the move is within range
            # move_in_range = True
                
            # # send correction to tip/tilt
            # if move_in_range:
            #     self.logger.info("Moving tip/tilt " + str(north) +
            #                      '" North, ' + str(east) + '" East')
            #     self.tiptilt.move_north_east(north,east)
            # else:
            #     # TODO: move telescope, recenter tip/tilt
            #     self.logger.error("Tip/tilt out of range. Must manually recenter")
        else:
            self.x_correction_arcsec = 0.0
            self.y_correction_arcsec = 0.0
            self.ra_mispointings_arcsec = [0.0] * len(self.stars)
            self.dec_mispointings_arcsec = [0.0] * len(self.stars)
            self.ra_correction_arcsec = 0.0
            self.dec_correction_arcsec = 0.0
            self.flux_counts = 0.0
            self.peak_counts = 0.0
            self.star_fwhm = 0.0

#-------------------------------------------------------------------------------
    def perform_offset_guiding(self,image,camera_ydim_pix,camera_xdim_pix,
                               y1,y2,x1,x2):
        '''
        This is where the action happens.
        Find stars in image and compute centroids of starlike objects.
        Use star closest to desired position and use for feedback
        '''

        # Find stars and compute centroids in pixels
        self.stars = self.sep_image_processor.get_stars(image)

        if (len(self.stars) != 1):
            self.logger.info("No or multiple stars passed to perform_guiding.")
            self.ndx = 0
            self.x_mispointings_arcsec = [0.0]
            self.y_mispointings_arcsec = [0.0]
            self.ra_mispointings_arcsec = [0.0]
            self.dec_mispointings_arcsec = [0.0]
            self.x_correction_arcsec = 0.0
            self.y_correction_arcsec = 0.0
            self.ra_correction_arcsec = 0.0
            self.dec_correction_arcsec = 0.0
            self.flux_counts = 0.0
            self.peak_counts = 0.0
            self.star_fwhm = 0.0
            self.stars = np.array([])
            return
        else:
            print("Guiding on %i stars" % (len(self.stars)))

        self.ndx = 0
        roi_xdim_pix = x2-x1
        roi_ydim_pix = y2-y1
        # Add bottom left corner of ROI in order to have centroids be with
        # respect to full camera frame and then offset to place 0,0 in the
        # center of the camera
        self.stars[:,0] -= roi_xdim_pix/2
        self.stars[:,1] -= roi_ydim_pix/2
        
        x_errors_pixels = (self.stars[:,0] -
                           self.offset[0] / self.arcsec_per_pixel)
        y_errors_pixels = (self.stars[:,1] -
                           self.offset[1] / self.arcsec_per_pixel)

        self.x_mispointings_arcsec = x_errors_pixels * self.arcsec_per_pixel
        self.y_mispointings_arcsec = y_errors_pixels * self.arcsec_per_pixel
        
        self.logger.info("Using guide star (" +
                         str(self.stars[self.ndx,0] *
                             self.arcsec_per_pixel) + \
                         ',' + str(self.stars[self.ndx,1] * \
                                   self.arcsec_per_pixel))
        
        self.pid.setPoint((-1*self.offset[1],-1*self.offset[0]))

        # calculate the X & Y corrections needed in this step of the PID
        # loop in arcsec
        self.y_correction_arcsec,self.x_correction_arcsec = \
            self.pid.update(np.array([self.stars[self.ndx,1] *
                                      self.arcsec_per_pixel,
                                      self.stars[self.ndx,0] *
                                      self.arcsec_per_pixel]))
        self.logger.info('X Correction": '+ str(self.x_correction_arcsec) +\
                         ' Y Correction": ' + str(self.y_correction_arcsec))
                         
        # convert X & Y pixel to North & East arcsec offset
        # don't need cos(dec) term unless we send via mount
        PA = 0.0 # get from Telescope? Config file? user?

        self.dec_mispointings_arcsec = \
                (self.x_mispointings_arcsec * math.cos(PA) -
                 self.y_mispointings_arcsec * math.sin(PA))
        self.ra_mispointings_arcsec  = \
                (self.x_mispointings_arcsec * math.sin(PA) +
                 self.y_mispointings_arcsec * math.cos(PA))
                
        self.dec_correction_arcsec = \
                (self.x_correction_arcsec * math.cos(PA) - \
                 self.y_correction_arcsec * math.sin(PA))
        self.ra_correction_arcsec  = \
                (self.x_correction_arcsec * math.sin(PA) + \
                 self.y_correction_arcsec * math.cos(PA))

        self.flux_counts = self.stars[self.ndx,2]
        self.star_fwhm = 1.0+np.random.uniform(low=-0.1,high=0.1)

        if self.loop_state == 'closed':
            self.tiptilt.move_north_east(
                -0.8*self.y_mispointings_arcsec[self.ndx],
                -0.8*self.x_mispointings_arcsec[self.ndx])

#-------------------------------------------------------------------------------
    def perform_annulus_guiding(self,guiding_mode,image,
                                camera_ydim_pix,camera_xdim_pix,y1,y2,x1,x2):
        '''
        This is where the action happens.
        Use annulus algorithm specified by guiding mode on science fiber ROI.
        '''

        # Compute centroid in pixels
        if self.guiding_mode == 'annulus_sep':
            self.stars = self.sep_image_processor.get_stars(image)
        elif self.guiding_mode == 'annulus_quad':
            self.stars = self.quad_image_processor.get_stars(image)
        elif self.guiding_mode == 'annulus_model':
            self.stars = self.model_image_processor.get_stars(image)
            
        if (len(self.stars) != 1):
            self.logger.info("No or multiple stars passed to perform_guiding.")
            self.ndx = 0
            self.x_mispointings_arcsec = [0.0]
            self.y_mispointings_arcsec = [0.0]
            self.ra_mispointings_arcsec = [0.0]
            self.dec_mispointings_arcsec = [0.0]
            self.x_correction_arcsec = 0.0
            self.y_correction_arcsec = 0.0
            self.ra_correction_arcsec = 0.0
            self.dec_correction_arcsec = 0.0
            self.flux_counts = 0.0
            self.peak_counts = 0.0
            self.star_fwhm = 0.0
            self.stars = np.array([])
            return
        else:
            print("Guiding on %i stars" % (len(self.stars)))

        self.ndx = 0
        roi_xdim_pix = x2-x1
        roi_ydim_pix = y2-y1
        # Add bottom left corner of ROI in order to have centroids be with
        # respect to full camera frame and then offset to place 0,0 in the
        # center of the camera
        self.stars[:,0] -= roi_xdim_pix/2
        self.stars[:,1] -= roi_ydim_pix/2
        
        x_errors_pixels = (self.stars[:,0] -
                           self.offset[0] / self.arcsec_per_pixel)
        y_errors_pixels = (self.stars[:,1] -
                           self.offset[1] / self.arcsec_per_pixel)

        self.x_mispointings_arcsec = x_errors_pixels * self.arcsec_per_pixel
        self.y_mispointings_arcsec = y_errors_pixels * self.arcsec_per_pixel
        
        self.logger.info("Using guide star (" +
                         str(self.stars[self.ndx,0] *
                             self.arcsec_per_pixel) + \
                         ',' + str(self.stars[self.ndx,1] * \
                                   self.arcsec_per_pixel))
        
        self.pid.setPoint((-1*self.offset[1],-1*self.offset[0]))

        # calculate the X & Y corrections needed in this step of the PID
        # loop in arcsec
        self.y_correction_arcsec,self.x_correction_arcsec = \
            self.pid.update(np.array([self.y_mispointings_arcsec[self.ndx],
                                      self.x_mispointings_arcsec[self.ndx]]))
        
        self.logger.info('Y Correction": '+ str(self.y_correction_arcsec) +\
                         ' X Correction": ' + str(self.x_correction_arcsec))
                         
        # convert X & Y pixel to North & East arcsec offset
        # don't need cos(dec) term unless we send via mount
        PA = 0.0 # get from Telescope? Config file? user?

        self.dec_mispointings_arcsec = \
                (self.x_mispointings_arcsec * math.cos(PA) -
                 self.y_mispointings_arcsec * math.sin(PA))
        self.ra_mispointings_arcsec  = \
                (self.x_mispointings_arcsec * math.sin(PA) +
                 self.y_mispointings_arcsec * math.cos(PA))
                
        self.dec_correction_arcsec = \
                (self.x_correction_arcsec * math.cos(PA) - \
                 self.y_correction_arcsec * math.sin(PA))
        self.ra_correction_arcsec  = \
                (self.x_correction_arcsec * math.sin(PA) + \
                 self.y_correction_arcsec * math.cos(PA))

        self.flux_counts = self.stars[self.ndx,2]
        self.star_fwhm = 1.0+np.random.uniform(low=-0.1,high=0.1)

        if self.loop_state == 'closed':
#            self.tiptilt.move_north_east(
#                -0.8*self.y_mispointings_arcsec[self.ndx],
#                -0.8*self.x_mispointings_arcsec[self.ndx])
            self.tiptilt.move_north_east(self.y_correction_arcsec,
                                         self.x_correction_arcsec)
            

#-------------------------------------------------------------------------------
    def send_telemetry(self):

#        self.telem_image = self.image.astype(np.uint16)
        h, w = self.image.shape
#        shape = struct.pack('>II',h,w)
#        encoded_img = self.telem_image.tobytes()

        img_base64 = base64.b64encode(self.image.astype(np.uint16))
        sci_roi_base64 = base64.b64encode(self.sci_roi.astype(np.uint16))
        sky_roi_base64 = base64.b64encode(self.sky_roi.astype(np.uint16))
        star_roi_base64 = base64.b64encode(self.star_roi.astype(np.uint16))
        fsm_position = self.tiptilt.get_position()
        ENCODING = 'utf-8'

        telem_struct = \
            json.dumps({'timestamp':\
                        self.dateobs.strftime('%Y-%m-%dT%H:%M:%S.%f'),
                        'loop_state':self.loop_state,
                        'guiding_mode':self.guiding_mode,
                        'x_mispointing':self.x_mispointings_arcsec[self.ndx],
                        'y_mispointing':self.y_mispointings_arcsec[self.ndx],
                        'ra_mispointing':self.ra_mispointings_arcsec[self.ndx],
                        'dec_mispointing':self.dec_mispointings_arcsec[self.ndx],
                        'x_correction':self.x_correction_arcsec,
                        'y_correction':self.y_correction_arcsec,
                        'ra_correction':self.ra_correction_arcsec,
                        'dec_correction':self.dec_correction_arcsec,
                        'counts':self.flux_counts,
                        'peak_counts':self.peak_counts,
                        'fwhm':self.star_fwhm,
                        'platescale':self.arcsec_per_pixel,
                        'camera_xdim_pix':self.camera_xdim_pix,
                        'camera_ydim_pix':self.camera_ydim_pix,
                        'roi_x1':self.x1,
                        'roi_x2':self.x2,
                        'roi_y1':self.y1,
                        'roi_y2':self.y2,
                        'height':h,
                        'width':w,
                        'sci_fiber_x':self.sci_fiber_x,
                        'sci_fiber_xwidth':self.sci_fiber_xwidth,
                        'sci_hole_xwidth':self.sci_hole_xwidth,
                        'sky_fiber_x':self.sky_fiber_x,
                        'sky_fiber_xwidth':self.sky_fiber_xwidth,
                        'sky_hole_xwidth':self.sky_hole_xwidth,
                        'guider_magnification':self.guider_magnification,
                        'arcsec_per_um_guider_ccd':self.arcsec_per_um_guider_ccd,
                        'sci_fiber_y':self.sci_fiber_y,
                        'sci_fiber_ywidth':self.sci_fiber_ywidth,
                        'sci_hole_ywidth':self.sci_hole_ywidth,
                        'sky_fiber_y':self.sky_fiber_y,
                        'sky_fiber_ywidth':self.sky_fiber_ywidth,
                        'sky_hole_ywidth':self.sky_hole_ywidth,
                        'sci_roi_x1':self.sci_roi_x1,
                        'sci_roi_x2':self.sci_roi_x2,
                        'sci_roi_y1':self.sci_roi_y1,
                        'sci_roi_y2':self.sci_roi_y2,
                        'sky_roi_x1':self.sky_roi_x1,
                        'sky_roi_x2':self.sky_roi_x2,
                        'sky_roi_y1':self.sky_roi_y1,
                        'sky_roi_y2':self.sky_roi_y2,
                        'star_roi_x1':self.star_roi_x1,
                        'star_roi_x2':self.star_roi_x2,
                        'star_roi_y1':self.star_roi_y1,
                        'star_roi_y2':self.star_roi_y2,
                        'camera_xcenter_pix':self.camera_xcenter_pix,
                        'camera_ycenter_pix':self.camera_ycenter_pix,
                        'guiding_offset_x':self.offset[0],
                        'guiding_offset_y':self.offset[1],
                        'fsm_angle_x':fsm_position['E'],
                        'fsm_angle_y':fsm_position['N'],
                        'sky_fiber_xcenter_pix':self.sky_fiber_xcenter_pix,
                        'sky_fiber_ycenter_pix':self.sky_fiber_ycenter_pix,
                        'pixel_size_um':self.pixel_size_um,
                        'arcsec_per_um_guider_ccd':self.arcsec_per_um_guider_ccd,
                        'exposure_time':self.cam.get_exposure_time(),
                        'cadence':self.cam.get_frame_period(),                        
                        'sensor_temp':self.cam.get_sensor_temp(),
                        'sensor_temp_status':self.cam.get_sensor_temp_status(),
                        'frame_counter':self.cam.get_frame_counter(),
                        'loop_kp':self.KP,
                        'loop_ki':self.KI,
                        'loop_kd':self.KD,
                        'plate_solve_success': self.plate_solve_success,
                        'plate_solve_running': self.plate_solve_running,
                        'plate_solve_ra_mispointing_arcsec': self.plate_solve_ra_mispointing_arcsec,
                        'plate_solve_dec_mispointing_arcsec': self.plate_solve_dec_mispointing_arcsec,
#                        'fits_hdr':self.fits_hdr,
                        'wcs_hdr_dict': self.wcs_hdr_dict,
                        'stars':self.stars.tolist(),
                        'image':img_base64.decode(ENCODING),
                        'sci_roi':sci_roi_base64.decode(ENCODING),
                        'sky_roi':sky_roi_base64.decode(ENCODING),
                        'star_roi':star_roi_base64.decode(ENCODING)})

        self.telem_out.send('guider_data',telem_struct)

            
#-------------------------------------------------------------------------------
    def start(self):
        self.cam.start()
        self.framing = True
        print("Camera framing started")

#-------------------------------------------------------------------------------
    def stop(self):
        self.cam.stop_framing()
        self.framing = False


################################################################################
if __name__ == "__main__":
    base_directory = "./"
    
    guider = GuidingSystem(base_directory,
                           cam_type='andor',
                           tiptilt_type='pi',
                           calstage_type='simulated',
                           telescope_type='projector')
    guider.start()
    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    finally:
        loop.close()
    print("TRES Guider stopping")

    
