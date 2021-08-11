import utils
import ipdb
import centroid
import numpy as np
import math
from scipy.optimize import least_squares

def compute_residuals(pars, positions, xstars, ystars, flip):

    x_offset = pars[0] 
    y_offset = pars[1]
    x_scale = pars[2]
    y_scale = pars[3]
    theta = pars[4]
    
    residuals = []
    for i in range(len(positions)):
        if flip: residuals.append(x_offset - (math.cos(theta)*positions[i][0] - math.sin(theta)*positions[i][1])/x_scale-xstars[i])
        else: residuals.append(x_offset + (math.cos(theta)*positions[i][0] - math.sin(theta)*positions[i][1])/x_scale-xstars[i])
        residuals.append(y_offset + (math.sin(theta)*positions[i][0] + math.cos(theta)*positions[i][1])/y_scale-ystars[i])

    return residuals

retake = False

if retake:
    from guider import imager
    from tiptilt import tiptilt
    import pyds9

    base_directory = '/home/tres/tres-guider/'
    logger = utils.setup_logger(base_directory + '/log/', 'calibration')
    guider = imager(base_directory, 'zyla.ini', logger=logger, simulate=False)
    tiptilt = tiptilt(base_directory, 'tiptilt.ini', logger=logger, simulate=False)
    tiptilt.connect()
    ds9 = pyds9.DS9()

positions = [[1.0,1.0],
             [0.0,0.0],
             [0.0,2.0],
             [2.0,2.0],
             [2.0,0.0],
             [0.0,0.0],
             [1.0,1.0]]

xstars = []
ystars = []
# take an image
for i in range(len(positions)):
    
    filename = '/home/tres/data/testdata/tiptilt_cal_20210810_' + str(i+1).zfill(4) + '_' + str(positions[i][0]) + '_' + str(positions[i][1]) + '.fits'

    if retake:
        tiptilt.move_tip_tilt(positions[i][0],positions[i][1])
        guider.take_image(0.02)
        guider.save_image(filename,overwrite=True)

    stars = centroid.get_stars_sep(None,filename=filename)

    if retake:
        # display the image and the stars it found
        ds9.set_np2arr(guider.image)
        for star in stars:
            ds9.set('regions','circle(' + str(star[0]) + ',' + str(star[1]) + ',7)')

#    targetx = 1906
#    targety = 925
    targetx = 947
    targety = 960

    good = np.where(stars[:,2] > 5e4)
    stars = stars[good[0],:]
    dx = stars[:,0] - targetx
    dy = stars[:,1] - targety
    dist = np.sqrt(dx*dx + dy*dy)
    
    ndx = np.argmin(dist)
    print(filename, stars[ndx,0], stars[ndx,1])
    
    xstars.append(stars[ndx,0])
    ystars.append(stars[ndx,1])

x_offset = 1843.2
y_offset = 881.15
scale = 1.0/50.0
theta = math.pi/2.0
flip = True
pars = [x_offset,y_offset,scale,scale,theta]

# solve for x_offset, y_offset, x_scale, y_scale, and theta
result = least_squares(compute_residuals, pars, args=(positions,xstars,ystars,flip))

x_offset = result.x[0] # nuisance parameter
y_offset = result.x[1] # nuisance parameter
x_scale = result.x[2]
y_scale = result.x[3]
theta = result.x[4]

# sanity check -- compare modeled positions with actual positions
for i in range(len(positions)):
    if flip: print(x_offset - (math.cos(theta)*positions[i][0] - math.sin(theta)*positions[i][1])/x_scale ,xstars[i])
    else: print(x_offset + (math.cos(theta)*positions[i][0] - math.sin(theta)*positions[i][1])/x_scale ,xstars[i])
    print(y_offset + (math.sin(theta)*positions[i][0] + math.cos(theta)*positions[i][1])/y_scale ,ystars[i])

# these are the values that go in config/tiptilt.ini
print("STEPS_PER_PIXEL_TIP", x_scale)
print("STEPS_PER_PIXEL_TILT", y_scale)
print("THETA", theta*180.0/math.pi)
print("FLIP", flip)
    
ipdb.set_trace()

