from get_all_centroids import *
from astropy.io import fits
from pyAndorSDK3 import AndorSDK3
import numpy as np
import socket
import os, sys
import utils
from configobj import ConfigObj
import ipdb
import logging
import datetime

class imager:

    def __init__(self, base_directory, config_file, logger=None):
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file                                                                 
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'zyla')
        else: self.logger = logger

        # read the config file                                                                
        config = ConfigObj(self.config_file)

        # read the config file                                                                
        if os.path.exists(self.config_file):
            config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + self.config_file + ')')
            sys.exit()

        self.platescale = float(config['PLATESCALE'])
        self.gain = float(config['GAIN'])
        self.model = config['MODEL']
        self.sn = config['SN']
        self.datapath = config['DATAPATH']
        self.x_science_fiber = None
        self.y_science_fiber = None
        self.x_sky_fiber = None
        self.y_sky_fiber = None
        self.dateobs = None
        self.exptime = None
        self.guidestatus = None
        self.x1 = 1
        self.x2 = 2048
        self.y1 = 1
        self.y2 = 2048
        self.xbin = 1
        self.ybin = 1
        self.guiding = False
        
        sdk3 = AndorSDK3()
        self.imager = sdk3.cameras[0].camera()

    # this currently has ~0.5s of overhead
    def take_image(self, exptime):
        self.exptime = exptime
        self.imager.ExposureTime = self.exptime
        self.dateobs = datetime.datetime.utcnow()
        t0 = datetime.datetime.utcnow()
        self.image = (self.imager.acquire(timeout=20000).image.astype(np.int16))[self.y1:self.y2,self.x1:self.x2]
        self.logger.info("image done in " + str((datetime.datetime.utcnow() - t0).total_seconds()))

    def save_image(self, filename, overwrite=False, hdr=None):

        # make a minimal header if not supplied
        if hdr==None: hdr = fits.Header()

        # update a few things that might change
        hdr['DATE-OBS'] = (self.dateobs.strftime('%Y-%m-%dT%H:%M:%S.%f'),'YYYY-MM-DDThh:mm:ss.ssssss (UTC)')
        hdr['EXPTIME'] = (self.exptime,'Exposure time (s)')
        datasec = '[' + str(self.x1) + ':' + str(self.x2) + ',' + str(self.y1) + ':' + str(self.y2) + ']'
        hdr['DATASEC'] = (datasec,"Region of CCD read")
        hdr['CCDSUM'] = (str(self.xbin) + ' ' + str(self.ybin),'CCD on-chip summing')
        
        # save the image and header
        hdu = fits.PrimaryHDU(self.image, header=hdr)
        hdulist = fits.HDUList([hdu])
        hdulist.writeto(self.datapath + '/' + filename, overwrite=overwrite)
        
    ''' set the region of interest'''
    # right now, it appears this is not supported on chip in Python
    # this will read the whole image, but only save the ROI in self.image
    def set_roi(self,x1,x2,y1,y2):

        # boundary checking
        if x1 < 1 or x1 >= x2 or x2 > 2048 or y1 < 1 or y1 >= y2 or y2 > 2048:
            self.logger.error('Region of interest not allowed')
            return

        # set the ROI
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def get_stars(self):
        d = np.array(self.image, dtype='float')
        th = threshold_pyguide(d, level = 4)
        imtofeed = np.array(np.round((d*th)/np.max(d*th)*255), dtype='uint8')
        stars = centroid_all_blobs(imtofeed)
        return stars
        
    def calc_offsets(self):
        pass

if __name__ == '__main__':

    if socket.gethostname() == 'tres-guider':
        base_directory = '/home/tres/tres-guider'
    elif socket.gethostname() == 'Jason-THINK':
        base_directory = 'C:/tres-guider/'
    else:
        print('unsupported system')
        sys.exit()

    config_file = 'zyla.ini'
    camera = imager(base_directory, config_file)

    camera.take_image(0.2)
    camera.save_image('test3.fits', overwrite=True)

    ipdb.set_trace()





