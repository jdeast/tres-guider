#!/usr/bin/python3
import sys
import os
import socket
import utils
from configobj import ConfigObj
import asyncio
import aioredis
import async_timeout
from collections import deque
import datetime
import struct
import redis
import json
import atexit
import base64
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import dates
import parse
from astropy.io import fits
import pyds9

import logging

from qasync import QEventLoop, QtGui, QtCore, QtWidgets

from tres_guider_control_ui import Ui_Dialog

################################################################################
class EventSender():
    '''Send guider events to Redis for GUI usage'''
    
    def __init__(self,config):
        self.server_host = config['REDIS_SERVER']
        self.server_port = config['REDIS_PORT']
        self.redis = redis.Redis(host=self.server_host,
                                 port=self.server_port)
        self.command_counter = 0

    def send(self,command_dict):
        '''
        Pass in a dict of key value pairs to set in underlying code
        '''
        command_json_struct = json.dumps(command_dict)
        res = self.redis.publish('guider_commands',command_json_struct)
        self.command_counter += 1
        print("Sent command %i" % (self.command_counter,))
        return(res)


################################################################################
class TresGUI(QtWidgets.QWidget):
    def __init__(self, base_directory,config_file,event_loop,
                 logger=None,parent = None):
        '''
        Constructor
        '''
        super(TresGUI,self).__init__()
        
        self.base_directory=base_directory
        self.config_file = self.base_directory + '/config/' + config_file

        # set up the log file
        if logger == None:
            self.logger = utils.setup_logger(base_directory + '/log/', 'tres')
        else: self.logger = logger


        # read the config file
        if os.path.exists(self.config_file):
            self.config = ConfigObj(self.config_file)
        else:
            self.logger.error('Config file not found: (' + \
                              self.config_file + ')')
            sys.exit()        
        
        QtWidgets.QWidget.__init__(self,parent)
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)

#        self.ui.loopButton.setOutbg('binoRed')
#        self.ui.loopButton.setInbg('binoGreen')
#        self.ui.loopButton.setOuttext('Open')
#        self.ui.loopButton.setIntext('Closed')
#        self.ui.loopButton.on_toggled(False)

        self.dequelen  = 30
        self.axrect = [0.15, 0.15, 0.75, 0.7]
        
        self.gdr_focus_axis_lim = 0.25
        self.gdr_focus_data  = {'timestamp'  : deque([], self.dequelen), 
                          'fwhm' : deque([], self.dequelen)}
        self.gdr_focus_fig   = self.ui.focusMplwidget.figure   
        self.plot_focus_cnt  = -1     
#        self.replotf()

        self.gdr_counts_axis_lim = 0.25
        self.gdr_counts_data  = {'timestamp'  : deque([], self.dequelen), 
                          'counts' : deque([], self.dequelen)}
        self.gdr_counts_fig   = self.ui.bcountsMplwidget.figure   
        self.plot_counts_cnt  = -1     

        self.gdr_tilt_axis_lim = 0.25
        self.gdr_tilt_data_x = {'timestamp' : deque([], self.dequelen), 
                                'dx' : deque([], self.dequelen)}
        self.gdr_tilt_data_y = {'timestamp' : deque([], self.dequelen), 
                                'dy' : deque([], self.dequelen)}
        self.gdr_fsm_data_x = {'timestamp' : deque([], self.dequelen), 
                                'dx' : deque([], self.dequelen)}
        self.gdr_fsm_data_y = {'timestamp' : deque([], self.dequelen), 
                               'dy' : deque([], self.dequelen)}
        
        self.gdr_tilt_fig = self.ui.azelMplwidget.figure        
        #         self.replott()

        self.plot_tilt_cnt = -1

        self.subplot_axrect = [0.0, 0.1, 1.0, 0.85]
        self.gdr_bullseye_fig = self.ui.bullseyeMplwidget.figure                
        self.plot_bullseye_cnt = -1
        
        self.gdr_profile_fig = self.ui.profileMplwidget.figure                
        self.plot_profile_cnt = -1

        self.loop_state = 'open'
        self.guiding_mode = 'full_frame'
        self.exposure_time = 0
        self.cadence = 0
        self.sensor_temp = 0.0
        self.sensor_temp_status = ""
        self.frame_counter = 0
        self.ds9_inspect_ff = True
        self.ds9_inspect_sci = True
        self.ds9_inspect_sky = True
        self.ds9_inspect_star = True
        self.ds9_live_updates = True
        
        self.guider_xdim = 2048  # Defaults for Zyla 4.2 sCMOS camera
        self.guider_ydim = 2048        
        self.roi_x1 = 996
        self.roi_x2 = 1052
        self.roi_y1 = 996
        self.roi_y2 = 1052
        self.roi_xdim = self.roi_x2 - self.roi_x1
        self.roi_ydim = self.roi_y2 - self.roi_y1
        self.guiding_offset_x = 0.0
        self.guiding_offset_y = 0.0
        self.fsm_angle_x = 0.0
        self.fsm_angle_y = 0.0

        self.star_roi_xcenter_pix = 1024
        self.star_roi_ycenter_pix = 1024
        
        self.region_xcen = self.roi_xdim/2
        self.region_ycen = self.roi_ydim/2
        self.region_radius = 20
        self.plate_solve_success = False
        self.plate_solve_running = False
        self.wcs_hdr_dict = {}

        self.event_tree = {'loop_state':self.on_loop_changed,
                           'framing':self.on_framing_changed,
                           'exposure_time':self.on_exposure_time_changed,
                           'cadence':self.on_cadence_changed,
                           'loop_gains':self.on_gains_changed,
                           'plate_solve_event':self.on_plate_solve_event}
        
        self.receive_task = asyncio.ensure_future(
            self.receive_telem(self.on_guider_data,
                               self.config['REDIS_SERVER'],
                               self.config['REDIS_PORT'],
                               'guider_data'))

        self.receive_event_task = asyncio.ensure_future(
            self.receive_events(self.on_events,
                               self.config['REDIS_SERVER'],
                               self.config['REDIS_PORT'],
                               'guider_state'))
        
        self.command_sender = EventSender(self.config)
        self.exit_request = asyncio.Event()
        
        print("Done with TresGUI init")

#-------------------------------------------------------------------------------
    @staticmethod
    async def telem_reader(channel: aioredis.client.PubSub, callback):
        print("In telem_reader")
        receive_counter = 0
        while True:
            try:
                async with async_timeout.timeout(10):
                    msg = await channel.get_message(ignore_subscribe_messages=True)
                    if msg is not None:
                        callback(json.loads(msg["data"]))
                        del msg
                        receive_counter += 1
                    await asyncio.sleep(0.01)
            except asyncio.TimeoutError:
                pass

        
#-------------------------------------------------------------------------------
    async def receive_telem(self,callback,server,port,data_name):
        conn_str = 'redis://'+server  # +':'+port
        print("Connecting to redis for telem:",conn_str)
        self.telem_redis_sub = aioredis.from_url(conn_str,decode_responses=True)
        print("Created connection")
        self.telem_pubsub = self.telem_redis_sub.pubsub()
        res = await self.telem_pubsub.subscribe(data_name)
        print("Subscribed to " + data_name)
        asyncio.create_task(self.telem_reader(self.telem_pubsub,callback))

#-------------------------------------------------------------------------------
    @staticmethod
    async def event_reader(channel: aioredis.client.PubSub, callback):
        print("In event_reader")
        receive_counter = 0
        while True:
            try:
                async with async_timeout.timeout(10):
                    msg = await channel.get_message(ignore_subscribe_messages=True)
                    if msg is not None:
                        callback(json.loads(msg["data"]))
                        del msg
                        receive_counter += 1
                    await asyncio.sleep(0.01)
            except asyncio.TimeoutError:
                pass

        
#-------------------------------------------------------------------------------
    async def receive_events(self,callback,server,port,data_name):
        conn_str = 'redis://'+server  # +':'+port
        print("Connecting to redis for events:",conn_str)
        self.event_redis_sub = aioredis.from_url(conn_str,decode_responses=True)
        print("Created connection")
        self.event_pubsub = self.event_redis_sub.pubsub()
        res = await self.event_pubsub.subscribe(data_name)
        print("Subscribed to " + data_name)
        asyncio.create_task(self.event_reader(self.event_pubsub,callback))
        
#-------------------------------------------------------------------------------
    def closeEvent(self,*args):
        print("Exiting")
        self.exit_request.set()
            
#-------------------------------------------------------------------------------
    def replot_counts(self):
        # bucket counts plot
#        print('entering replot_counts')
        
        self.plot_counts_cnt += 1
        initplots = False        
        if self.plot_counts_cnt % 10 == 0:
            initplots = True
            
        if initplots:
            self.gdr_counts_fig.clear()
            self.gdrbax = self.gdr_counts_fig.add_axes(self.axrect)
        else:
            self.gdrbax.clear()

#         self.gdr_counts_fig.clear()
#         self.gdrbax = self.gdr_counts_fig.add_axes(self.axrect)
        self.gdrbax.set_title('Bucket counts')
        hfmt = dates.DateFormatter('%H:%M:%S')
        if len(self.gdr_counts_data['timestamp']) > 0:
            self.gdrbax.xaxis.set_major_locator(dates.MinuteLocator())
            self.gdrbax.xaxis.set_major_formatter(hfmt)
        ylim = self.gdr_counts_axis_lim
        tmp = list(self.gdr_counts_data['counts'])
        if len(tmp) >= 1:
            maxx = abs(max(tmp))
            minx = abs(min(tmp))
            if minx > maxx:
                maxx = minx
            if maxx > ylim:
                ylim = maxx
        self.gdrbax.set_ylim([0, ylim * 1.1])
        self.gdrbax.grid(True)
        self.gdrbax.plot(self.gdr_counts_data['timestamp'], self.gdr_counts_data['counts'], '-go')
#         self.gdrbax.axhline(1.5, 0, 1, color = 'g')
#         self.gdrbax.axhline(3.0, 0, 1, color = 'y')
#         self.gdrbax.axhline(-1.5, 0, 1, color = 'g')
#         self.gdrbax.axhline(-3.0, 0, 1, color = 'y')
        self.ui.bcountsMplwidget.draw()
#        print('leaving replot_counts')

#-------------------------------------------------------------------------------
    def replot_focus(self):
        # focus plot
        self.plot_focus_cnt += 1
        initplots = False        
        if self.plot_focus_cnt % 10 == 0:
            initplots = True
            
        if initplots:
            self.gdr_focus_fig.clear()
            self.gdrfax = self.gdr_focus_fig.add_axes(self.axrect)  # aspect ratio
        else:
            self.gdrfax.clear()

#         self.gdr_focus_fig.clear()
#         self.gdrfax = self.gdr_focus_fig.add_axes(self.axrect)
        self.gdrfax.set_title('Average FWHM ["]')
        hfmt = dates.DateFormatter('%H:%M:%S')
        if len(self.gdr_focus_data['timestamp']) > 0:
            self.gdrfax.xaxis.set_major_locator(dates.MinuteLocator())
            self.gdrfax.xaxis.set_major_formatter(hfmt)
        ylim = self.gdr_focus_axis_lim
        tmp = list(self.gdr_focus_data['fwhm'])
        if len(tmp) >= 1:
            maxx = abs(max(tmp))
            minx = abs(min(tmp))
            if minx > maxx:
                maxx = minx
            if maxx > ylim:
                ylim = maxx
        self.gdrfax.set_ylim([0.0, ylim * 1.1])
        self.gdrfax.grid(True)
        self.gdrfax.plot(self.gdr_focus_data['timestamp'], self.gdr_focus_data['fwhm'], '-go')
#         self.gdrfax.legend(['Box x', 'Box y', 'Star x', 'Star y'])
#         self.gdrfax.axhline(1.5, 0, 1, color = 'g')
#         self.gdrfax.axhline(3.0, 0, 1, color = 'y')
#         self.gdrfax.axhline(-1.5, 0, 1, color = 'g')
#         self.gdrfax.axhline(-3.0, 0, 1, color = 'y')
        self.ui.focusMplwidget.draw()
            
#-------------------------------------------------------------------------------
    def replot_tilts(self):
#        print('entering replot_tilts')
        
        self.plot_tilt_cnt += 1
        initplots = False        
        if self.plot_tilt_cnt % 10 == 0:
            initplots = True
            
        if initplots:
            self.gdr_tilt_fig.clear()
            self.gdrtax = self.gdr_tilt_fig.add_axes(self.axrect)  # aspect ratio
        else:
            self.gdrtax.clear()
       
        self.gdrtax.set_title('Pointing error [Instrument "]')
        hfmt = dates.DateFormatter('%H:%M:%S')
        if len(self.gdr_tilt_data_x['timestamp']) > 0:
            self.gdrtax.xaxis.set_major_locator(dates.MinuteLocator())
            self.gdrtax.xaxis.set_major_formatter(hfmt)
        ylim = self.gdr_tilt_axis_lim
        tmp = list(self.gdr_tilt_data_x['dx']) + list(self.gdr_tilt_data_y['dy']) + list(self.gdr_fsm_data_x['dx']) + list(self.gdr_fsm_data_y['dy'])
        if len(tmp) >= 1:
            maxx = abs(max(tmp))
            minx = abs(min(tmp))
            if minx > maxx:
                maxx = minx
            if maxx > ylim:
                ylim = maxx
        self.gdrtax.set_ylim([-ylim * 1.1, ylim * 1.1])
        self.gdrtax.grid(True)
        self.gdrtax.plot(self.gdr_tilt_data_x['timestamp'], self.gdr_tilt_data_x['dx'], '-go')
        self.gdrtax.plot(self.gdr_tilt_data_y['timestamp'], self.gdr_tilt_data_y['dy'], '-ro')
        self.gdrtax.plot(self.gdr_fsm_data_x['timestamp'], self.gdr_fsm_data_x['dx'], '-co')
        self.gdrtax.plot(self.gdr_fsm_data_y['timestamp'], self.gdr_fsm_data_y['dy'], '-mo')
        self.gdrtax.legend(['cen_x','cen_y','fsm_x', 'fsm_y'],
                           loc='upper left',framealpha=0.4)
        
#         self.gdrtax.axhline(1.5, 0, 1, color = 'g')
#         self.gdrtax.axhline(3.0, 0, 1, color = 'y')
#         self.gdrtax.axhline(-1.5, 0, 1, color = 'g')
#         self.gdrtax.axhline(-3.0, 0, 1, color = 'y')
        self.ui.azelMplwidget.draw()
#        print('leaving replot_tilts')

#-------------------------------------------------------------------------------
    def replot_bullseye(self):
#        print('entering replot_bullseye')
        
        self.plot_bullseye_cnt += 1
#        initplots = False        
#        if self.plot_bullseye_cnt % 10 == 0:
#            initplots = True
            
#        if initplots:
        self.gdr_bullseye_fig.clear()
        self.gdrbeax = self.gdr_bullseye_fig.add_axes(self.subplot_axrect)  # aspect ratio
#        else:
#            self.gdrbax.clear()
        fov=5.0

        ages = np.array(self.gdr_tilt_data_x['timestamp'])
        ages = (ages-ages[0])*2/2.31539234e-5
        oldest_point_age = max(ages)
        if oldest_point_age == 0:
            alphas = 1.
        else:
            alphas = np.flip(1. - (ages/oldest_point_age)*0.95)
        self.gdrbeax.set_xlim([-fov/2,fov/2])
        self.gdrbeax.set_ylim([-fov/2,fov/2])
        self.gdrbeax.grid(True)
#        self.gdrbeax.add_patch(plt.Circle((0,0),5.0,alpha=0.1,color="grey",
#                                          fill=False))
        self.gdrbeax.add_patch(plt.Circle((0,0),2.0,alpha=0.2,color="grey"
                                          ,fill=False))
        self.gdrbeax.add_patch(plt.Circle((0,0),1.0,alpha=0.4,color="grey",
                                          fill=False))
        self.gdrbeax.add_patch(plt.Circle((0,0),0.5,alpha=0.7,color="grey",
                                          fill=False))
        self.gdrbeax.scatter(self.gdr_tilt_data_x['dx'],
                             self.gdr_tilt_data_y['dy'],
                             s=30,color="black",
                             alpha=alphas,marker='+')
        self.gdrbeax.axline((-5,0),(5,0),alpha=0.5,color="aqua")
        self.gdrbeax.axline((0,-5),(0,5),alpha=0.5,color="aqua")
#        self.gdrbeax.set_xlabel('RA Error "')
#        self.gdrbeax.set_ylabel('DEC Error "')
        self.gdrbeax.set_aspect('equal')
        self.ui.bullseyeMplwidget.draw()
#        print('leaving replot_bullseye')


#-------------------------------------------------------------------------------
    def replot_profile(self):
#        print('entering replot_profile')
        
        self.plot_profile_cnt += 1

        fov = 10.0  # arcseconds
        num_pixels = int(np.round(fov/2/self.platescale))*2  # Make even
        self.gdr_profile_fig.clear()
        self.gdrpax = self.gdr_profile_fig.add_axes(self.axrect)  # aspect ratio

        star_center_pix_x = int(np.round(self.region_xcen))
        star_center_pix_y = int(np.round(self.region_ycen))
        angular_offsets = np.linspace(-1*fov/2,fov/2,num=num_pixels)
        yslice = self.image[star_center_pix_y-int(num_pixels/2):star_center_pix_y+int(num_pixels/2),star_center_pix_x]
        xslice = self.image[star_center_pix_y,star_center_pix_x-int(num_pixels/2):star_center_pix_x+int(num_pixels/2)]
        
        self.gdrpax.set_xlim([-1*fov/2,fov/2])
        self.gdrpax.grid(True)
        self.gdrpax.plot(angular_offsets,xslice)
        self.gdrpax.plot(angular_offsets,yslice)

        self.ui.profileMplwidget.draw()
#        print('leaving replot_profile')

#------------------------------------------------------------------------------
    def update_gui(self):
#        print("Received guider data");
        self.ui.exptime1Edit.setText(str(round(float(self.exposure_time),6)))
        self.ui.cadenceEdit.setText(str(round(float(self.cadence),6)))        
        self.ui.sensorTempEdit.setText(str(round(float(self.sensor_temp),2)))
        if self.sensor_temp_status == "Stabilised":
            self.ui.sensorTempEdit.setStyleSheet("color: green;")
        else:
            self.ui.sensorTempEdit.setStyleSheet("color: red;")


        self.ra_jitter =  np.std(self.gdr_tilt_data_x['dx'])
        self.dec_jitter =  np.std(self.gdr_tilt_data_y['dy'])
        self.ui.raJitterEdit.setText(str(round(self.ra_jitter,2))+'"')
        self.ui.decJitterEdit.setText(str(round(self.dec_jitter,2))+'"')
        if self.ra_jitter > 0.5 or self.dec_jitter > 0.5:
            self.ui.raJitterEdit.setStyleSheet("color: red;")
            self.ui.decJitterEdit.setStyleSheet("color: red;")
        elif self.ra_jitter > 1.0 or self.dec_jitter > 1.0:
            self.ui.raJitterEdit.setStyleSheet("color: orange;")
            self.ui.decJitterEdit.setStyleSheet("color: orange;")
        elif self.ra_jitter > 2.0 or self.dec_jitter > 2.0:
            self.ui.raJitterEdit.setStyleSheet("color: red;")
            self.ui.decJitterEdit.setStyleSheet("color: red;")
        else:
            self.ui.raJitterEdit.setStyleSheet("color: green;")
            self.ui.decJitterEdit.setStyleSheet("color: green;")
            
            
        self.ui.medianSignalEdit.setText(str(round(np.median(self.gdr_counts_data['counts']),2)))

        self.median_seeing = np.median(self.gdr_focus_data['fwhm'])        
        self.ui.medianSeeingEdit.setText(str(round(self.median_seeing,2))+'"')
        if self.median_seeing > 2.0:
            self.ui.medianSeeingEdit.setStyleSheet("color: red;")
        elif self.median_seeing > 1.0:
            self.ui.medianSeeingEdit.setStyleSheet("color: orange;")
        elif self.median_seeing <= 1.0:
            self.ui.medianSeeingEdit.setStyleSheet("color: green;")
        self.ui.frameCounterEdit.setText(str(self.frame_counter))
        self.ui.xoffsetEdit.setText(str(round(self.guiding_offset_x,2)))
        self.ui.yoffsetEdit.setText(str(round(self.guiding_offset_y,2)))
        self.ui.fsmXEdit.setText(str(round(self.fsm_angle_x,2)))
        self.ui.fsmYEdit.setText(str(round(self.fsm_angle_y,2)))
        if self.loop_state == 'open':
            self.ui.loopButton.setText("Open")
        elif self.loop_state == 'closed':
            self.ui.loopButton.setText("Closed")
            
        if self.guiding_mode == 'full_frame':
            self.ui.fullFrameRadioButton.setChecked(True)
        elif self.guiding_mode == 'offset':
            self.ui.offsetGuidingRadioButton.setChecked(True)
        elif self.guiding_mode == 'annulus_sep':
            self.ui.annulusGuidingSEPRadioButton.setChecked(True)
        elif self.guiding_mode == 'annulus_quad':
            self.ui.annulusGuidingQuadRadioButton.setChecked(True)
        elif self.guiding_mode == 'annulus_model':
            self.ui.annulusGuidingModelRadioButton.setChecked(True)
            
        self.ui.starROIXPosEdit.setText(str(self.star_roi_xcenter_pix+
                                            self.star_roi_x1))
        self.ui.starROIYPosEdit.setText(str(self.star_roi_ycenter_pix+
                                            self.star_roi_y1))        
        self.ui.pGainEdit.setText(str(round(self.loop_kp,3)))
        self.ui.iGainEdit.setText(str(round(self.loop_ki,3)))
        self.ui.dGainEdit.setText(str(round(self.loop_kd,3)))

        if self.plate_solve_success:
            self.ui.solutionStatusLineEdit.setText('Solved')
        else:
            if self.plate_solve_running:            
                self.ui.solutionStatusLineEdit.setText('Running')
            elif self.plate_solve_running == False:
                self.ui.solutionStatusLineEdit.setText('Not Solved')
            
            
#------------------------------------------------------------------------------
    def on_guider_data(self,new_data):
#        print("Received guider data")
        ts = new_data['timestamp']
        tstamp  = datetime.datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S.%f')
        newtime = dates.date2num(tstamp)
        self.loop_state = new_data['loop_state']
        self.guiding_mode = new_data['guiding_mode']
        self.gdr_tilt_data_x['timestamp'].append(newtime)
        self.gdr_tilt_data_x['dx'].append(new_data['x_mispointing'])
        self.gdr_tilt_data_y['timestamp'].append(newtime)
        self.gdr_tilt_data_y['dy'].append(new_data['y_mispointing'])
        self.gdr_focus_data['timestamp'].append(newtime)
        self.gdr_focus_data['fwhm'].append(new_data['fwhm'])        
        self.gdr_counts_data['timestamp'].append(newtime)
        self.gdr_counts_data['counts'].append(new_data['counts'])
        self.platescale = new_data['platescale']
        self.roi_x1 = new_data['roi_x1']
        self.roi_x2 = new_data['roi_x2']
        self.roi_y1 = new_data['roi_y1']
        self.roi_y2 = new_data['roi_y2']
        self.roi_xdim = self.roi_x2 - self.roi_x1
        self.roi_ydim = self.roi_y2 - self.roi_y1
        self.roi_xcenter = self.roi_xdim/2
        self.roi_ycenter = self.roi_ydim/2

        self.sci_roi_x1 = new_data['sci_roi_x1']
        self.sci_roi_x2 = new_data['sci_roi_x2']
        self.sci_roi_y1 = new_data['sci_roi_y1']
        self.sci_roi_y2 = new_data['sci_roi_y2']
        self.sci_roi_xdim = self.sci_roi_x2 - self.sci_roi_x1
        self.sci_roi_ydim = self.sci_roi_y2 - self.sci_roi_y1
        self.sci_roi_xcenter = self.sci_roi_xdim/2
        self.sci_roi_ycenter = self.sci_roi_ydim/2

        self.sky_roi_x1 = new_data['sky_roi_x1']
        self.sky_roi_x2 = new_data['sky_roi_x2']
        self.sky_roi_y1 = new_data['sky_roi_y1']
        self.sky_roi_y2 = new_data['sky_roi_y2']
        self.sky_roi_xdim = self.sky_roi_x2 - self.sky_roi_x1
        self.sky_roi_ydim = self.sky_roi_y2 - self.sky_roi_y1
        self.sky_roi_xcenter = self.sky_roi_xdim/2
        self.sky_roi_ycenter = self.sky_roi_ydim/2

        self.star_roi_x1 = new_data['star_roi_x1']
        self.star_roi_x2 = new_data['star_roi_x2']
        self.star_roi_y1 = new_data['star_roi_y1']
        self.star_roi_y2 = new_data['star_roi_y2']
        self.star_roi_xdim = self.star_roi_x2 - self.star_roi_x1
        self.star_roi_ydim = self.star_roi_y2 - self.star_roi_y1
        self.star_roi_xcenter_pix = int(self.star_roi_xdim/2)
        self.star_roi_ycenter_pix = int(self.star_roi_ydim/2)
        
        self.camera_xcenter_pix = new_data['camera_xcenter_pix']
        self.camera_ycenter_pix = new_data['camera_ycenter_pix']
        self.exposure_time = new_data['exposure_time']
        self.cadence = new_data['cadence']
        self.sensor_temp = new_data['sensor_temp']
        self.sensor_temp_status = new_data['sensor_temp_status']
        self.frame_counter = new_data['frame_counter']
        self.region_xcen = self.camera_xcenter_pix + \
                           new_data['x_mispointing']/self.platescale
        self.region_ycen = self.camera_ycenter_pix + \
                           new_data['y_mispointing']/self.platescale
        self.region_radius = new_data['fwhm']/self.platescale
        self.sci_hole_xwidth = new_data['sci_hole_xwidth']
        self.sci_hole_ywidth = new_data['sci_hole_ywidth']
        self.sky_hole_xwidth = new_data['sky_hole_xwidth']
        self.sky_hole_ywidth = new_data['sky_hole_ywidth']
        self.guiding_offset_x = new_data['guiding_offset_x']
        self.guiding_offset_y = new_data['guiding_offset_y']
        self.loop_kp = new_data['loop_kp']
        self.loop_ki = new_data['loop_ki']
        self.loop_kd = new_data['loop_kd']

        self.fsm_angle_x = new_data['fsm_angle_x']
        self.fsm_angle_y = new_data['fsm_angle_y']
        self.gdr_fsm_data_x['timestamp'].append(newtime)
        self.gdr_fsm_data_x['dx'].append(new_data['fsm_angle_x'])
        self.gdr_fsm_data_y['timestamp'].append(newtime)
        self.gdr_fsm_data_y['dy'].append(new_data['fsm_angle_y'])
        self.plate_solve_running = new_data['plate_solve_running']
        self.plate_solve_success = new_data['plate_solve_success']
        self.wcs_hdr_dict = new_data['wcs_hdr_dict']
        
        self.base64_bytes = new_data['image'].encode('utf-8')
        self.img_bytes = base64.b64decode(self.base64_bytes)
        self.image = np.frombuffer(self.img_bytes,dtype=np.uint16).reshape((self.roi_ydim,self.roi_xdim))

        self.sky_base64_bytes = new_data['sky_roi'].encode('utf-8')
        self.sky_roi_bytes = base64.b64decode(self.sky_base64_bytes)
        self.sky_roi = np.frombuffer(self.sky_roi_bytes,dtype=np.uint16).reshape((self.sky_roi_ydim,self.sky_roi_xdim))

        self.sci_base64_bytes = new_data['sci_roi'].encode('utf-8')
        self.sci_roi_bytes = base64.b64decode(self.sci_base64_bytes)
        self.sci_roi = np.frombuffer(self.sci_roi_bytes,dtype=np.uint16).reshape((self.sci_roi_ydim,self.sci_roi_xdim))

        self.star_base64_bytes = new_data['star_roi'].encode('utf-8')
        self.star_roi_bytes = base64.b64decode(self.star_base64_bytes)
        self.star_roi = np.frombuffer(self.star_roi_bytes,dtype=np.uint16).reshape((self.star_roi_ydim,self.star_roi_xdim))
#        print(new_data)
        self.replot_tilts()
        self.replot_bullseye()
        self.replot_profile()
        self.replot_focus()
        self.replot_counts()
        self.update_gui()
        
        if self.ds9_live_updates:
            if self.ds9_inspect_ff:
                try:
                    ff_hdr = {}
                    if self.plate_solve_success:
                        ff_hdr = fits.Header(self.wcs_hdr_dict)
                        hdu = fits.PrimaryHDU(self.image,header=ff_hdr)
                    else:
                        hdu = fits.PrimaryHDU(self.image)
                    hdulist = fits.HDUList([hdu])
                    self.ds9_ff.set_pyfits(hdulist)

#                    self.ds9_ff.set_np2arr(self.image)
                    # self.ds9_ff.set('regions', 'image; circle(%f,%f,%f)' %
                    #                 (self.region_xcen,self.region_ycen,
                    #                  self.region_radius))
                    # self.ds9_ff.set('regions', 'image; circle(%f,%f,%f)' %
                    #                 (self.camera_xcenter_pix,
                    #                  self.camera_ycenter_pix,
                    #                  self.sci_hole_xwidth/self.platescale))
                except:
                    print("DS9 full frame window closed")
                    self.ds9_inspect_ff = False
                    
            if self.ds9_inspect_sci:
                try:
                    self.ds9_sci.set_np2arr(self.sci_roi)
                    # self.ds9_sci.set('regions', 'image; circle(%f,%f,%f)' %
                    #                  (self.region_xcen,self.region_ycen,
                    #                   self.region_radius))
                    # self.ds9_sci.set('regions', 'image; circle(%f,%f,%f)' %
                    #                  (self.camera_xcenter_pix,
                    #                   self.camera_ycenter_pix,
                    #                   self.sci_hole_xwidth/self.platescale))
                except:
                    print("DS9 Sci ROI window closed")
                    self.ds9_inspect_sci = False
                    
            if self.ds9_inspect_sky:
                try:
                    self.ds9_sky.set_np2arr(self.sky_roi)
                    # self.ds9_sky.set('regions', 'image; circle(%f,%f,%f)' %
                    #                  (self.camera_xcenter_pix,
                    #                   self.camera_ycenter_pix,
                    #                   self.sci_hole_xwidth/self.platescale))
                except:
                    print("DS9 Sky ROI window closed")
                    self.ds9_inspect_sky = False
                    
            if self.ds9_inspect_star:
                try:
                    self.ds9_star.set_np2arr(self.star_roi)
                    # self.ds9_star.set('regions', 'image; circle(%f,%f,%f)' %
                    #                  (self.camera_xcenter_pix,
                    #                   self.camera_ycenter_pix,
                    #                   self.sci_hole_xwidth/self.platescale))
                except:
                    print("DS9 Star ROI window closed")
                    self.ds9_inspect_star = False

#        print("Received image data");
#        h,w = struct.unpack('>II',new_data[:8])
#        image = np.frombuffer(new_data[8:],dtype=np.uint16).reshape(h,w)
#        ts = new_data['timestamp']
#        tstamp  = datetime.datetime.strptime(ts,'%Y-%m-%dT%H:%M:%S.%f')
#        newtime = dates.date2num(tstamp)
#        print("Got new image")
#        self.ds9.set_np2arr(image)

#------------------------------------------------------------------------------
    def on_events(self,new_events_dict):
        print("Got events")
        print(new_events_dict)              
        for new_event in new_events_dict:
            print(new_event)
            print(new_events_dict[new_event])
            res = self.event_tree[new_event](new_events_dict[new_event])
        print("Done processing events");


#-------------------------------------------------------------------------------
    def on_dx(self,message):
        print(message)

#-------------------------------------------------------------------------------
    def on_dy(self,message):
        print(message)

#-------------------------------------------------------------------------------
    def on_gdr_onoff(self):
        pass
    
#-------------------------------------------------------------------------------
    def on_set_offsets(self):
        print("In on_set_fsm")        
        new_offsetx = self.ui.xoffsetSpinBox.value()
        new_offsety = self.ui.yoffsetSpinBox.value()
        res = self.command_sender.send({'offset_angle':[new_offsety,new_offsetx]})        

#-------------------------------------------------------------------------------
    def on_set_fsm(self,checked):
        print("In on_set_fsm")        
        new_fsmx = self.ui.fsmXSpinBox.value()
        new_fsmy = self.ui.fsmYSpinBox.value()
        res = self.command_sender.send({'fsm_angle':[new_fsmx,new_fsmy]})    

#-------------------------------------------------------------------------------
    def on_set_gains(self,checked):
        print("In on_set_gains")        
        new_pgain = self.ui.pGainSpinBox.value()
        new_igain = self.ui.iGainSpinBox.value()
        new_dgain = self.ui.dGainSpinBox.value()        
        res = self.command_sender.send({'loop_gains':[new_pgain,new_igain,new_dgain]})    

#-------------------------------------------------------------------------------
    def on_set_roi_manually(self,checked):
        print("In on_set_roi_manually")        
        new_xcenter = self.ui.starROIXPosSpinBox.value()
        new_ycenter = self.ui.starROIYPosSpinBox.value()
        res = self.command_sender.send(
            {'star_position':[new_ycenter,new_xcenter]})
    
#-------------------------------------------------------------------------------
    def on_set_exposure_time(self,checked):
        print("In on_set_exposure_time")        
        new_exposure_time = self.ui.exptime1SpinBox.value()
        res = self.command_sender.send({'exposure_time':new_exposure_time})        

#-------------------------------------------------------------------------------
    def on_standby(self):
        pass

#-------------------------------------------------------------------------------
    def on_azelxy(self):
        pass
    
#-------------------------------------------------------------------------------
    def on_bucketsize(self):
        pass
    
#-------------------------------------------------------------------------------
    def on_change_loop(self,checked):
        print("In on_change_loop")
        if self.ui.loopButton.text() == 'Open':
            res = self.command_sender.send({'loop_state':1})
            print("Closing loops")
        elif self.ui.loopButton.text() == 'Closed':
            res = self.command_sender.send({'loop_state':0})
            print("Opening loops")

#-------------------------------------------------------------------------------
    def on_set_cadence(self,checked):
        print("In on_set_cadence")
        self.command_sender.send({'cadence':self.ui.cadenceSpinBox.value()})
        
#-------------------------------------------------------------------------------
    def on_exposure_time_changed(self,sval):
        print("Got message that exposure time changed")
        self.ui.exptime1Edit.setText(str(sval))

#-------------------------------------------------------------------------------
    def on_cadence_changed(self,sval):
        print("Got message that cadence changed")
        self.ui.cadenceEdit.setText(str(sval))

#-------------------------------------------------------------------------------
    def on_gains_changed(self,sval):
        print("Got message that gains changed",sval[0],sval[1],sval[2])
        self.ui.pGainEdit.setText(str(round(sval[0],3)))
        self.ui.iGainEdit.setText(str(round(sval[1],3)))
        self.ui.dGainEdit.setText(str(round(sval[2],3)))

#-------------------------------------------------------------------------------
    def on_plate_solve_event(self,sval):
        print("Got message of plate solve event")
        self.plate_solve_success = sval[0]
        self.plate_solve_running = sval[1]
        self.wcs_hdr_dict = sval[2]
        self.plate_solve_res = sval[3]
        
        
#-------------------------------------------------------------------------------
    def on_loop_changed(self,sval):
        print("Got message that loop state changed")
        if sval == True:
            self.ui.loopButton.setText('Closed')
#            self.loopButton.toggled.emit(True)
        elif sval == False:
            self.ui.loopButton.setText('Open')            
#            self.loopButton.toggled.emit(False)

#-------------------------------------------------------------------------------
    def on_change_framing(self,checked):
        print("In on_change_framing")
        if self.ui.enableButton.text() == 'Running':
            res = self.command_sender.send({'framing':0})
            print("Stopping camera framing")
        elif self.ui.enableButton.text() == 'Stopped':
            res = self.command_sender.send({'framing':1})
            print("Starting camera framing")

#-------------------------------------------------------------------------------
    def on_framing_changed(self,sval):
        print("Got message that framing state changed")
        if sval == True:
            self.ui.enableButton.setText('Running')
        elif sval == False:
            self.ui.enableButton.setText('Stopped')

#-------------------------------------------------------------------------------
    def on_ds9_inspect_dark(self,sval):
        print("Inspecting dark")
        pass
    
#-------------------------------------------------------------------------------
    def on_ds9_inspect_full_frame(self,sval):
        print("Inspecting full frame")
        self.ds9_inspect_ff = True
        self.ds9_ff = pyds9.DS9('TRES_Full_Frame')
        self.ds9_ff.set('zoom to fit')
        self.ds9_ff.set('preserve pan')
#        ff_hdr = self.fits_hdr
        ff_hdr = {}
        if self.plate_solve_success:
            ff_hdr = fits.Header(self.wcs_hdr_dict)
            hdu = fits.PrimaryHDU(self.image,header=ff_hdr)
        else:
            hdu = fits.PrimaryHDU(self.image)
        hdulist = fits.HDUList([hdu])
        self.ds9_ff.set_pyfits(hdulist)

#-------------------------------------------------------------------------------
    def on_ds9_inspect_object_fiber(self,sval):
        print("Inspecting object fiber frame")
        self.ds9_inspect_sci = True
        self.ds9_sci = pyds9.DS9('TRES_Sci_ROI')
        self.ds9_sci.set('zoom to fit')
        self.ds9_sci.set('preserve pan')        
        self.ds9_sci.set_np2arr(self.sci_roi)

#-------------------------------------------------------------------------------
    def on_ds9_inspect_sky_fiber(self,sval):
        print("Inspecting sky fiber frame")
        self.ds9_inspect_sky = True
        self.ds9_sky = pyds9.DS9('TRES_Sky_ROI')
        self.ds9_sky.set('zoom to fit')
        self.ds9_sky.set('preserve pan')        
        self.ds9_sky.set_np2arr(self.sky_roi)        

#-------------------------------------------------------------------------------
    def on_ds9_inspect_star(self,sval):
        print("Inspecting star ROI")
        self.ds9_inspect_star = True
        self.ds9_star = pyds9.DS9('TRES_Star_ROI')
        self.ds9_star.set('zoom to fit')
        self.ds9_star.set('preserve pan')        
        self.ds9_star.set_np2arr(self.star_roi)        
        
#-------------------------------------------------------------------------------
    def on_ds9_live_updates(self,sval):
        print("Toggling DS9 live updates")
        print(sval)
        self.ds9_live_updates = sval
        pass
    
#-------------------------------------------------------------------------------
    def on_full_frame_guiding(self,sval):
        print("Using full frame guiding")
        res = self.command_sender.send({'guiding_mode':'full_frame'})        
        pass
    
#-------------------------------------------------------------------------------
    def on_offset_guiding(self,sval):
        print("Using offset guiding")
        res = self.command_sender.send({'guiding_mode':'offset'})        
        pass

#-------------------------------------------------------------------------------
    def on_annulus_guiding_sep(self,sval):
        print("Using annulus guiding with SEP")
        res = self.command_sender.send({'guiding_mode':'annulus_sep'})        

#-------------------------------------------------------------------------------
    def on_annulus_guiding_quad(self,sval):
        print("Using annulus guiding with quadrants")
        res = self.command_sender.send({'guiding_mode':'annulus_quad'})

#-------------------------------------------------------------------------------
    def on_annulus_guiding_model(self,sval):
        print("Using annulus guiding with model fit")
        res = self.command_sender.send({'guiding_mode':'annulus_model'})
        
#-------------------------------------------------------------------------------
    def on_acquisition_mouse(self,sval):
        print("Using mouse click for acquisition")
        pass
    
#-------------------------------------------------------------------------------
    def on_acquisition_plate_solving(self,sval):
        print("Using plate solving for acquistion")
        pass

#-------------------------------------------------------------------------------
    def on_ds9_inspect_flat(self,sval):
        print("Inspecting flat using ds9")
        pass
    
#-------------------------------------------------------------------------------
    def on_acquire_dark(self,sval):
        print("Acquiring dark frame")
        pass
    
#-------------------------------------------------------------------------------
    def on_zero_dark(self,sval):
        print("Zeroing dark frame")
        pass
    
#-------------------------------------------------------------------------------
    def on_load_dark(self,sval):
        print("Loading dark frame")
        pass

#-------------------------------------------------------------------------------
    def on_acquire_flat(self,sval):
        print("Acquiring flat field")
        pass

#-------------------------------------------------------------------------------
    def on_unity_flat(self,sval):
        print("Setting flat field to unity")
        pass

#-------------------------------------------------------------------------------
    def on_load_flat(self,sval):
        print("Loading flat field")
        pass
    
#-------------------------------------------------------------------------------
    def on_latch_crosshair(self,sval):
        print("Latching DS9 crosshair in full frame image")
        try:
            crosshair_str = self.ds9_ff.get("crosshair")
            print(crosshair_str)
            res = crosshair_str.split()
            self.crosshair_xpixel = float(res[0])
            self.crosshair_ypixel = float(res[1])
            res = self.command_sender.send(
                {'star_position':[self.crosshair_ypixel,self.crosshair_xpixel]})
        except:
            print("Failed to latch crosshair.")

    
#-------------------------------------------------------------------------------
    def on_acquire_telescope_focus(self,sval):
        print("Acquiring telescope focus")
        pass

#-------------------------------------------------------------------------------
    def on_plate_solve(self,sval):
        print("Plate solving full frame image")
        self.plate_solve_running = True
        self.plate_solve_success = False
        res = self.command_sender.send({'plate_solve':True})        

#-------------------------------------------------------------------------------
    def on_correct_pointing(self,sval):
        print("Correcting telescope pointing")
        pass
            
################################################################################
if __name__ == "__main__":
    base_directory = './'

    config_file = 'tres_gui.ini'
    logging.getLogger('quamash').setLevel(logging.ERROR)
    app = QtWidgets.QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    atexit.register(loop.close)
    
    tresgui = TresGUI(base_directory,config_file,loop)
    tresgui.show()

    loop.run_until_complete(tresgui.exit_request.wait())
         
        
    
