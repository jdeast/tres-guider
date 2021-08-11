from get_all_centroids import *
from astropy.io import fits
from pyAndorSDK3 import AndorSDK3
import numpy as np
import socket
import os, sys
import utils
from configobj import ConfigObj
import ipdb
import math
import logging
import datetime
from photutils import DAOStarFinder
from astropy.stats import sigma_clipped_stats
import redis
import json
import struct
import pyds9
import pdu
import centroid

class imager:

    def __init__(self, base_directory, config_file, logger=None, simulate=False):
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

#        self.redis = redis.Redis(host=config['REDIS_SERVER'],
#                                 port=config['REDIS_PORT'])            
            
        self.platescale = float(config['PLATESCALE'])
        self.gain = float(config['GAIN'])
        self.model = config['MODEL']
        self.sn = config['SN']
        self.datapath = config['DATAPATH']
        self.x_science_fiber = float(config['XSCIFIB'])
        self.y_science_fiber = float(config['YSCIFIB'])
        self.x_sky_fiber = None
        self.y_sky_fiber = None
        self.dateobs = ''
        self.exptime = 0.0
        self.guidestatus = None
        self.x1 = 1
        self.x2 = 2048
        self.y1 = 1
        self.y2 = 2048
        self.xbin = 1
        self.ybin = 1
        self.guiding = False
        self.simulate=simulate

#        self.redis.set('gain',self.gain)
#        self.redis.set('x_science_fiber',self.x_science_fiber)
#        self.redis.set('y_science_fiber',self.y_science_fiber)
#        self.redis.set('dateobs',self.dateobs)
#        self.redis.set('exptime',self.exptime)
#        self.redis.set('x1',self.x1)
#        self.redis.set('x2',self.x2)
#        self.redis.set('y1',self.y1)
#        self.redis.set('y2',self.y2)
#        self.redis.set('xbin',self.xbin)
#        self.redis.set('ybin',self.ybin)
#        self.redis.set('guiding',str(self.guiding))
        
        # servo parameters
        self.KPx = float(config['KPx'])
        self.KIx = float(config['KIx'])
        self.KDx = float(config['KDx'])
        self.KPy = float(config['KPy'])
        self.KIy = float(config['KIy'])
        self.KDy = float(config['KDy'])
        self.Imax = float(config['Imax'])
        self.Dband = float(config['Dband'])
        self.Corr_max = float(config['Corr_max'])

#        self.redis.set('KPx',self.KPx)
#        self.redis.set('KIx',self.KIx)
#        self.redis.set('KDx',self.KDx)
#        self.redis.set('KPy',self.KPy)
#        self.redis.set('KIy',self.KIy)
#        self.redis.set('KDy',self.KDy)        
#        self.redis.set('Imax',self.Imax)
#        self.redis.set('Dband',self.Dband)
#        self.redis.set('Corr_max',self.Corr_max)
        
        if not self.simulate:
            sdk3 = AndorSDK3()
            self.imager = sdk3.cameras[0].camera()

    ''' 
    this creates a simple simulated image of a star field
    the idea is to be able to test guide performance without being on sky
    x -- an array of X centroids of the stars (only integers tested!)
    y -- an array of Y centroids of the stars (only integers tested!)
    flux -- an array of fluxes of the stars (electrons)
    fwhm -- the fwhm of the stars (arcsec)
    background -- the sky background of the image
    noise -- readnoise of the image
    '''
    def simulate_star_image(self,x,y,flux,fwhm,background=300.0,noise=0.0):

        self.dateobs = datetime.datetime.utcnow()
#        self.redis.set('dateobs',self.dateobs.strftime('%Y-%m-%dT%H:%M:%S.%f'))
        

        xwidth = self.x2-self.x1
        ywidth = self.y2-self.y1
        self.image = np.zeros((ywidth,xwidth),dtype=np.float64) + background + np.random.normal(scale=noise,size=(ywidth,xwidth))
        
        # add a guide star?
        sigma = fwhm/self.platescale
        mu = 0.0
        
        boxsize = math.ceil(sigma*10.0)
        
        # make sure it's even to make the indices/centroids come out right
        if boxsize % 2 == 1: boxsize+=1 
        
        xgrid,ygrid = np.meshgrid(np.linspace(-boxsize,boxsize,2*boxsize+1), np.linspace(-boxsize,boxsize,2*boxsize+1))
        d = np.sqrt(xgrid*xgrid+ygrid*ygrid)
        g = np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) )
        g = g/np.sum(g) # normalize the gaussian
        
        # add each of the stars
        for ii in range(len(x)):

            xii = x[ii]-self.x1+1
            yii = y[ii]-self.y1+1
            
            # make sure the stamp fits on the image (if not, truncate the stamp)
            if xii >= boxsize:
                x1 = xii-boxsize
                x1stamp = 0
            else:
                x1 = 0
                x1stamp = boxsize-xii
            if xii <= (xwidth-boxsize):
                x2 = xii+boxsize+1
                x2stamp = 2*boxsize+1
            else:
                x2 = xwidth
                x2stamp = xwidth - xii + boxsize
            if yii >= boxsize:
                y1 = yii-boxsize
                y1stamp = 0
            else:
                y1 = 0
                y1stamp = boxsize-yii
            if yii <= (ywidth-boxsize):
                y2 = yii+boxsize+1
                y2stamp = 2*boxsize+1
            else:
                y2 = ywidth
                y2stamp = ywidth - yii + boxsize
            
            if (y2-y1) > 0 and (x2-x1) > 0:
                # normalize the star to desired flux
                star = g[y1stamp:y2stamp,x1stamp:x2stamp]*flux[ii]

                # add Poisson noise; convert to ADU
                noise = np.random.normal(size=(y2stamp-y1stamp,x2stamp-x1stamp))
                noisystar = (star + np.sqrt(star)*noise)/self.gain                

                # add the star to the image
                self.image[y1:y2,x1:x2] += noisystar
            else: self.logger.warning("star off image (" + str(xii) + "," + str(yii) + "); ignoring")
                
        # now convert to 16 bit int
        self.image = self.image.astype(np.int16)
        h, w = self.image.shape
        shape = struct.pack('>II',h,w)
        encoded_img = shape + self.image.tobytes()
#        self.redis.publish('guider_image',encoded_img)

    # this currently has ~0.5s of overhead
    def take_image(self, exptime):

        self.exptime = exptime
#        self.redis.set('exptime',self.exptime)
        
        self.imager.ExposureTime = self.exptime
        self.dateobs = datetime.datetime.utcnow()
#        self.redis.set('dateobs',self.dateobs.strftime('%Y-%m-%dT%H:%M:%S.%f'))
        
        t0 = datetime.datetime.utcnow()
        self.image = (self.imager.acquire(timeout=20000).image.astype(np.int16))[self.y1:self.y2,self.x1:self.x2]
        self.logger.info("image done in " + str((datetime.datetime.utcnow() - t0).total_seconds()))

    def save_image(self, filename, overwrite=False, hdr=None):

        self.logger.info("Saving " + filename)
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
        hdulist.writeto(filename, overwrite=overwrite)
        
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
#        self.redis.set('x1',self.x1)
#        self.redis.set('x2',self.x2)
#        self.redis.set('y1',self.y1)
#        self.redis.set('y2',self.y2)

    def get_stars(self):

        stars = centroid.get_stars_sep(self.image)
        stars[:,0] += (self.x1 - 1)
        stars[:,1] += (self.y1 - 1)
        return stars
        
        # this is too slow (~3s/image)!
        #mean, median, std = sigma_clipped_stats(self.image, sigma=3.0)
        #daofind = DAOStarFinder(fwhm=1.0/self.platescale, threshold=5.0*std)
        #sources = daofind(data - median)
        #stars = np.row_stack((sources['xcentroid'],sources['ycentroid'],sources['flux']))

        d = np.array(self.image, dtype='float')
        th = threshold_pyguide(d, level = 4)
        if np.max(th) == False: return [] # nothing above the threshhold
        imtofeed = np.array(np.round((d*th)/np.max(d*th)*255), dtype='uint8')
        stars = centroid_all_blobs(imtofeed)
        stars[:,0] += (self.x1 - 1)
        stars[:,1] += (self.y1 - 1)
        
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

    # turn on the star projector
    apc = pdu.pdu(base_directory, 'pdu.ini')
    if not apc.starprojector.status():
        apc.starprojector.on()
    
    ds9=pyds9.DS9()
    while True:
        camera.take_image(0.02)
        ds9.set_np2arr(camera.image)

        # extract the pinholes, get the distance between them
        if True:
            stars_sep = centroid.get_stars_sep(camera.image)
            sort_stars = stars_sep[(-stars_sep[:,2]).argsort()]
            # the brightest four are the pinholes                                                
            pinholes = sort_stars[0:4,:]
            for ii in range(len(pinholes[:,0])):
                for jj in range(len(pinholes[:,0])):
                    if ii > jj:
                        print(math.sqrt((pinholes[ii,0] - pinholes[jj,0])**2 + (pinholes[ii,1] - pinholes[jj,1])**2))


        
 
    camera.take_image(0.02)
    camera.save_image('star_projector_20210809.fits', overwrite=True)
    stars_sep = centroid.get_stars_sep(camera.image)
    sort_stars = stars_sep[(-stars_sep[:,2]).argsort()]
                               
    ipdb.set_trace()





