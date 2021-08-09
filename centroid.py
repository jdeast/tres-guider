import cv2
import numpy as np
from photutils import DAOStarFinder
from astropy.stats import sigma_clipped_stats
from astropy.io import fits as pyfits
import sep
import datetime, os
import utils
import ipdb

# this contains several different (swappable) algorithms to identify stars and return their x, y, intensity, and fwhm
# they have different advantages for speed and accuracy

# fast but not very accurate
def get_stars_cv(image, filename=None):
    if filename != None:
        image = pyfits.getdata(filename)

    d = np.array(image, dtype='float')
    th = threshold_pyguide(d, level = 4)

    # all zero image
    if np.max(image*th) == 0.0:
        return []

    imtofeed = np.array(np.round((d*th)/np.max(d*th)*255), dtype='uint8')
    return centroid_all_blobs(imtofeed)

# helper function for get_stars_cv
def centroid_all_blobs(thresholded_image, areacutoff=30):
    thresholded_copy = thresholded_image.copy()
    contours,hierarchy = cv2.findContours(thresholded_copy,
                                        cv2.RETR_LIST,
                                        cv2.CHAIN_APPROX_SIMPLE)
    if len(contours)==0:
        return np.zeros((1, 3))

    else:
        outarray = np.zeros((1, 3))
        counter = 0
        for cnt in contours:
            M = cv2.moments(cnt)
            if M['m00']<areacutoff:
                counter = counter+1
                continue
            cx,cy,ssum = (M['m10']/M['m00']), (M['m01']/M['m00']), M['m00']
            outarray=np.vstack((outarray, np.array((cx, cy, ssum))))
    return outarray[1:,:]

# helper function for get_stars_cv
def threshold_pyguide(image,level =3):
    stddev = robust_std(image)
    median = np.median(image)
    goodpix = image>median+stddev*level
    return goodpix

# helper function for get_stars_cv
def robust_std(x):
    y = x.flatten()
    n = len(y)
    y.sort()
    ind_qt1 = int(round((n+1)/4.))
    ind_qt3 = int(round((n+1)*3/4.))
    IQR = y[ind_qt3]- y[ind_qt1]
    lowFense = y[ind_qt1] - 1.5*IQR
    highFense = y[ind_qt3] + 1.5*IQR
    ok = (y>lowFense)*(y<highFense)
    yy=y[ok]
    return yy.std(dtype='double')

# finds the integer pixel value for the brightest star in the image
# only useful if we know we want to target the brightest star in the image
def get_stars_brightest(image, filename=None):

    if filename != None:
        image = pyfits.getdata(filename)

    xc0 = np.where(np.amax(np.sum(image,axis=0)) ==  np.sum(image,axis=0))
    yc0 = np.where(np.amax(np.sum(image,axis=1)) ==  np.sum(image,axis=1))
    xc = xc0[0][0]+1
    yc = yc0[0][0]+1

    # make sure we have a detection
    boxsize = 50
    xmin = xc - boxsize
    xmax = xc + boxsize
    ymin = yc - boxsize
    ymax = yc + boxsize
    mean, median, std = sigma_clipped_stats(image[xmin:xmax,ymin:ymax], sigma = 3.0)
    try:
        if np.max(image[xmin:xmax,ymin:ymax]) > 10.0*std:
            return np.transpose(np.vstack((xc, yc, 1)))
            #return [[xc],[yc],[1]]
    except:
        return []
    return []

# use source extractor
# only works on linux, must write a file fits file if image array given, 
# must have source extractor installed and in the path
# probably want to use get_stars_sep instead
# (sep wraps the core C source extractor functions in python)
def get_stars_sex(image, filename=None):

    # source extractor can only run on a fits file
    # write a fits file if an image array is given
    if filename == None:
        filename0 = 'temp.fits'
        cleanup = True
    else: filename0 = filename

    # write the fits image
    if not os.path.isfile(filename0):
        hdu = pyfits.PrimaryHDU(image)
        hdu.writeto(filename0)
    
    catname = utils.sextract('',filename0,\
                             sexfile='/usr/share/sextractor/tres.sex',\
                             paramfile='/usr/share/sextractor/tres.param')
    cat = utils.readsexcat(catname)

    if cleanup: os.remove(filename0)

    return np.transpose(np.vstack((cat['XWIN_IMAGE'],cat['YWIN_IMAGE'],cat['FLUX_ISO'])))

# sep wraps the core C source extractor functions in python
# assuming we can use it correctly,
# this is going to be faster, more general, and just as good as get_stars_sex
def get_stars_sep(image, filename=None):
    if filename != None:
        image = pyfits.getdata(filename)

    image0 = image.astype('float64')
        
    bkg = sep.Background(image0, bw=64, bh=64, fw=3, fh=3)
#    bkg_rms = bkg.rms()
    data_sub = image0 - bkg
    stars = sep.extract(data_sub, 1.5, err=bkg.globalrms)
    return np.transpose(np.vstack((stars['x'],stars['y'],stars['flux'])))

# use dao to identify stars
def get_stars_dao(image, filename=None):

    if filename != None:
        image = pyfits.getdata(filename)

    mean, median, std = sigma_clipped_stats(image, sigma = 3.0)
    daofind = DAOStarFinder(fwhm=4.0, threshold=10.0*std, ratio=0.3)
    sources = daofind(image - median)
    if len(sources) == 0: return []

    stars = np.vstack((sources['xcentroid'], sources['ycentroid'], sources['flux'])).T
    return stars

# use get_stars_brightest to locate the brightest star,
# then refine position using get_stars_dao on an ROI around that
def get_brightest_dao(image,filename=None):

    if filename != None:
        image = pyfits.getdata(filename)

    stars = get_stars_brightest(image)
    if len(stars) < 1: return []

    xc = stars[0,0]
    yc = stars[0,1]

    boxsize = 50
    xmin = xc - boxsize
    xmax = xc + boxsize
    ymin = yc - boxsize
    ymax = yc + boxsize

    sources = get_stars_dao(image[ymin:ymax,xmin:xmax])

    stars = np.vstack((sources[:,0]+xmin, sources[:,1]+ymin, sources[:,2])).T

    return stars
    
