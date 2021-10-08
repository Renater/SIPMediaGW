#!/usr/bin/env python

import cv2
from PIL import Image, ImageFont, ImageDraw
import numpy as np


class Ivr :
    def __init__(self, prompt, bgFile, fontFile, fontsize):
        self.prompt = prompt
        im = Image.open(bgFile)
        width, height = im.size
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


    def show(self, width, height, inStr=''):
        if inStr:
            im = self.addText(inStr)
        else:
            im = self.promptIm

        cv2.imshow('IVR', cv2.resize(im, (width, height)))
        cv2.waitKey(10)


