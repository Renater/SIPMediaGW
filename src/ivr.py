#!/usr/bin/env python

import cv2
from PIL import Image, ImageFont, ImageDraw
import time
import numpy as np
import threading


class Ivr :
    def __init__(self, prompt, bgFile, fontFile, fontsize):
        self.prompt = prompt
        self.maxDelay = 60 #seconds
        self.timeOutTh = None
        im = Image.open(bgFile)
        width, height = im.size
        cv2.namedWindow('IVR')
        cv2.moveWindow('IVR',0,-28) # To remove the grey border on the top...
        font = ImageFont.truetype(fontFile, fontsize)
        textSize = font.getsize(prompt)
        textX = int((width - textSize[0]) / 2)
        textY = int((height + textSize[1]) / 2.5)
        
        draw = ImageDraw.Draw(im)
        draw.text((textX, textY), prompt, font=font, fill="black")

        self.promptIm = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR) 

    def addText(self, inStr):
        height, width, depth = (self.promptIm).shape
        font = cv2.FONT_HERSHEY_SIMPLEX
        textSize = cv2.getTextSize(inStr, font, 1, 2)[0]
        textX = int((width - textSize[0]) / 2)
        textY = int((height + textSize[1]) / 1.5)
        self.ivrIm = (self.promptIm).copy()
        cv2.putText(self.ivrIm, inStr, (textX, textY ), font, 1, (0,0,0), 2)

        return self.ivrIm

    def show(self, width, height, inStr='', wait=10):
        if inStr:
            im = self.addText(inStr)
        else:
            im = self.promptIm
        self.update=True
        if self.timeOutTh:
            self.timeOutTh.join()
        cv2.imshow('IVR', cv2.resize(im, (width, height)))
        cv2.waitKey(wait)
        self.update = False
        self.timeOutTh = threading.Thread(target=self.timeOut, args=(lambda: self.update,))
        self.timeOutTh.start()

    def onTimeout(self):
        pass

    def timeOut(self, stop):
        runTime = 0
        while True:
            time.sleep(0.1)
            if stop():
                break
            runTime+=0.1
            if runTime >= self.maxDelay:
                self.onTimeout()
                break

    def close(self):
        cv2.destroyAllWindows()
        self.update = True
        if self.timeOutTh:
            self.timeOutTh.join()


