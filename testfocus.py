#import matplotlib.pyplot as plt
import numpy as np
import ipdb
import redis
import json
#from tres_guider import GuidingSystem

# some dummy values for testing
focus_results = [(2700,10.3),
                 (2800,5.2),
                 (2900,2.9),
                 (3000,2.1),
                 (3100,1.5),
                 (3200,2.2),
                 (3300,3.1),
                 (3400,5.3),
                 (3500,10.0)]

command_dict = {'focus_results':focus_results}
command_json_struct = json.dumps(command_dict)
r = redis.Redis(host='flwo60',port=6380)
r.publish('guider_state',command_json_struct)

ipdb.set_trace()

focpos = focus_results[:,0]
fwhm = focus_results[:,1]
plt.ion()
plt.figure()
plt.plot(focpos,fwhm,'ko')
plt.grid()
plt.xlabel("Focus postion (um)")
plt.ylabel("Star FWHM (arcsec)")

# fit a quadratic and overplot it as a red line
coeffs = np.polyfit(focpos, fwhm, 2)
pad = 100
prettyfocpos = np.linspace(np.min(focpos)-pad,np.max(focpos)+pad,num=30)
fitfwhm = np.polyval(coeffs,prettyfocpos)
plt.plot(prettyfocpos,fitfwhm,"-r")

# solve for the minimum of the quadratic (best focus)
bestfocus = int(round(-coeffs[1]/(2.0*coeffs[0])))
bestfwhm = coeffs[0]*bestfocus**2 + coeffs[1]*bestfocus + coeffs[2]

# put the best FWHM and focus in the title
plt.title("Best focus is " + '{0:.2f}'.format(bestfwhm) + '" at ' + str(bestfocus) + ' um')


ipdb.set_trace()
