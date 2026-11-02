#!/usr/bin/python3
#from __future__ import division

import datetime
import numpy as np
import sep
import utils

################################################################################
class ImageProcessor():
    '''Manage image processing to compute guiding feedback'''
    def __init__(self,config,logger=None):
        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger('./log/','image_processor')
        else:
            self.logger = logger
            
#-------------------------------------------------------------------------------
    def populate_header(self,hdr):
        '''
        Populate FITS header passed in to set current Image processing state
        '''
        # WCS solution
        #hdr['EPOCH'] = (2000,'Epoch of coordinates')
        #hdr['SECPIX'] = (self.platescale,'arcsec/pixel')
        #hdr['CTYPE1'] = ("RA---TAN","TAN projection")
        #hdr['CTYPE2'] = ("DEC--TAN","TAN projection")
        #hdr['CUNIT1'] = ("deg","X pixel scale units")
        #hdr['CUNIT2'] = ("deg","Y pixel scale units")
        #hdr['CRVAL1'] = (ra,"RA of reference point")
        #hdr['CRVAL2'] = (dec,"DEC of reference point")
        #hdr['CRPIX1'] = (self.x_sci_fiber,"X reference pixel")
        #hdr['CRPIX2'] = (self.y_sci_fiber,"Y reference pixel")
        #hdr['CD1_1'] = (-self.platescale*math.cos(skypa),"DL/DX")
        #hdr['CD1_2'] = (self.platescale*math.sin(skypa),"DL/DY")
        #hdr['CD2_1'] = (self.platescale*math.sin(skypa),"DM/DX")
        #hdr['CD2_2'] = (self.platescale*math.cos(skypa),"DM/DY")
        pass

#-------------------------------------------------------------------------------
    def get_stars(self,image,threshold=5.0,linearize=False,minarea=100.0):
        #t0 = datetime.datetime.utcnow()
        image0 = image.astype('float32')
        
        bkg = sep.Background(image0, bw=64, bh=64, fw=3, fh=3)
        #bkg_rms = bkg.rms()

        data_sub = image0 - bkg
        try:
            stars = sep.extract(data_sub,threshold,err=bkg.globalrms,
                                minarea=minarea, deblend_nthresh=2)
        except:
            return []
        #tf = datetime.datetime.utcnow()
        #print((tf-t0).total_seconds())
        fwhm = 2.0 * (np.log(2.0) * (stars['a']**2.0 + stars['b']**2.0))**0.5

        xsep = stars['x']+1
        ysep = stars['y']+1
        if linearize:
            xcoeffs = [-4.85439689840629995388, 1.93559022660328050591, 1.61252683504826066496, -0.13589925878456243780,\
                       0.00868260421091360257, 0.00179647133793564562, -0.00674434017647176920, 0.00173227814504929578,\
                       -0.00008668280313570143, -0.00002886427988069585, 0.00002190978880285287, -0.00000590355638837149, 0.00000053915003532794]
            ycoeffs = [-0.78503066364238160979, 0.35500402642138922937, 1.42024333606683406117, -0.08977156521297151304,\
                       0.00646432412014710800, -0.00230635299460563289, -0.00614922732836410343, 0.00197234376101712615,\
                       0.00000410599917383841, -0.00001093749803809911, 0.00002241081702355307, -0.00000832687575098769, 0.00000005611923117332]
            x = utils.polyval_2d(xcoeffs,xsep,fwhm,6,1)
            y = utils.polyval_2d(ycoeffs,ysep,fwhm,6,1)
        else:
            x = xsep
            y = ysep

        # add one to X & Y for FITS convention
        return(np.transpose(np.vstack((x,
                                       y,
                                       stars['flux'],
                                       fwhm))))

################################################################################
