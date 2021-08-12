from scipy.optimize import least_squares
from scipy.optimize import minimize
import numpy as np
import pyds9
import ipdb
import datetime
from astropy.io import fits as pyfits
from scipy.ndimage.filters import gaussian_filter

def model_annulus(pars, image, err, save=False):
    
    x_center = pars[0]
    y_center = pars[1]
    sigma = pars[2]
    background = pars[3]
    amplitude = pars[4]
    x_hole = pars[5]
    y_hole = pars[6]
    hole_size = pars[7]
    ylen,xlen = image.shape

    xmin = 1
    xmax = xlen

    ymin = 1
    ymax = ylen

    # boundary checking
    if hole_size  <  0.0: return [np.Infinity]
    if sigma      <= 0.0: return [np.Infinity]
    if amplitude  <= 0.0: return [np.Infinity]
    if background <  0.0: return [np.Infinity]

    if x_hole   < (xmin-hole_size) or x_hole   > (xmax+hole_size): return [np.Infinity]
    if y_hole   < (ymin-hole_size) or y_hole   > (ymax+hole_size): return [np.Infinity]
    if x_center < (xmin-3.0*sigma) or x_center > (xmax+3.0*sigma): return [np.Infinity] 
    if y_center < (ymin-3.0*sigma) or y_center > (ymax+3.0*sigma): return [np.Infinity]

    xgrid,ygrid = np.meshgrid(np.linspace(xmin-x_center, xmax-x_center, xlen), np.linspace(ymin-y_center, ymax-y_center, ylen))
    xgridhole,ygridhole = np.meshgrid(np.linspace(xmin-x_hole, xmax-x_hole, xlen), np.linspace(ymin-y_hole, ymax-y_hole, ylen))

    dhole = np.sqrt(xgridhole*xgridhole+ygridhole*ygridhole)
    hole = np.where(dhole < hole_size)


    hole_mask = np.zeros((ylen,xlen),dtype=np.float64) + 1.0

    hole_mask[hole[0],hole[1]] = 0.0
    hole_mask = gaussian_filter(hole_mask,sigma=1.0)


    mu = 0.0
    d = np.sqrt(xgrid*xgrid+ygrid*ygrid)
    g = hole_mask*amplitude*np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) ) + background
#    g = amplitude*np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) ) + background
#    g[hole[0],hole[1]] = background

    ds9=pyds9.DS9()
    ds9.set_np2arr(g)
#    ds9.set_np2arr(image)

#    ipdb.set_trace()

    save = True
    if save: 
        hdu = pyfits.PrimaryHDU(g)
        hdu.writeto('model.fits',overwrite=True)

        hdu = pyfits.PrimaryHDU(image-g)
        hdu.writeto('diff.fits',overwrite=True)

        hdu = pyfits.PrimaryHDU(image)
        hdu.writeto('image.fits',overwrite=True)

    print(np.sum(((image - g)/err)**2), x_center, y_center, sigma, background, amplitude, x_hole, y_hole, hole_size) 
#    ipdb.set_trace()

#    return [np.sum(((image - g)/err)**2)]

    return ((image - g)/err).flatten()


def fit_annulus(image, pars=None, scale=None):

    if pars==None:
        x_center = 0.1
        y_center = 0.3
        sigma = 7.0
        background = np.median(image)
        amplitude = np.amax(image)-background
        x_hole = x_center
        y_hole = y_center
        hole_size = 7.0
        pars = [x_center,y_center,sigma,background,amplitude,x_hole,y_hole,hole_size]

    err = np.sqrt(image)

#    result = least_squares(model_annulus, pars, args=([image,err]), x_scale=scale)
    result = least_squares(model_annulus, pars, args=(image,err), x_scale=scale, method='lm')
#    result = minimize(model_annulus, pars, method='Nelder-Mead', args=(image,err))
    return result
    
    
if __name__ == '__main__':
    
    filename = '../data/test.210811.guider.1001.fits'
    image = pyfits.getdata(filename)

    x1 = 290
    x2 = 331
    y1 = 294
    y2 = 336
    stamp = image[y1:y2+1,x1:x2+1]

    ds9=pyds9.DS9()
    ds9.set_np2arr(stamp)
        
    t0 = datetime.datetime.utcnow()
    #pars = [x_center,y_center,sigma,background, amplitude,x_hole,y_hole,hole_size]
    pars  = [    28.3,    20.1,  7.4,     105.5,     500.7, 25.01, 20.63,      9.8]
    scale = [    10.0,    10.0,  3.0,      10.0,    5000.0, 10.00, 10.00,      5.0]
#    scale = [    1e-9,    1e-9,  3.0,      1e-9,      1e-9,  1e-9,  1e-9,      5.0]

    result = fit_annulus(stamp, pars=pars, scale=scale)


    print((datetime.datetime.utcnow()-t0).total_seconds())


    junk = model_annulus(result.x, stamp, np.sqrt(stamp), save=True)

    ipdb.set_trace()

    boxsize = 99
    mu = 0.0
    amplitude = 10.0
    sigma = 15.0
    background = 100.0
    hole_size = 7.0
    
    xgrid,ygrid = np.meshgrid(np.linspace(-boxsize,boxsize,2*boxsize+1), np.linspace(-boxsize,boxsize,2*boxsize+1))
    d = np.sqrt(xgrid*xgrid+ygrid*ygrid)
    image = amplitude*np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) ) + background

    hole = np.where(d < hole_size)
    image[hole[0],hole[1]] = background


    

    

    
