#!/usr/bin/python3
from astropy.io import fits
from pyAndorSDK3 import AndorSDK3
import numpy as np
import socket
import os, sys, time
import utils
from configobj import ConfigObj
import ipdb
import logging
import datetime
import pid
from get_all_centroids import *
import threading
import math
from guider import imager
from calstage import calstage
from tiptilt import tiptilt
import redis
import json


class tres:

    def __init__(self, base_directory, config_file, logger=None, calstage_simulate=False, tiptilt_simulate=False, guider_simulate=False):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'tres')
        else: self.logger = logger

        # read the config file
        config = ConfigObj(self.config_file)

        # read the config file
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        self.redis = redis.StrictRedis(host=config['REDIS_SERVER'],
                                       port=config['REDIS_PORT'])
        self.pub_tracking_data = self.redis.pubsub()
        
        self.redis.set('state','Starting')
        self.redis.set('errors','None')
            
        # set up the devices
        self.guider = imager(base_directory, 'zyla.ini', logger=self.logger, simulate=guider_simulate)
        self.calstage = calstage(base_directory, 'calstage.ini', logger=self.logger, simulate=calstage_simulate)
        self.tiptilt = tiptilt(base_directory, 'tiptilt.ini', logger=self.logger, simulate=tiptilt_simulate)
        
        # connect the devices
        self.tiptilt.connect()
        self.calstage.connect()
        self.redis.set('state','Initialized')
        self.redis.publish('tracking_data',json.dumps({'timestamp':datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f') ,'x_mispointing':0.0,'y_mispointing':0.0,'north_mispointing':0.0,'east_mispointing':0.0,'dx':0.0,'dy':0.0,'north':0.0,'east':0.0,'counts':0,'fwhm':1.0,'platescale':0.0,'roi_x1':0,'roi_x2':0,'roi_y1':0,'roi_y2':0}))

        
    # this assumes there are is no confusion (within tolerance) and each offset is small (< tolerance)
    # annulus guiding (pick star closest to fiber and guide)                     -- done
    # offset guiding (pick star closest to position offset from fiber and guide) -- done
    # platesolve and guide to RA/Dec -- TODO (enough stars?)
    # platesolve and guide to Star closest to RA/Dec -- TODO (enough stars?)
    # exptime - the exposure time, in seconds
    # offset - a tuple describing the (x,y) offset from the fiber. Pick the star closest to there and keep it there.
    # tolerance - beyond this tolerance (arcsec), don't guide
    # simulate - Boolean. If true, will use a simulated stellar image
    # save - boolean. If true, it will save the guider images (and increase overhead)
    # subframe - Boolean. If true, it will use a 3*tolerance subframe to guide (decrease overhead). 
    def guide(self, exptime, offset=(0.0,0.0), tolerance=3.0, simulate=False, save=False, subframe=True):

        self.redis.set('state','Guiding')
        # move to the middle of the range
        self.tiptilt.move_tip_tilt(1.0,1.0)
        
        # load the PID servo parameters
        p=pid.PID(P=np.array([self.guider.KPx, self.guider.KPy]),
                  I=np.array([self.guider.KIx, self.guider.KIy]),
                  D=np.array([self.guider.KDx, self.guider.KDy]),
                  Integrator_max = self.guider.Imax,
                  Deadband = self.guider.Dband,
                  Correction_max = self.guider.Corr_max)

        # TODO: refine fiber position on the chip (does it change? do it elsewhere?)

        # load the PID set point
        p.setPoint((self.guider.x_science_fiber+offset[0], self.guider.y_science_fiber+offset[1]))
        
        # TODO: pick guide star, move it to fiber via telescope (pre-load tip/tilt?)
        # requires TCS communication (current functionality requires observer to do this)
        
        # main loop
        while self.guider.guiding:

            # set the subframe
            if subframe:
                subframesize = int(round(1.5*tolerance/self.guider.platescale))
                if (subframesize % 2) == 1: subframesize +=1 # make sure it's even
                x1 = int(round(self.guider.x_science_fiber + offset[0] - subframesize))
                x2 = int(round(self.guider.x_science_fiber + offset[0] + subframesize))
                y1 = int(round(self.guider.y_science_fiber + offset[1] - subframesize))
                y2 = int(round(self.guider.y_science_fiber + offset[1] + subframesize))
                self.guider.set_roi(x1,x2,y1,y2)
            
            if simulate:
                t0 = datetime.datetime.utcnow()
                xstar = int(round(self.guider.x_science_fiber + np.random.uniform(low=-1.0,high=1.0)))
                ystar = int(round(self.guider.y_science_fiber + np.random.uniform(low=-1.0,high=1.0)))
                self.guider.simulate_star_image([xstar],[ystar],[1e6], 1.5, noise=10.0)
                elapsed_time = (datetime.datetime.utcnow()-t0).total_seconds()
            else:
                # expose while we get the header info
                expose_thread = threading.Thread(target=self.guider.take_image, args=(exptime,))
                expose_thread.name = 'guider_expose_thread'
                expose_thread.start()

            # get the header info
            if save: hdr = self.get_header()
            
            # wait for the exposure to complete
            if simulate:
                if elapsed_time < exptime:
                    time.sleep(exptime-elapsed_time)
            else: expose_thread.join()

            # save the image
            if save:
                objname = 'test'
                files = glob.glob(self.guider.datapath + "*.fits")
                index = str(len(files)+1).zfill(4)
                datestr = datetime.datetime.utcnow().strftime('%m%d%y') 
                filename = self.guider.datapath + objname + '.' + datestr + '.guider.' + index + '.fits'

                # saving can go on in the background
                kwargs={'hdr':hdr}
                save_image_thread = threading.Thread(target=self.guider.save_image,args=(filename,),kwargs=kwargs)
                save_image_thread.name = 'save_image_thread'
                save_image_thread.start()
                
                #self.guider.save_image(filename, hdr=hdr)

            self.logger.info("Finding stars")
            stars = self.guider.get_stars()
            
            if len(stars) == 0:
                self.logger.warning("No guide stars in image; skipping correction")
                if save: save_image_thread.join()
                continue

            # find the closest star to the desired position                            
            dx = stars[:,0] - (self.guider.x_science_fiber-offset[0])
            dy = stars[:,1] - (self.guider.y_science_fiber-offset[1])
            dist = np.sqrt(dx*dx + dy*dy)*self.guider.platescale
            ndx = np.argmin(dist)
            self.logger.info("Using guide star (" + str(stars[ndx,0]) + ',' +
                             str(stars[ndx,1]) + ') ' + str(dist[ndx]) +
                             ' pixels from the requested position (' +
                             str(self.guider.x_science_fiber-offset[0]) + ',' +
                             str(self.guider.y_science_fiber-offset[1]) + ')')

            # if the star disappears, don't correct to a different star
            # magnitude tolerance, too? (probably not -- clouds could cause trouble)
            if dist < tolerance:
                p.setPoint((self.guider.x_science_fiber+offset[0],self.guider.y_science_fiber+offset[1]))

                # calculate the X & Y pixel offsets
                dx,dy = p.update(np.array([stars[ndx,0],stars[ndx,1]]))
                
                # convert X & Y pixel to North & East arcsec offset
                # don't need cos(dec) term unless we send via mount
                PA = 0.0 # get from Telescope? Config file? user?

                north_mispointing = self.guider.platescale*(stars[ndx,0]*math.cos(PA) - stars[ndx,1]*math.sin(PA))
                east_mispointing  = self.guider.platescale*(stars[ndx,0]*math.sin(PA) + stars[ndx,1]*math.cos(PA))
                
                north = self.guider.platescale*(dx*math.cos(PA) - dy*math.sin(PA))
                east  = self.guider.platescale*(dx*math.sin(PA) + dy*math.cos(PA))

                self.redis.publish('tracking_data',json.dumps({'timestamp':datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f'),'x_mispointing':stars[ndx,0],'y_mispointing':stars[ndx,1],'north_mispointing':north_mispointing,'east_mispointing':east_mispointing,'dx':dx,'dy':dy,'north':north,'east':east,'counts':stars[ndx,2],'fwhm':1.0+np.random.uniform(low=-0.1,high=0.1),'platescale':self.guider.platescale,'roi_x1':x1,'roi_x2':x2,'roi_y1':y1,'roi_y2':y2}))
                
                # TODO: make sure the move is within range
                move_in_range = True
                
                # send correction to tip/tilt
                if move_in_range:
                    self.logger.info("Moving tip/tilt " + str(north) + '" North, ' + str(east) + '" East')
                    self.tiptilt.move_north_east(north,east)
                else:
                    # TODO: move telescope, recenter tip/tilt
                    self.logger.error("Tip/tilt out of range. Must manually recenter")
            else: self.logger.warning("Guide star too far away; skipping correction")
                    
            # make sure the image is saved first
            if save: save_image_thread.join()

                    
    def take_image(self, filename, exptime, overwrite=False):

        # expose while we get the header info
        expose_thread = threading.Thread(target=self.guider.take_image, args=(exptime,))
        expose_thread.name = 'guider_expose_thread'
        expose_thread.start()

        # get the header info
        hdr = self.get_header()

        # wait for the exposure to complete
        expose_thread.join()
        
        # save the image
        self.guider.save_image(filename, hdr=hdr, overwrite=overwrite)
        
    def get_header(self):

        hdr = fits.Header()

        # placeholders might be wrong if we populated them now. let guider.save_image populate them
        hdr['DATE-OBS'] = ('','YYYY-MM-DDThh:mm:ss.ssssss (UTC)') # placeholder
        hdr['EXPTIME'] = ('','Exposure time (s)') # placeholder
        hdr['PIXSCALE'] = (self.guider.platescale,'arcsec/pixel')
        hdr['GAIN'] = (self.guider.gain,'electrons/ADU')
        hdr['DATASEC'] = ('',"Region of CCD read") # placeholder
        hdr['CCDSUM'] = ('','CCD on-chip summing') # placeholder

        hdr['INSTRUME'] = ('TRES','Name of the instrument')
        hdr['OBSERVER'] = ('',"Observer") # do we have this info?

        # Camera info
        hdr['CAMMOD'] = (self.guider.model,'Model of the acquisition camera')
        hdr['CAMERASN'] = (self.guider.sn,'Serial number of the acquisition camera')
        hdr['CCD-TEMP'] = (-999,'CCD Temperature (C)') # do we have this?

        # Calibration stage info
        hdr['CSPOS'] = (self.calstage.get_position_string(),"Position of the cal stage (string)")
        hdr['CSPOSN'] = (self.calstage.get_position(),"Position of the cal stage (mm)")
        hdr['CSMODEL'] = (self.calstage.model,"Model Number of the cal stage")
        hdr['CSSN'] = (self.calstage.sn,"Serial number of the calibration stage")
        hdr['CSCMODEL'] = (self.calstage.model_controller,"Model of the cal stage controller")
        hdr['CSCSN'] = (self.calstage.sn_controller,"Serial number of the cal stage controller")

        # Tip/Tilt stage info
        ttpos = self.tiptilt.get_position()
        hdr['TTTIPPOS'] = (ttpos['A'],"Tip Position of the tip/tilt stage (urad)")
        hdr['TTTILPOS'] = (ttpos['B'],"Tilt Position of the tip/tilt stage (urad)")
        hdr['TTMODEL'] = (self.tiptilt.model,"Model number of the tip/tilt stage")
        hdr['TTSN'] = (self.tiptilt.sn,"Serial number of the tip/tilt stage")
        hdr['TTCMODEL'] = (self.tiptilt.model_controller,"Model number of the tip/tilt stage controller")
        hdr['TTCSN'] = (self.tiptilt.sn_controller,"Serial number of the tip/tilt stage controller")

        # Fiber info
        hdr['XSCIFIB'] = (self.guider.x_science_fiber,'X pixel of science fiber centroid')
        hdr['YSCIFIB'] = (self.guider.y_science_fiber,'Y pixel of science fiber centroid')
        hdr['XSKYFIB'] = (self.guider.x_sky_fiber,'X pixel of sky fiber centroid')
        hdr['YSKYFIB'] = (self.guider.y_sky_fiber,'Y pixel of sky fiber centroid')
        hdr['GUIDSTAT'] = (self.guider.guidestatus,'Status of the guiding loop')

        # telescope information (requires communication with TCS)
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
        
        # WCS solution
        #hdr['EPOCH'] = (2000,'Epoch of coordinates')
        #hdr['SECPIX'] = (self.platescale,'arcsec/pixel')
        #hdr['CTYPE1'] = ("RA---TAN","TAN projection")
        #hdr['CTYPE2'] = ("DEC--TAN","TAN projection")
        #hdr['CUNIT1'] = ("deg","X pixel scale units")
        #hdr['CUNIT2'] = ("deg","Y pixel scale units")
        #hdr['CRVAL1'] = (ra,"RA of reference point")
        #hdr['CRVAL2'] = (dec,"DEC of reference point")
        #hdr['CRPIX1'] = (self.x_science_fiber,"X reference pixel")
        #hdr['CRPIX2'] = (self.y_science_fiber,"Y reference pixel")
        #hdr['CD1_1'] = (-self.platescale*math.cos(skypa),"DL/DX")
        #hdr['CD1_2'] = (self.platescale*math.sin(skypa),"DL/DY")
        #hdr['CD2_1'] = (self.platescale*math.sin(skypa),"DM/DX")
        #hdr['CD2_2'] = (self.platescale*math.cos(skypa),"DM/DY")

        # target information (do we have this?)
        #hdr['TARGRA'] = (ra, "Target RA (J2000 deg)")
        #hdr['TARGDEC'] = (dec,"Target Dec (J2000 deg)")
        #hdr['PMRA'] = (pmra, "Target Proper Motion in RA (mas/yr)")
        #hdr['PMDEC'] = (pmdec, "Target Proper Motion in DEC (mas/yr)")
        #hdr['PARLAX'] = (parallax, "Target Parallax (mas)")
        #hdr['RV'] = (rv, "Target RV (km/s)")

        # weather keywords ??
        
        return hdr

    def test_guide_loop(self, exptime=0.1, simulate=False, save=False):
        self.guider.guiding=True

#        self.guide(exptime, simulate=False)
#        ipdb.set_trace()
        
        self.logger.info("Starting guide loop")
        kwargs = {'simulate':simulate, 'save':save}
        guide_thread = threading.Thread(target=self.guide, args=(exptime,),kwargs=kwargs)
        guide_thread.name = 'guide_thread'
        guide_thread.start()

        time.sleep(600)

        self.logger.info("Done guiding")
        self.guider.guiding=False

        guide_thread.join()

        
        
if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'tres.ini'
    tres = tres(base_directory, config_file, calstage_simulate=True, tiptilt_simulate=True,guider_simulate=True)
    
    tres.test_guide_loop(simulate=True, save=False, exptime=1.0)
    
    ipdb.set_trace()

    tres.guider.simulate_star_image([600,30,1500],[100,350,1700],[1000000,1e6,1e6],1.5, noise=10)
    stars = tres.guider.get_stars()
    hdr = tres.get_header()
    tres.guider.save_image('test_star.fits', hdr=hdr, overwrite=True)
    ipdb.set_trace()

    tres.take_image('test.fits', 0.1, overwrite=True)
    


