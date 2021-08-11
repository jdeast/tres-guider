from scipy.optimize import least_squares
import numpy as np
import pyds9
import ipdb
import datetime

def model_annulus(pars, image):
    
    x_center = pars[0]
    y_center = pars[1]
    sigma = pars[2]
    amplitude = pars[3]
    background = pars[4]
    x_hole = pars[5]
    y_hole = pars[6]
    hole_size = pars[7]
    boxsize = np.floor(len(image[0,:])/2).astype(int)

    xgrid,ygrid = np.meshgrid(np.linspace(-boxsize,boxsize,2*boxsize+1), np.linspace(-boxsize,boxsize,2*boxsize+1))
    mu = 0.0
    d = np.sqrt(xgrid*xgrid+ygrid*ygrid)

    hole = np.where(d < hole_size)
    g = amplitude*np.exp(-( (d-mu)**2 / ( 2.0 * sigma**2 ) ) ) + background
    g[hole[0],hole[1]] = background

    return (image - g).flatten()


def fit_annulus(image):


    x_center = len(image[0,:])/2.0
    y_center = len(image[:,0])/2.0
    sigma = len(image[:,0])/5.0
    amplitude = np.amax(image)
    background = np.median(image)
    x_hole = x_center
    y_hole = y_center
    hole_size = 7.0

    pars = [x_center,y_center,sigma,amplitude,background,x_hole,y_hole,hole_size]
    result = least_squares(model_annulus, pars, args=([image]))
    return result
    
    
if __name__ == '__main__':

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

    
    ds9=pyds9.DS9()
    ds9.set_np2arr(image)
        

    t0 = datetime.datetime.utcnow()
    result = fit_annulus(image)
    print((datetime.datetime.utcnow()-t0).total_seconds())

    ipdb.set_trace()

    
